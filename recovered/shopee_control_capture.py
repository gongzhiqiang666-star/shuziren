"""Recovered polling adapter for Shopee Live seller-centre comments."""

from __future__ import annotations

from collections import deque
from threading import Event
from typing import Any, Dict, Iterator

from .shopee_live_control import get_shopee_controller


class ShopeeControlDanmuCapture:
    def __init__(self, *, poll_interval_sec: float = 1.0, skip_anchor: bool = True) -> None:
        self.poll_interval_sec = float(poll_interval_sec)
        self.skip_anchor = bool(skip_anchor)
        self._stop_event = Event()
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()
        self.running = False

    def start(self) -> None:
        self._seen.clear()
        self._seen_order.clear()
        self._stop_event.clear()
        self.running = True

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()

    def _fingerprint(self, item: Dict[str, str]) -> str:
        return "|".join(
            str(item.get(key) or "")
            for key in ("commentId", "uid", "nickname", "content")
        )

    def _remember(self, key: str) -> None:
        self._seen.add(key)
        self._seen_order.append(key)
        while len(self._seen_order) > 800:
            self._seen.discard(self._seen_order.popleft())

    def _is_anchor(self, item: Dict[str, str]) -> bool:
        return str(item.get("tag") or "").strip().lower() == "host"

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        if not self.running or self._stop_event.is_set():
            return
        controller = get_shopee_controller()
        if not controller.ensure_connected():
            raise RuntimeError("ShopeeLiveControl connect failed")
        while not self._stop_event.is_set():
            for item in controller.fetch_comments():
                if self._stop_event.is_set():
                    return
                if self.skip_anchor and self._is_anchor(item):
                    continue
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                key = self._fingerprint(item)
                if key in self._seen:
                    continue
                self._remember(key)
                notice = str(item.get("tag") or "").strip().lower() == "notice"
                yield {
                    **item,
                    "nickname": str(item.get("nickname") or "").strip() or "用户",
                    "content": content,
                    "platform": "shopee",
                    "msg_type": "通知" if notice else "弹幕",
                    "source": "shopee_control",
                }
            self._stop_event.wait(self.poll_interval_sec)

