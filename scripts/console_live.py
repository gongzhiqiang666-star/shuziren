"""Run a local live session from the console's existing selections."""
from collections import deque
import json
import logging
import sqlite3
from pathlib import Path
from queue import Empty, Full, Queue, SimpleQueue
import sys
import subprocess
import threading
import time
import uuid

from scripts.product_store import Conflict, ProductError, playback_segments, product_fact_deadline, verified_product_facts


class ConsoleLive:
    active_states = {'preparing', 'running', 'stopping'}

    def __init__(self, tts, directory, *, device_buffer_frames=8):
        self.tts = tts
        self.directory = Path(directory).resolve()
        self.device_buffer_frames = device_buffer_frames
        self.lock = threading.RLock()
        self.thread = None
        self.session = None
        self.client = None
        self.cancel = threading.Event()
        self.status = {'status': 'idle'}
        self.rotation = None
        self.reply_session = None
        self.completed = SimpleQueue()

    def state(self):
        with self.lock:
            state = dict(self.status)
            if self.session is not None:
                state['frames'] = self.session.frames_written
                state['camera_frames'] = self.session.sink.camera.frames
                state.update(self.session.control_state())
            rotation = self.rotation
            if rotation:
                current = rotation['items'][rotation['index']]
                stock = current.get('stock_evidence')
                deadline = current.get('fact_deadline')
                if stock and (deadline is None or time.time() < deadline):
                    state['rotation_stock_evidence'] = stock
            if rotation and len(rotation['items']) > 1 and not state.get('manual'):
                item = rotation['items'][rotation['index']]
                started = rotation.get('shift_started_at')
                duration = item.get('duration_seconds')
                if started is not None and duration is not None and time.monotonic() >= started + duration:
                    state['shift_waiting_for_boundary'] = {
                        key: item[key] for key in ('product_id', 'product_version', 'script_id', 'duration_seconds')
                    }
                    state['shift_waiting_for_boundary']['shift_started_at_monotonic'] = started
            return state

    def stall_snapshot(self):
        with self.lock:
            session = self.session
            worker = self.client.process if self.client is not None else None
        return {
            'session': session.stall_context() if session is not None else None,
            'worker': {'pid': worker.pid, 'exit_code': worker.poll()} if worker is not None else None,
        }

    def start(self, audio_device, *, language='zh-CN', assistant_voice_id=None, camera_device=None, rtmp_url=None):
        if type(audio_device) is not int or audio_device < 0:
            raise ProductError('请选择明确的音频输出设备')
        with self.lock:
            if self.status['status'] in self.active_states:
                raise Conflict('已有场次正在运行或清理')
            if assistant_voice_id is not None:
                self.tts.voices.get(assistant_voice_id)
            self.cancel.clear()
            session_id = uuid.uuid4().hex
            self.status = {'id': session_id, 'status': 'preparing', 'audio_device': audio_device,
                           'frames': 0, 'rotation_language': language, 'assistant_voice_id': assistant_voice_id,
                           'requested_at': time.time()}
            if camera_device is not None:
                self.status['requested_camera_device'] = camera_device
            self._record_session()
            self.rotation = None
            self.reply_session = None
            self.completed = SimpleQueue()
            self.thread = threading.Thread(target=self._run, args=(session_id, audio_device, camera_device, rtmp_url), name='console-live')
            self.thread.start()
            return self.state()

    def _run(self, session_id, audio_device, camera_device=None, rtmp_url=None):
        client = receiver = sink = ingress = assembler = None
        ole32 = None
        rotation_thread = None
        rotation_stop = threading.Event()
        error = None
        recent_submissions = deque(maxlen=8)
        try:
            if sys.platform == 'win32':
                import ctypes
                com = ctypes.WinDLL('ole32')
                result = com.CoInitializeEx(None, 0)
                if result < 0:
                    raise OSError(f'音频设备线程初始化失败 ({result:#x})')
                ole32 = com
            from scripts.avatar_store import AvatarStore
            from scripts.continuous_session import ContinuousSession
            from scripts.live_avatar_client import LiveAvatarClient
            from scripts.live_av_device_sink import AVDeviceSink
            from scripts.live_frame_channel import FrameReceiver
            from scripts.live_speech_ingress import LiveSpeechIngress
            from scripts.speech_assembler import SpeechAssembler

            directory = self.directory / 'live' / session_id
            avatars = AvatarStore(self.directory)
            ingress = LiveSpeechIngress(self.tts, avatars, directory)
            binding = ingress.start()
            avatar_id = ingress.context['avatar_id']
            avatar = avatars.identity(avatar_id)
            assembler = SpeechAssembler(directory / 'assembled')
            if self.cancel.is_set():
                return
            client = LiveAvatarClient(self.tts.runtime, avatars.directory(avatar_id), directory, self.directory / 'live-avatar-cache')
            with self.lock:
                self.client = client
            if self.cancel.is_set():
                return
            client.request('start', session_id=binding.id)
            if rtmp_url is not None:
                client.request('attach_rtmp', url=rtmp_url, width=avatar['width'], height=avatar['height'])
            client.request('prepare')
            if self.cancel.is_set():
                return
            receiver = FrameReceiver(binding.id, avatar['width'], avatar['height'])
            client.request('attach_frames', channel=receiver.descriptor())
            sink = AVDeviceSink(
                avatar['width'], avatar['height'], audio_device,
                buffer_frames=self.device_buffer_frames, video_delay_ms=100,
                smooth_clock=True, camera_i420=True,
                camera_device=camera_device,
            )

            def started():
                with self.lock:
                    if not self.cancel.is_set():
                        self.status.update(status='running', started_at=time.time(), camera_device=sink.camera.device)

            def presented(row):
                recent_submissions.append({key: row[key] for key in (
                    'frame_index', 'task_id', 'presented_ns', 'receive_ns', 'pcm_read_ns', 'submit_ns', 'sink_timing')})
                silent_frames = row['silent_speech_frames']
                if silent_frames == 125:
                    self.status['silent_speech'] = {'first_frame': row['frame_index'] - 124}
                elif not silent_frames:
                    self.status.pop('silent_speech', None)
                if self.cancel.is_set():
                    session.stop_event.set()

            def source_complete(event):
                source_id = event['source_id']
                if not source_id.startswith('idle-'):
                    end = session.pcm.read_samples
                    self.completed.put((source_id, end - event['samples'], end))

            session = ContinuousSession(binding.id, client, receiver, sink, assembler.root,
                                        on_started=started, on_present=presented,
                                        on_source_complete=source_complete, idle_frames=4)
            sink.underrun_context = session.stall_context
            with self.lock:
                self.session = session
                self.ingress = ingress
                self.assembler = assembler
            if not self.cancel.is_set():
                rotation_thread = threading.Thread(target=self._rotate, args=(session_id, rotation_stop), name='live-rotation')
                rotation_thread.start()
                session.run()
        except Exception as exc:
            if not self.cancel.is_set():
                logging.exception('本地场次失败')
                error = str(exc)
        finally:
            rotation_stop.set()
            with self.lock:
                self._record_completed()
                if sink is not None and sink.underrun is not None:
                    self.status['device_underrun'] = {**sink.underrun, 'recent_submissions': list(recent_submissions)}
                if self.session is not None:
                    self.status['frames'] = self.session.frames_written
                self.session = None
                self.client = None
                self.status.update(status='stopping')
            if rotation_thread is not None:
                rotation_thread.join()
            for resource, method in [(sink, 'abort'), (receiver, 'close'), (client, 'close'),
                                     (assembler, 'close'), (ingress, 'stop')]:
                if resource is not None:
                    try:
                        getattr(resource, method)()
                    except Exception as exc:
                        logging.exception('场次资源释放失败')
                        error = error or str(exc)
            if ole32 is not None:
                ole32.CoUninitialize()
            with self.lock:
                self.status.update(status='failed' if error else 'stopped', error=error, ended_at=time.time())
                self._record_session()

    def start_video(self, audio_device, video_path, *, backend='cuda'):
        if type(audio_device) is not int or audio_device < 0:
            raise ProductError('请选择明确的音频输出设备')
        if backend not in ('cuda', 'tensorrt'):
            raise ProductError('本地视频推理后端无效')
        if not isinstance(video_path, str) or not video_path.strip():
            raise ProductError('请选择本地驱动视频')
        video = Path(video_path).expanduser()
        if not video.is_absolute() or not video.is_file():
            raise ProductError('本地驱动视频不存在')
        with self.lock:
            if self.status['status'] in self.active_states:
                raise Conflict('已有场次正在运行或清理')
            self.cancel.clear()
            session_id = uuid.uuid4().hex
            self.status = {'id': session_id, 'status': 'preparing', 'mode': 'local_video',
                           'audio_device': audio_device, 'backend': backend, 'frames': 0, 'requested_at': time.time()}
            self.rotation = self.reply_session = None
            self.video_commands = Queue(maxsize=1)
            self.video_insert_snapshot = None
            self._record_session()
            self.thread = threading.Thread(target=self._run_video, args=(session_id, audio_device, video.resolve(), backend),
                                           name='console-origin-live')
            self.thread.start()
            return self.state()

    def _run_video(self, session_id, audio_device, video, backend):
        from scripts.media_runtime import runtime_python

        error = None
        process = None
        reader = None
        final_frames = None
        try:
            directory = self.directory / 'live' / session_id
            directory.mkdir(parents=True)
            command = [str(runtime_python(self.tts.runtime)), '-X', 'utf8', '-m', 'scripts.origin_live_worker',
                       '--runtime-root', str(self.tts.runtime), '--video', str(video), '--audio-device', str(audio_device)]
            if backend == 'tensorrt':
                command.extend(['--tensorrt-cache', str(self.directory / 'origin-engine-cache')])
            events = SimpleQueue()
            with (directory / 'origin-worker.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                           text=True, encoding='utf-8',
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

                def read_events():
                    for line in process.stdout:
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(event, dict):
                            events.put(event)

                reader = threading.Thread(target=read_events, daemon=True)
                reader.start()
                deadline = time.monotonic() + (240 if backend == 'tensorrt' else 60)
                stopping = False
                while process.poll() is None:
                    if self.cancel.is_set() and not stopping:
                        process.stdin.close()
                        stopping = True
                        deadline = time.monotonic() + 10
                    if not stopping:
                        try:
                            command = self.video_commands.get_nowait()
                        except Empty:
                            pass
                        else:
                            process.stdin.write(json.dumps(command) + '\n')
                            process.stdin.flush()
                            deadline = time.monotonic() + 45
                    try:
                        event = events.get(timeout=.1)
                    except Empty:
                        event = {}
                    if event.get('event') == 'running' and not stopping:
                        with self.lock:
                            if not self.cancel.is_set():
                                self.status.update(status='running', started_at=time.time(), frames=event['frames'])
                                self._record_session()
                        deadline = float('inf')
                    elif event.get('event') == 'stopped':
                        final_frames = event['frames']
                    elif event.get('event') == 'seek':
                        if not stopping:
                            deadline = float('inf')
                        with self.lock:
                            self.status.update(seek_position_ms=event['position_ms'], seek_pending=False)
                    elif event.get('event') == 'insert':
                        if not stopping:
                            deadline = float('inf')
                        with self.lock:
                            self.status.update(insert_pending=False, insert_error=event['error'])
                            if event['error'] is None:
                                self.status['last_insert_task_id'] = event['task_id']
                    if time.monotonic() >= deadline:
                        raise TimeoutError('本地视频场次操作超时')
                if process.returncode or not self.cancel.is_set():
                    raise RuntimeError('本地视频工作进程意外退出，请查看场次日志')
        except Exception as exc:
            logging.exception('本地视频场次失败')
            error = str(exc)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                if reader is not None:
                    reader.join()
                while not events.empty():
                    event = events.get_nowait()
                    if event.get('event') == 'stopped':
                        final_frames = event['frames']
                process.stdin.close()
                process.stdout.close()
                if final_frames is not None:
                    with self.lock:
                        self.status['frames'] = final_frames
            with self.lock:
                staged = self.video_insert_snapshot
                self.video_insert_snapshot = None
                if staged is not None:
                    Path(staged).unlink(missing_ok=True)
                self.status.update(status='failed' if error else 'stopped', error=error, ended_at=time.time())
                self._record_session()

    def seek_video(self, session_id, position_ms):
        if type(position_ms) is not int or not 0 <= position_ms <= 86_400_000:
            raise ProductError('请输入有效的视频位置（毫秒）')
        with self.lock:
            if (self.status.get('id') != session_id or self.status['status'] != 'running'
                    or self.status.get('mode') != 'local_video'):
                raise Conflict('本地视频场次尚未就绪')
            if self.status.get('seek_pending') or self.status.get('insert_pending'):
                raise Conflict('正在处理本地视频指令')
            self.video_commands.put_nowait({'action': 'seek', 'position_ms': position_ms})
            self.status['seek_pending'] = True
            return self.state()

    def _record_session(self):
        state = self.status
        try:
            self.tts.products.record_live_session(
                state['id'], state['requested_at'], started_at=state.get('started_at'),
                ended_at=state.get('ended_at'), status=state['status'], frames=state['frames'],
                failure_reason=state.get('error') if state['status'] == 'failed' else None,
            )
        except sqlite3.Error:
            logging.exception('记录场次生命周期失败')
            state['session_event_error'] = '场次生命周期记录写入失败'

    def _record_completed(self):
        while True:
            try:
                source_id, sample_start, sample_end = self.completed.get_nowait()
            except Empty:
                return
            self.status['last_completed_task_id'] = source_id
            if self.rotation and self.rotation['task_id'] == source_id:
                item = self.rotation['items'][self.rotation['index']]
                try:
                    self.tts.products.record_rotation_completion(
                        self.status['id'], source_id, item, self.rotation['segment'],
                        sample_start=sample_start, sample_end=sample_end,
                        voice_id=self.rotation.pop('task_voice_id', None),
                        speech_provenance=self.rotation.pop('task_speech_provenance', None),
                    )
                except sqlite3.Error:
                    logging.exception('记录商品口播完成事件失败')
                    self.status['rotation_event_error'] = '商品口播完成事件写入失败'
                self.rotation['task_id'] = None
                self._advance_rotation(self.rotation)
            else:
                try:
                    self.tts.products.record_reply_playback(self.status['id'], source_id, time.time())
                except sqlite3.Error:
                    logging.exception('记录问答播放完成失败')

    def _advance_rotation(self, rotation):
        item = rotation['items'][rotation['index']]
        rotation['segment'] += 1
        if rotation['segment'] >= len(item.get('segments', (None,))):
            self.status['last_rotation_product_id'] = item['product_id']
            self.status['rotation_completed'] += 1
            if 'duration_seconds' not in item:
                rotation['index'] = (rotation['index'] + 1) % len(rotation['items'])
            rotation['segment'] = 0

    def set_manual(self, session_id, enabled, revision):
        with self.lock:
            if self.status.get('id') != session_id or self.status['status'] != 'running' or self.session is None:
                raise Conflict('场次已变化或尚未就绪')
            try:
                self.session.set_manual(enabled, revision)
            except ValueError as error:
                raise Conflict(str(error)) from error
            state = self.state()
            if state['control_revision'] != revision:
                try:
                    self.tts.products.record_live_control(session_id, state['control_revision'], enabled, time.time())
                except sqlite3.Error:
                    logging.exception('记录手动接管事件失败')
                    self.status['session_event_error'] = '场次控制事件写入失败'
                    state['session_event_error'] = self.status['session_event_error']
            return state

    def reply_context(self):
        with self.lock:
            if self.status['status'] != 'running' or self.session is None:
                raise Conflict('请先启动本机场次')
            control = self.session.control_state()
            if control['manual']:
                raise Conflict('手动接管中，暂不播报评论回复')
            return (self.status['id'], control['control_revision'], self.ingress.context['voice_id'],
                    self.tts.products.get(self.ingress.context['product_id']), self.status['rotation_language'])

    def configure_rotation(self, session_id, product_ids, *, shift_durations=None, shift_voice_ids=None,
                           expected_items=None, preparation=None):
        if shift_durations is not None and (
            not isinstance(shift_durations, list) or len(shift_durations) != len(product_ids)
            or not all(type(duration) in (int, float) and 0 < duration <= 86400
                       for duration in shift_durations)
        ):
            raise ProductError('请为每个班次指定大于0且不超过86400秒的时长')
        if shift_voice_ids is not None and (
            shift_durations is None or not isinstance(shift_voice_ids, list)
            or len(shift_voice_ids) != len(product_ids)
            or not all(voice is None or isinstance(voice, str) and voice for voice in shift_voice_ids)
        ):
            raise ProductError('请为每个班次指定有效的主播音色或沿用场次主播')
        with self.lock:
            if self.status.get('id') != session_id or self.status['status'] != 'running' or self.session is None:
                raise Conflict('场次已变化或尚未就绪')
            items = []
            for index, product_id in enumerate(product_ids):
                product = self.tts.products.get(product_id)
                script_id = self.tts.products.selected_script(product_id)
                if not script_id:
                    raise Conflict(f'请先为商品「{product["title"]}」选用话术')
                item = {'product_id': product_id, 'product_version': product['version'], 'script_id': script_id}
                if expected_items is not None and item != expected_items[index]:
                    raise Conflict('商品或话术已变化，请重新核对轮播配置')
                deadline = product_fact_deadline(product)
                if deadline is not None:
                    item['fact_deadline'] = deadline
                stock = verified_product_facts(product).get('库存')
                if stock and type(stock['value']) is int and stock['value'] == 0:
                    item['stock_evidence'] = {**{key: item[key] for key in ('product_id', 'product_version', 'script_id')},
                                              'source': stock['source']}
                if shift_durations is not None:
                    item['duration_seconds'] = shift_durations[index]
                if shift_voice_ids is not None and shift_voice_ids[index] is not None:
                    voice_id = shift_voice_ids[index]
                    self.tts.voices.get(voice_id)
                    item['shift_voice_id'] = voice_id
                script = next((row for row in self.tts.products.scripts(product_id) if row['id'] == script_id), None)
                if script is None:
                    raise Conflict('选用话术已变化，请重新设置轮播')
                segments = playback_segments(script)
                if any(segment['type'] in {'assistant', 'pause'} for segment in segments):
                    item['segments'] = segments
                items.append(item)
            if self.rotation and self.rotation['task_id']:
                self.session.discard_pending(self.rotation['task_id'])
            if preparation is not None:
                self.tts.products.record_preparation_application(session_id, preparation)
            self.rotation = {'items': items, 'index': 0, 'segment': 0, 'task_id': None} if items else None
            self.status.update(rotation_products=list(product_ids), rotation_completed=0, rotation_error=None)
            self.status.pop('rotation_fault', None)
            self.status.pop('shift_index', None)
            self.status.pop('rotation_retry_products', None)
            self.status.pop('last_rotation_product_id', None)
            return self.state()

    def _check_rotation_item(self, item):
        products = self.tts.products
        if products.get(item['product_id'])['version'] != item['product_version']:
            raise Conflict('轮播商品已修改，请重新设置轮播')
        deadline = item.get('fact_deadline')
        if deadline is not None and time.time() >= deadline:
            raise Conflict('轮播话术引用的商品事实已到期，请核对后重新选用话术')
        if products.selected_script(item['product_id']) != item['script_id']:
            raise Conflict('选用话术已变化，请重新设置轮播')

    def _rotate(self, session_id, stop):
        pending = None
        startup_recorded = False
        while not stop.wait(.15):
            with self.lock:
                if self.cancel.is_set() or self.status['status'] != 'running' or self.session is None:
                    continue
                if not startup_recorded and 'started_at' in self.status:
                    self._record_session()
                    startup_recorded = True
                self._record_completed()
                rotation = self.rotation
                control = self.session.control_state()
                try:
                    if rotation and rotation['task_id']:
                        deadline = rotation['items'][rotation['index']].get('fact_deadline')
                        if deadline is not None and time.time() >= deadline:
                            self.session.discard_pending(rotation['task_id'])
                            raise Conflict('轮播话术引用的商品事实已到期，请核对后重新选用话术')
                    if pending is None and (not rotation or rotation['task_id'] or control['manual']
                                            or self.reply_session or self.session.queue_full()):
                        continue
                    state = self.tts.state()
                    if pending:
                        task_id, origin, revision = pending
                        stale = origin is not rotation or revision != control['control_revision']
                        if stale or not state or state['id'] != task_id:
                            pending = None
                        elif state['status'] == 'succeeded' and not self.session.queue_full():
                            item = rotation['items'][rotation['index']]
                            self._check_rotation_item(item)
                            voice_id = item.get('shift_voice_id', self.ingress.context['voice_id'])
                            if 'segments' in item:
                                segment = item['segments'][rotation['segment']]
                                if segment['type'] == 'assistant':
                                    voice_id = self.status.get('assistant_voice_id') or voice_id
                            if 'segments' in item or 'shift_voice_id' in item:
                                item = {**item, 'voice_id': voice_id}
                            utterance = self.enqueue(session_id, task_id, rotation_item=item)
                            rotation['task_id'] = task_id
                            rotation['task_voice_id'] = voice_id
                            rotation['task_speech_provenance'] = {
                                key: state[key] for key in ('engine', 'language', 'voice_audio_sha256', 'voice_text_sha256')
                                if key in state
                            }
                            rotation['task_speech_provenance'].update(
                                generated_audio_sha256=utterance.original_sha256,
                                played_pcm_sha256=utterance.pcm_sha256,
                            )
                            pending = None
                        elif state['status'] not in {'running', 'succeeded'}:
                            raise ProductError(state.get('error') or '轮播语音合成失败')
                    elif not state or state['status'] != 'running':
                        self._tick_rotation_shift(rotation, time.monotonic())
                        item = rotation['items'][rotation['index']]
                        self._check_rotation_item(item)
                        options = {'rotation_voice_id': item['shift_voice_id']} if 'shift_voice_id' in item else {}
                        if 'segments' in item:
                            segment = item['segments'][rotation['segment']]
                            if segment['type'] == 'pause':
                                if rotation.get('pause_until') is None:
                                    rotation['pause_until'] = time.monotonic() + segment['duration']
                                elif time.monotonic() >= rotation['pause_until']:
                                    rotation.pop('pause_until')
                                    self._advance_rotation(rotation)
                                continue
                            options.update(segment_index=rotation['segment'],
                                           assistant_voice_id=self.status.get('assistant_voice_id'))
                        with self.tts.lock:
                            current = self.tts.state()
                            if current and current['status'] == 'running':
                                continue
                            task = self.tts.start(
                                item['product_id'], item['script_id'], self.ingress.context['voice_id'],
                                language=self.status['rotation_language'], use_cache=True, rotation=True, **options,
                            )
                        pending = (task['id'], rotation, control['control_revision'])
                except (ValueError, OSError, RuntimeError) as error:
                    logging.exception('商品轮播失败')
                    retry = [item['product_id'] for item in rotation['items']] if rotation else []
                    self.rotation = None
                    self.status.update(rotation_products=[], rotation_error=str(error), rotation_retry_products=retry)
                    failed_item = rotation['items'][rotation['index']] if rotation else None
                    occurred_at = time.time()
                    self.status['rotation_fault'] = {
                        'occurred_at': occurred_at,
                        **{key: failed_item[key] for key in ('product_id', 'product_version', 'script_id')}
                    } if failed_item else {'occurred_at': occurred_at}
                    deadline = failed_item.get('fact_deadline') if failed_item else None
                    if deadline is not None and occurred_at >= deadline:
                        self.status['rotation_fault']['fact_expired_at'] = deadline
                    try:
                        self.tts.products.record_rotation_fault(session_id, occurred_at, str(error), item=failed_item)
                    except sqlite3.Error:
                        logging.exception('记录轮播故障失败')
                    self.status.pop('shift_index', None)
                    pending = None

    def _tick_rotation_shift(self, rotation, now):
        item = rotation['items'][rotation['index']]
        if 'duration_seconds' not in item or rotation['segment']:
            return
        if 'shift_started_at' not in rotation:
            rotation['shift_started_at'] = now
        elif now - rotation['shift_started_at'] >= item['duration_seconds']:
            rotation['index'] = (rotation['index'] + 1) % len(rotation['items'])
            rotation['shift_started_at'] = now
        self.status['shift_index'] = rotation['index']

    def enqueue(self, session_id, task_id, *, priority=False, manual_revision=None, rotation_item=None, reply_guard=None):
        with self.lock:
            if self.status.get('id') != session_id or self.status['status'] != 'running':
                raise Conflict('场次已变化或尚未就绪')
            if self.status.get('mode') == 'local_video':
                if not priority or manual_revision is not None or rotation_item is not None or reply_guard is not None:
                    raise Conflict('本地视频场次请使用优先插播')
                if self.status.get('insert_pending') or self.status.get('seek_pending'):
                    raise Conflict('正在处理本地视频指令')
                snapshot = self.directory / 'live' / session_id / f'{uuid.uuid4().hex}.wav'
                task = self.tts.snapshot_audio(task_id, snapshot)
                if task.get('kind') == 'reply':
                    snapshot.unlink(missing_ok=True)
                    raise Conflict('评论回复只在原场次安排播报')
                self.video_insert_snapshot = snapshot
                self.video_commands.put_nowait({'action': 'insert', 'task_id': task_id, 'path': str(snapshot)})
                self.status.update(insert_pending=True, insert_error=None)
                return
            if self.session is None:
                raise Conflict('场次已变化或尚未就绪')
            if self.session.queue_full(manual_revision):
                raise Conflict('待播队列已满')
            control = self.session.control_state()
            if reply_guard is not None and (any(event.is_set() for event in reply_guard[0]) or reply_guard[1] != control['control_revision']):
                raise Conflict('评论回复已失效')
            task = self.tts.state()
            if task and task['id'] == task_id and task.get('kind') == 'reply' and reply_guard is None:
                raise Conflict('评论回复只在原场次安排播报')
            if manual_revision is None and control['manual']:
                raise Conflict('手动接管中，请使用手动口播')
            if manual_revision is not None and (not control['manual'] or manual_revision != control['control_revision']):
                raise Conflict('手动接管状态已变化，请刷新')
            self.ingress.capture(task_id, rotation_item=rotation_item)
            utterance = None
            while utterance is None:
                utterance = self.assembler.push(self.ingress.take(timeout=2))
            try:
                options = {}
                if task and task['id'] == task_id and task.get('fact_deadline') is not None:
                    options['fact_deadline'] = task['fact_deadline']
                self.session.submit(utterance, priority=priority, manual_revision=manual_revision,
                                    reply_guard=reply_guard, **options)
            except Full:
                utterance.path.unlink(missing_ok=True)
                raise Conflict('待播队列已满') from None
            except Exception:
                utterance.path.unlink(missing_ok=True)
                raise
            return utterance

    def stop(self, session_id):
        with self.lock:
            if self.status.get('id') != session_id:
                raise Conflict('场次已变化，请刷新状态')
            if self.status['status'] not in self.active_states:
                return self.state()
            client = self.client if self.status['status'] == 'preparing' else None
            self.cancel.set()
            self.status.update(status='stopping')
        if client is not None:
            client.close()
        return self.state()

    def close(self):
        state = self.state()
        if state['status'] in self.active_states:
            self.stop(state['id'])
        if self.thread is not None:
            self.thread.join(30)
            if self.thread.is_alive():
                raise RuntimeError('场次退出超时')
