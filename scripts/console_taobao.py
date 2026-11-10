"""Own the Taobao login, comment capture and explicit product controls."""
from collections import deque
import logging
from pathlib import Path
import threading
import time
import uuid

from recovered.taobao_control_capture import TaobaoControlDanmuCapture
from recovered.taobao_live_control import TaobaoLiveControl, TaobaoLoginRequired, taobao_storage_path, _is_control_url
from scripts.product_store import Conflict, ProductError


class ConsoleTaobao:
    def __init__(self, directory):
        self.storage = taobao_storage_path(Path(directory).resolve())
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.thread = None
        self.capture = None
        self.control = None
        self.connection_cancel = threading.Event()
        self.reconnects = 0
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
                    'saved_login': self.storage.is_file(), 'count': self.count, 'reconnects': self.reconnects,
                    'comments': [{key: value for key, value in item.items() if key != 'received_at'}
                                 for item in self.comments]}

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
            self.capture_id = None
            self.count = 0
            self.reconnects = 0
            self.comments.clear()
            self.error = None
            self.status = 'login' if live_id is None else 'connecting'
            self.thread = threading.Thread(target=self._run, args=(live_id,), name='console-taobao', daemon=True)
            self.thread.start()
            return self.state()

    def _run(self, live_id):
        final = 'stopped'
        error = None
        try:
            if live_id is None:
                control = TaobaoLiveControl()
                try:
                    control.login(storage_path=self.storage, login_timeout_sec=180, cancel=self.cancel)
                finally:
                    control.shutdown()
                final = 'signed_in'
            else:
                for attempt in range(4):
                    if self.cancel.is_set():
                        break
                    try:
                        self._capture_once(live_id)
                        break
                    except (TaobaoLoginRequired, ProductError):
                        raise
                    except Exception:
                        if attempt == 3:
                            raise
                        with self.lock:
                            if self.cancel.is_set():
                                break
                            self.reconnects += 1
                            self.status = 'reconnecting'
                        if self.cancel.wait(2 ** attempt):
                            break
        except TaobaoLoginRequired:
            final, error = 'login_required', '淘宝登录已失效，请重新登录'
        except Exception as exc:
            if not self.cancel.is_set():
                logging.warning('淘宝操作失败：%s', type(exc).__name__)
                final, error = 'failed', '淘宝操作失败，请检查浏览器、网络和场次权限'
        finally:
            with self.lock:
                self.status = 'stopped' if self.cancel.is_set() and error is None else final
                self.error = error
                self.cancel.set()

    def _capture_once(self, live_id):
        control = TaobaoLiveControl()
        connection = threading.Event()
        try:
            control._connect_configured(headless=True, storage_state=self.storage)
            if self.cancel.is_set():
                return
            if not control.open_control_page(live_id):
                raise ProductError('无法打开所选淘宝直播场次')
            capture = TaobaoControlDanmuCapture._configured(controller=control, prime_existing=True, reconnect_on_error=True)
            with self.lock:
                if self.cancel.is_set():
                    return
                self.connection_cancel = connection
                self.capture_id = uuid.uuid4().hex
                self.comments.clear()
                self.count = 0
                self.capture = capture
                self.control = control
                capture.start()
                self.status = 'capturing'
            for comment in capture:
                with self.lock:
                    if self.cancel.is_set():
                        break
                    self.count += 1
                    self.comments.append({'id': self.count, 'nickname': comment['nickname'][:120],
                                          'content': comment['content'][:500], 'time': comment['time'][:80],
                                          'received_at': time.monotonic()})
        finally:
            connection.set()
            with self.lock:
                self.capture = None
                self.control = None
            control.shutdown()

    def goods(self, capture_id, goods_id=None):
        with self.lock:
            if self.status != 'capturing' or self.capture_id != capture_id or self.control is None:
                raise Conflict('淘宝场次已变化，请刷新后重试')
            control, connection, live_id = self.control, self.connection_cancel, self.live_id
        deadline = time.monotonic() + 25

        def operate():
            if connection.is_set() or time.monotonic() >= deadline or not control.open_control_page(live_id):
                raise Conflict('淘宝场次已变化或商品操作超时')
            if connection.is_set() or time.monotonic() >= deadline or not _is_control_url(control._page.url, live_id):
                raise Conflict('淘宝场次已变化或商品操作超时')
            items = [{'id': item['itemId'], 'name': item['itemName'][:200]}
                     for item in control._scrape_commodity_dom()[:200] if item.get('itemId')]
            if goods_id is None:
                return {'items': items}
            if not any(item['id'] == goods_id for item in items):
                raise Conflict('该商品不在当前场次商品列表中')
            if connection.is_set() or time.monotonic() >= deadline:
                raise Conflict('淘宝场次已变化或商品操作超时')
            if not control.popup(goods_id):
                raise Conflict('淘宝页面尚未确认商品已开始讲解，请检查平台状态')
            confirm_until = min(deadline, time.monotonic() + 2)
            while not connection.is_set() and time.monotonic() < confirm_until:
                if control._goods_is_explaining(control._page, goods_id):
                    return {'goods_id': goods_id, 'explaining': True}
                control._page.wait_for_timeout(100)
            raise Conflict('淘宝页面尚未确认商品已开始讲解，请检查平台状态')

        try:
            result = control._call('_invoke', timeout=30, callback=operate)
        except Conflict:
            raise
        except Exception:
            raise Conflict('淘宝商品操作失败，请检查场次或登录状态') from None
        if connection.is_set():
            raise Conflict('淘宝场次连接已变化，请重新读取商品状态')
        return result

    def reply_context(self, capture_id, comment_id):
        with self.lock:
            if self.status != 'capturing' or self.cancel.is_set() or self.capture_id != capture_id:
                raise Conflict('评论采集已停止')
            comment = next((item for item in self.comments if item['id'] == comment_id), None)
            if comment is None:
                raise Conflict('评论已离开当前采集列表')
            if self.connection_cancel.is_set():
                raise Conflict('评论采集连接已变化')
            return dict(comment), self.connection_cancel

    def auto_reply_cursor(self):
        with self.lock:
            if self.status != 'capturing' or self.cancel.is_set():
                raise Conflict('请先启动淘宝评论采集')
            if self.connection_cancel.is_set():
                raise Conflict('评论采集连接已变化')
            return self.capture_id, self.connection_cancel, self.count

    def next_reply_comment(self, capture_id, after):
        with self.lock:
            if self.capture_id != capture_id or self.status != 'capturing' or self.cancel.is_set():
                raise Conflict('评论采集已停止或切换')
            cutoff = time.monotonic() - 30
            return next((item['id'] for item in self.comments
                         if item['id'] > after and item['received_at'] >= cutoff), None)

    def stop(self):
        with self.lock:
            if self.status in {'login', 'connecting', 'capturing', 'reconnecting'} and self.thread and self.thread.is_alive():
                self.cancel.set()
                self.connection_cancel.set()
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
