"""Run a local live session from the console's existing selections."""
import logging
from pathlib import Path
from queue import Full
import sys
import threading
import uuid

from scripts.product_store import Conflict, ProductError


class ConsoleLive:
    active_states = {'preparing', 'running', 'stopping'}

    def __init__(self, tts, directory):
        self.tts = tts
        self.directory = Path(directory).resolve()
        self.lock = threading.RLock()
        self.thread = None
        self.session = None
        self.client = None
        self.cancel = threading.Event()
        self.status = {'status': 'idle'}

    def state(self):
        with self.lock:
            return dict(self.status)

    def start(self, audio_device):
        if type(audio_device) is not int or audio_device < 0:
            raise ProductError('请选择明确的音频输出设备')
        with self.lock:
            if self.status['status'] in self.active_states:
                raise Conflict('已有场次正在运行或清理')
            self.cancel.clear()
            session_id = uuid.uuid4().hex
            self.status = {'id': session_id, 'status': 'preparing', 'audio_device': audio_device, 'frames': 0}
            self.thread = threading.Thread(target=self._run, args=(session_id, audio_device), name='console-live')
            self.thread.start()
            return self.state()

    def _run(self, session_id, audio_device):
        client = receiver = sink = ingress = assembler = None
        ole32 = None
        error = None
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
            sink = AVDeviceSink(avatar['width'], avatar['height'], audio_device)

            def started():
                with self.lock:
                    if not self.cancel.is_set():
                        self.status.update(status='running')

            def presented(row):
                with self.lock:
                    self.status['frames'] = row['frame_index'] + 1
                if self.cancel.is_set():
                    session.stop_event.set()

            def source_complete(event):
                source_id = event['source_id']
                if not source_id.startswith('idle-'):
                    with self.lock:
                        self.status['last_completed_task_id'] = source_id

            session = ContinuousSession(binding.id, client, receiver, sink, assembler.root,
                                        on_started=started, on_present=presented,
                                        on_source_complete=source_complete)
            with self.lock:
                self.session = session
                self.ingress = ingress
                self.assembler = assembler
            if not self.cancel.is_set():
                session.run()
        except Exception as exc:
            if not self.cancel.is_set():
                logging.exception('本地场次失败')
                error = str(exc)
        finally:
            with self.lock:
                self.session = None
                self.client = None
                self.status.update(status='stopping')
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

    def enqueue(self, session_id, task_id):
        with self.lock:
            if self.status.get('id') != session_id or self.status['status'] != 'running' or self.session is None:
                raise Conflict('场次已变化或尚未就绪')
            if self.session.ready.full():
                raise Conflict('待播队列已满')
            self.ingress.capture(task_id)
            utterance = None
            while utterance is None:
                utterance = self.assembler.push(self.ingress.take(timeout=2))
            try:
                self.session.submit(utterance)
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
