"""Run a local live session from the console's existing selections."""
from collections import deque
import logging
from pathlib import Path
from queue import Empty, Full, SimpleQueue
import sys
import threading
import uuid

from scripts.product_store import Conflict, ProductError


class ConsoleLive:
    active_states = {'preparing', 'running', 'stopping'}

    def __init__(self, tts, directory, *, device_buffer_frames=2):
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
                state.update(self.session.control_state())
            return state

    def start(self, audio_device):
        if type(audio_device) is not int or audio_device < 0:
            raise ProductError('请选择明确的音频输出设备')
        with self.lock:
            if self.status['status'] in self.active_states:
                raise Conflict('已有场次正在运行或清理')
            self.cancel.clear()
            session_id = uuid.uuid4().hex
            self.status = {'id': session_id, 'status': 'preparing', 'audio_device': audio_device, 'frames': 0}
            self.rotation = None
            self.reply_session = None
            self.completed = SimpleQueue()
            self.thread = threading.Thread(target=self._run, args=(session_id, audio_device), name='console-live')
            self.thread.start()
            return self.state()

    def _run(self, session_id, audio_device):
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
            client.request('prepare')
            if self.cancel.is_set():
                return
            receiver = FrameReceiver(binding.id, avatar['width'], avatar['height'])
            client.request('attach_frames', channel=receiver.descriptor())
            sink = AVDeviceSink(avatar['width'], avatar['height'], audio_device, buffer_frames=self.device_buffer_frames)

            def started():
                with self.lock:
                    if not self.cancel.is_set():
                        self.status.update(status='running')

            def presented(row):
                recent_submissions.append({key: row[key] for key in (
                    'frame_index', 'task_id', 'presented_ns', 'receive_ns', 'pcm_read_ns', 'submit_ns', 'sink_timing')})
                if self.cancel.is_set():
                    session.stop_event.set()

            def source_complete(event):
                source_id = event['source_id']
                if not source_id.startswith('idle-'):
                    self.completed.put(source_id)

            session = ContinuousSession(binding.id, client, receiver, sink, assembler.root,
                                        on_started=started, on_present=presented,
                                        on_source_complete=source_complete)
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
                self.status.update(status='failed' if error else 'stopped', error=error)

    def _record_completed(self):
        while True:
            try:
                source_id = self.completed.get_nowait()
            except Empty:
                return
            self.status['last_completed_task_id'] = source_id
            if self.rotation and self.rotation['task_id'] == source_id:
                item = self.rotation['items'][self.rotation['index']]
                self.status['last_rotation_product_id'] = item['product_id']
                self.status['rotation_completed'] += 1
                self.rotation['index'] = (self.rotation['index'] + 1) % len(self.rotation['items'])
                self.rotation['task_id'] = None

    def set_manual(self, session_id, enabled, revision):
        with self.lock:
            if self.status.get('id') != session_id or self.status['status'] != 'running' or self.session is None:
                raise Conflict('场次已变化或尚未就绪')
            try:
                self.session.set_manual(enabled, revision)
            except ValueError as error:
                raise Conflict(str(error)) from error
            return self.state()

    def reply_context(self):
        with self.lock:
            if self.status['status'] != 'running' or self.session is None:
                raise Conflict('请先启动本机场次')
            control = self.session.control_state()
            if control['manual']:
                raise Conflict('手动接管中，暂不播报评论回复')
            return (self.status['id'], control['control_revision'], self.ingress.context['voice_id'],
                    self.tts.products.get(self.ingress.context['product_id']))

    def configure_rotation(self, session_id, product_ids):
        with self.lock:
            if self.status.get('id') != session_id or self.status['status'] != 'running' or self.session is None:
                raise Conflict('场次已变化或尚未就绪')
            items = []
            for product_id in product_ids:
                product = self.tts.products.get(product_id)
                script_id = self.tts.products.selected_script(product_id)
                if not script_id:
                    raise Conflict(f'请先为商品「{product["title"]}」选用话术')
                items.append({'product_id': product_id, 'product_version': product['version'], 'script_id': script_id})
            if self.rotation and self.rotation['task_id']:
                self.session.discard_pending(self.rotation['task_id'])
            self.rotation = {'items': items, 'index': 0, 'task_id': None} if items else None
            self.status.update(rotation_products=list(product_ids), rotation_completed=0, rotation_error=None)
            self.status.pop('rotation_retry_products', None)
            self.status.pop('last_rotation_product_id', None)
            return self.state()

    def _rotate(self, session_id, stop):
        pending = None
        while not stop.wait(.15):
            with self.lock:
                if self.cancel.is_set() or self.status['status'] != 'running' or self.session is None:
                    continue
                self._record_completed()
                rotation = self.rotation
                control = self.session.control_state()
                if pending is None and (not rotation or rotation['task_id'] or control['manual'] or self.reply_session or self.session.queue_full()):
                    continue
                try:
                    state = self.tts.state()
                    if pending:
                        task_id, origin, revision = pending
                        stale = origin is not rotation or revision != control['control_revision']
                        if stale or not state or state['id'] != task_id:
                            pending = None
                        elif state['status'] == 'succeeded' and not self.session.queue_full():
                            item = rotation['items'][rotation['index']]
                            self.enqueue(session_id, task_id, rotation_item=item)
                            rotation['task_id'] = task_id
                            pending = None
                        elif state['status'] not in {'running', 'succeeded'}:
                            raise ProductError(state.get('error') or '轮播语音合成失败')
                    elif not state or state['status'] != 'running':
                        item = rotation['items'][rotation['index']]
                        if self.tts.products.get(item['product_id'])['version'] != item['product_version']:
                            raise Conflict('轮播商品已修改，请重新设置轮播')
                        with self.tts.lock:
                            current = self.tts.state()
                            if current and current['status'] == 'running':
                                continue
                            task = self.tts.start(item['product_id'], item['script_id'], self.ingress.context['voice_id'], use_cache=True, rotation=True)
                        pending = (task['id'], rotation, control['control_revision'])
                except (ValueError, OSError, RuntimeError) as error:
                    logging.exception('商品轮播失败')
                    retry = [item['product_id'] for item in rotation['items']] if rotation else []
                    self.rotation = None
                    self.status.update(rotation_products=[], rotation_error=str(error), rotation_retry_products=retry)
                    pending = None

    def enqueue(self, session_id, task_id, *, priority=False, manual_revision=None, rotation_item=None, reply_guard=None):
        with self.lock:
            if self.status.get('id') != session_id or self.status['status'] != 'running' or self.session is None:
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
                self.session.submit(utterance, priority=priority, manual_revision=manual_revision, reply_guard=reply_guard)
            except Full:
                utterance.path.unlink(missing_ok=True)
                raise Conflict('待播队列已满') from None
            except Exception:
                utterance.path.unlink(missing_ok=True)
                raise

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
