import asyncio
import json
import gzip
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recovered.assets.ws_danmu_capture.pdd.pinduoduo_danmu import (PinduoduoDanmu,
    _gzip_decompress_limited, normalize_pdd_live_url)
from recovered.danmu_bridge import PinduoduoDanmuBridge
from recovered.digital_live_manager import DigitalLiveManager
from recovered.ws_capture import BarrageCapture


class FakeSocket:
    def __init__(self):
        self.messages = []

    def send(self, value):
        self.messages.append(value)


class PddBridgeTests(unittest.TestCase):
    def test_live_url_requires_official_https_host(self):
        value = "https://mobile.yangkeduo.com/live.html?id=1"
        self.assertEqual(normalize_pdd_live_url(value), value)
        for invalid in ("http://mobile.yangkeduo.com/live", "https://yangkeduo.com.evil.test/live", "file:///local"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalize_pdd_live_url(invalid)

    def test_bridge_uses_dynamic_port_and_sends_validated_url(self):
        bridge = PinduoduoDanmuBridge("https://live.pinduoduo.com/room/1", port=23456)
        socket = FakeSocket()
        with mock.patch("recovered.danmu_bridge._SubprocessDanmuBridge.start", side_effect=lambda: setattr(bridge, "_socket", socket)):
            bridge.start()
        self.assertEqual(bridge.url, "ws://127.0.0.1:23456")
        self.assertEqual(json.loads(socket.messages[0]), {"url": "https://live.pinduoduo.com/room/1"})
        self.assertEqual(bridge.arguments, ("--port", "23456"))

    def test_chinese_pdd_types_are_normalized_for_interaction(self):
        capture = BarrageCapture("pinduoduo")
        self.assertEqual(capture._process_message({"type": "弹幕", "nickname": "用户", "content": "你好"}),
                         {"type": "comment", "nickname": "用户", "content": "你好"})
        self.assertEqual(capture._process_message({"type": "进入直播间", "nickname": "用户"})["type"], "enter")

    def test_cookie_default_is_user_data_not_source_tree(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"LOCALAPPDATA": root}):
            client = PinduoduoDanmu()
            self.assertTrue(Path(client.cookies_path).is_relative_to(Path(root)))

    def test_sync_websockets_broadcast_is_supported(self):
        client = PinduoduoDanmu()
        client.clients.add(object())
        with mock.patch("recovered.assets.ws_danmu_capture.pdd.pinduoduo_danmu.websockets.broadcast",
                        return_value=None) as broadcast:
            asyncio.run(client.broadcast({"type": "comment"}))
        broadcast.assert_called_once()

    def test_truncated_or_oversized_compressed_frames_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "超过"):
            _gzip_decompress_limited(gzip.compress(b"x" * 4096), limit=128)
        client = PinduoduoDanmu()
        with mock.patch("builtins.print") as output:
            asyncio.run(client.on_frame_received(b"\0" * 12 + struct.pack(">I", 1024) + b"short"))
        self.assertTrue(any("长度无效" in str(call) for call in output.call_args_list))

    def test_digital_live_manager_selects_owned_pdd_bridge(self):
        manager = DigitalLiveManager({}, Path.cwd())
        manager._runtime = object()
        capture = mock.MagicMock()
        capture.__iter__.return_value = iter(())
        with mock.patch("recovered.digital_live_manager.PinduoduoDanmuBridge", return_value=capture) as bridge:
            self.assertTrue(manager.start_danmu("https://live.pinduoduo.com/room/1", "pinduoduo"))
            manager._danmu_worker.join(timeout=2)
            self.assertTrue(manager.stop_danmu())
        bridge.assert_called_once_with("https://live.pinduoduo.com/room/1")
        capture.start.assert_called_once_with()
        capture.stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
