"""Recovered helpers for the Taobao control-panel comment capture."""

from collections import deque
import logging
from threading import Event

from .taobao_live_control import TaobaoLiveControl, TaobaoLoginRequired



def comment_fingerprint(item):
    fields = ("nickname", "time", "content", "tag")
    return "|".join(str(item.get(field) or "") for field in fields)


class CommentHistory:
    def __init__(self):
        self._seen = set()
        self._seen_order = deque()
        self._seen_cap = 800

    def remember(self, item):
        key = comment_fingerprint(item)
        if key in self._seen:
            return False
        self._seen.add(key)
        self._seen_order.append(key)
        if len(self._seen_order) > self._seen_cap:
            self._seen.discard(self._seen_order.popleft())
        return True


class TaobaoControlDanmuCapture:
    def __init__(self, *, poll_interval_sec=1.5, skip_anchor=True):
        self.poll_interval_sec = poll_interval_sec
        self.skip_anchor = skip_anchor
        self._controller = None
        self._storage_state = None
        self._history = CommentHistory()
        self._prime_existing = False
        self._reconnect_on_error = False
        self._stopped = Event()
        self._stopped.set()

    @classmethod
    def _configured(cls, *, poll_interval_sec=1.5, skip_anchor=True, controller=None, storage_state=None, prime_existing=False, reconnect_on_error=False):
        instance=cls(poll_interval_sec=poll_interval_sec,skip_anchor=skip_anchor)
        instance._controller=controller; instance._storage_state=storage_state
        instance._prime_existing=prime_existing
        instance._reconnect_on_error=reconnect_on_error
        return instance

    def start(self):
        self._history = CommentHistory()
        self._stopped.clear()

    def stop(self):
        self._stopped.set()

    def __iter__(self):
        if self._stopped.is_set():
            return
        if self._controller is not None:
            yield from self._poll(self._controller)
            return

        controller = TaobaoLiveControl()
        try:
            controller._connect_configured(storage_state=self._storage_state)
            if self._stopped.is_set():
                return
            if not controller.open_control_page():
                raise RuntimeError("Taobao live control page unavailable")
            yield from self._poll(controller)
        finally:
            controller.shutdown()

    def _is_anchor(self, item):
        return "主播" in str(item.get("tag") or "")

    def _fingerprint(self, item):
        return comment_fingerprint(item)

    def _remember(self, key):
        if key in self._history._seen:return None
        self._history._seen.add(key);self._history._seen_order.append(key)
        if len(self._history._seen_order)>self._history._seen_cap:
            self._history._seen.discard(self._history._seen_order.popleft())

    def _poll(self, controller):
        prime = self._prime_existing
        while not self._stopped.is_set():
            try:
                comments = controller.fetch_comments()
            except TaobaoLoginRequired:
                raise
            except Exception:
                if self._reconnect_on_error or (isinstance(controller, TaobaoLiveControl) and not controller.connected()):
                    raise
                logging.getLogger(__name__).exception("Taobao comment polling failed")
                prime = self._prime_existing
                self._stopped.wait(self.poll_interval_sec)
                continue
            if prime:
                for item in comments:
                    self._history.remember(item)
                prime = False
                self._stopped.wait(self.poll_interval_sec)
                continue
            for item in comments:
                if self._stopped.is_set():
                    return
                if self.skip_anchor and self._is_anchor(item):
                    continue
                content = str(item.get("content") or "").strip()
                key=self._fingerprint(item)
                if content and key not in self._history._seen:
                    self._remember(key)
                    yield {
                        **item,
                        "nickname": str(item.get("nickname") or "").strip() or "用户",
                        "content": content,
                        "time": str(item.get("time") or "").strip(),
                        "tag": str(item.get("tag") or "").strip(),

                        "platform": "taobao",
                        "msg_type": "弹幕",
                        "source": "taobao_control",
                    }
            self._stopped.wait(self.poll_interval_sec)
