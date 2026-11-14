"""Recovered unified barrage capture and platform message normalizer."""

from __future__ import annotations

import json
import socket
import queue
import threading
import time


class BarrageCapture:
    VALID_PLATFORMS = {
        "douyin", "kuaishou", "shipinhao", "meituan", "tiktok", "pinduoduo", "taobao",
        "xiaohongshu", "jingdong", "bilibili", "baidu", "shopee", "shoppe", "youtube",
        "facebook", "instagram", "twitter", "other", "general", "wework",
    }

    def __init__(self, platform_type: str, url=None):
        raw = str(platform_type or "other").lower().strip()
        aliases = {"xiapi": "shopee", "xiaopi": "shopee", "shoppe": "shopee",
                   "wechat": "shipinhao", "video_account": "shipinhao"}
        self.raw_platform_type = raw
        self.platform_type = aliases.get(raw, raw)
        if self.platform_type not in self.VALID_PLATFORMS:
            raise ValueError(f"不支持的弹幕平台: {platform_type}")
        self.url = url or "ws://127.0.0.1:8888"
        self._queue = queue.Queue()
        self.websocket = None
        self._receiver_thread = None
        self._keepalive_thread = None
        self._stop = threading.Event()
        self.process = None

    def _clean_port(self, port: int) -> None:
        """Stop a stale bundled websocket wrapper occupying ``port``."""
        process=self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except Exception:
                try:process.kill();process.wait(timeout=1)
                except Exception:pass
        self.process=None
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1",int(port)))
            return None
        except OSError:
            pass
        # Only terminate known capture wrappers. A different application using
        # the same port is left untouched and will surface a normal bind error.
        try:
            import psutil
            wrappers=("pdd_ws_wrapper","tb_ws_wrapper","ocr_capture.py","ws_danmu_capture")
            for connection in psutil.net_connections(kind="tcp"):
                if not connection.laddr or connection.laddr.port!=int(port) or not connection.pid:continue
                target=psutil.Process(connection.pid)
                command=" ".join(target.cmdline()).lower()
                if any(name in command for name in wrappers):
                    target.terminate()
                    try:target.wait(timeout=3)
                    except psutil.TimeoutExpired:target.kill()
        except Exception:
            pass
        return None

    def start(self):
        if self._receiver_thread and self._receiver_thread.is_alive(): return
        self._stop.clear()
        self._receiver_thread = threading.Thread(target=self._connect_and_receive,
                                                 name="BarrageCapture.receiver", daemon=True)
        self._receiver_thread.start()

    def _connect_and_receive(self) -> None:
        from websocket import create_connection
        while not self._stop.is_set():
            try:
                self.websocket = create_connection(self.url, timeout=5)
                self.websocket.settimeout(1)
                self._keepalive_thread = threading.Thread(target=self._keep_alive, daemon=True)
                self._keepalive_thread.start()
                while not self._stop.is_set():
                    try: raw = self.websocket.recv()
                    except TimeoutError: continue
                    except Exception:
                        if self._stop.is_set(): return
                        break
                    if not raw: break
                    try: data = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
                    except (ValueError, UnicodeError): continue
                    if not isinstance(data, dict): continue
                    if data.get("type") == "heartbeat":
                        self.websocket.send('{"type":"heartbeat_ack"}'); continue
                    if data.get("type") == "heartbeat_ack": continue
                    message = self._process_message(data)
                    if message: self._queue.put(message)
            except Exception:
                if self._stop.wait(2): return
            finally:
                socket, self.websocket = self.websocket, None
                if socket:
                    try: socket.close()
                    except Exception: pass

    @staticmethod
    def _result(kind, nickname="", content=""):
        kind = str(kind or "comment").lower()
        aliases = {"chat": "comment", "message": "comment", "member": "enter",
                   "join": "enter", "joined": "enter", "like_count": "like",
                   "弹幕": "comment", "进入直播间": "enter", "关注": "follow",
                   "点赞": "like", "礼物": "gift"}
        return {"type": aliases.get(kind, kind), "nickname": str(nickname or ""),
                "content": str(content or "")}

    def _process_message(self, data):
        handler = getattr(self, f"_process_{self.platform_type}_message", self._process_other_message)
        return handler(data)

    def _process_douyin_message(self, data):
        user = data.get("user") or data.get("user_data") or {}
        return self._result(data.get("type") or data.get("msg_type") or data.get("message_type"),
                            data.get("nickname") or data.get("username") or user.get("nickname"),
                            data.get("content") or data.get("message") or data.get("text"))

    def _process_kuaishou_message(self, data):
        payload = data.get("data") or data.get("Data") or data
        return self._result(payload.get("type") or payload.get("Type"),
                            payload.get("nickname") or payload.get("user_name") or payload.get("userName") or payload.get("Nickname"),
                            payload.get("content") or payload.get("message") or payload.get("Content"))

    def _process_taobao_message(self, data): return self._process_other_message(data)
    def _process_shipinhao_message(self, data): return self._process_other_message(data)
    def _process_meituan_message(self, data): return self._process_other_message(data)
    def _process_pinduoduo_message(self, data): return self._process_other_message(data)

    def _process_tiktok_message(self, data):
        kind = data.get("type") or data.get("event") or "comment"
        text = data.get("content") or data.get("comment") or data.get("message") or ""
        lowered = str(text).lower()
        if any(marker in lowered for marker in ("joined live", "joined the live")): kind = "enter"
        return self._result(kind, data.get("nickname") or data.get("username") or data.get("userName"), text)

    def _process_other_message(self, data):
        payload = data.get("data") if isinstance(data.get("data"), dict) else data
        kind = payload.get("type") or payload.get("message_type") or payload.get("event") or "comment"
        nickname = (payload.get("nickname") or payload.get("username") or payload.get("userName")
                    or payload.get("Nickname") or payload.get("User") or "")
        content = (payload.get("content") or payload.get("message") or payload.get("text")
                   or payload.get("Content") or payload.get("giftName") or "")
        return self._result(kind, nickname, content)

    def get_barrage(self, timeout=0.5):
        try: return self._queue.get(timeout=timeout)
        except queue.Empty: return None

    def __iter__(self):
        while not self._stop.is_set():
            message = self.get_barrage()
            if message is not None: yield message

    def _keep_alive(self):
        while not self._stop.wait(15):
            socket = self.websocket
            if socket is None: return
            try: socket.send('{"type":"heartbeat"}')
            except Exception: return

    def stop(self):
        self._stop.set()
        socket, self.websocket = self.websocket, None
        if socket:
            try: socket.close()
            except Exception: pass
        if self._receiver_thread and self._receiver_thread is not threading.current_thread():
            self._receiver_thread.join(timeout=2)
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()
