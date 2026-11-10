"""Own the Taobao login and read-only comment capture for one console."""
from collections import deque
import logging
from pathlib import Path
import threading
import uuid

from recovered.taobao_control_capture import TaobaoControlDanmuCapture
from recovered.taobao_live_control import TaobaoLiveControl, TaobaoLoginRequired, taobao_storage_path
from scripts.product_store import Conflict, ProductError


class ConsoleTaobao:
    def __init__(self, directory):
        self.storage = taobao_storage_path(Path(directory).resolve())
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.thread = None
        self.capture = None
        self.status = 'idle'
        self.error = None
        self.live_id = None
        self.capture_id = None
        self.count = 0
        self.comments = deque(maxlen=50)
        self.closed = False

    def state(self):
        with self.lock:
            return {'status': self.status, 'error': self.error, 'live_id': self.live_id, 'capture_id': self.capture_id,
                    'saved_login': self.storage.is_file(), 'count': self.count,
                    'comments': list(self.comments)}

    def login(self):
        return self._start(None)

    def start(self, live_id):
        if not isinstance(live_id, str) or not live_id.isascii() or not live_id.isdecimal() or len(live_id) > 30:
            raise ProductError('请输入淘宝直播场次 ID')
        return self._start(live_id)

    def _start(self, live_id):
        with self.lock:
            if self.closed or (self.thread and self.thread.is_alive()):
                raise Conflict('请先等待当前淘宝操作结束')
            if live_id is not None and not self.storage.is_file():
                raise Conflict('请先登录淘宝')
            self.cancel = threading.Event()
            self.live_id = live_id
            self.capture_id = uuid.uuid4().hex if live_id is not None else None
            self.count = 0
            self.comments.clear()
            self.error = None
            self.status = 'login' if live_id is None else 'connecting'
            self.thread = threading.Thread(target=self._run, args=(live_id,), name='console-taobao', daemon=True)
            self.thread.start()
            return self.state()

    def _run(self, live_id):
        control = TaobaoLiveControl()
        final = 'stopped'
        error = None
        try:
            if live_id is None:
                control.login(storage_path=self.storage, login_timeout_sec=180, cancel=self.cancel)
                final = 'signed_in'
            else:
                control._connect_configured(headless=True, storage_state=self.storage)
                if self.cancel.is_set():
                    return
                if not control.open_control_page(live_id):
                    raise ProductError('无法打开所选淘宝直播场次')
                capture = TaobaoControlDanmuCapture._configured(controller=control, prime_existing=True)
                with self.lock:
                    if self.cancel.is_set():
                        return
                    self.capture = capture
                    capture.start()
                    self.status = 'capturing'
                for comment in capture:
                    with self.lock:
                        if self.cancel.is_set():
                            break
                        self.count += 1
                        self.comments.append({'id': self.count, 'nickname': comment['nickname'][:120],
                                              'content': comment['content'][:500], 'time': comment['time'][:80]})
        except TaobaoLoginRequired:
            final, error = 'login_required', '淘宝登录已失效，请重新登录'
        except Exception as exc:
            if not self.cancel.is_set():
                logging.warning('淘宝操作失败：%s', type(exc).__name__)
                final, error = 'failed', '淘宝操作失败，请检查浏览器、网络和场次权限'
        finally:
            try:
                control.shutdown()
            except Exception as exc:
                logging.warning('淘宝浏览器关闭失败：%s', type(exc).__name__)
                final, error = 'failed', '淘宝浏览器关闭失败'
            with self.lock:
                self.capture = None
                self.status = 'stopped' if self.cancel.is_set() and error is None else final
                self.error = error
                self.cancel.set()

    def reply_context(self, capture_id, comment_id):
        with self.lock:
            if self.status != 'capturing' or self.cancel.is_set() or self.capture_id != capture_id:
                raise Conflict('评论采集已停止')
            comment = next((item for item in self.comments if item['id'] == comment_id), None)
            if comment is None:
                raise Conflict('评论已离开当前采集列表')
            return dict(comment), self.cancel

    def stop(self):
        with self.lock:
            if self.status in {'login', 'connecting', 'capturing'} and self.thread and self.thread.is_alive():
                self.cancel.set()
                if self.capture:
                    self.capture.stop()
                self.status = 'stopping'
            return self.state()

    def close(self):
        with self.lock:
            self.closed = True
            self.stop()
            thread = self.thread
        if thread:
            thread.join(45)
            if thread.is_alive():
                logging.warning('等待淘宝浏览器退出超时')
