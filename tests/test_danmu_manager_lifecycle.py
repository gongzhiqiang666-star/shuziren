import time
import unittest
from unittest.mock import patch

from recovered.digital_live_manager import DigitalLiveManager


class FakeCapture:
    def __init__(self, messages=(), stop_error=None):
        self.messages = messages
        self.stop_error = stop_error
        self.starts = 0
        self.stops = 0

    def start(self): self.starts += 1
    def __iter__(self): return iter(self.messages)
    def stop(self):
        self.stops += 1
        if self.stop_error: raise self.stop_error


class RaisingCapture(FakeCapture):
    def __iter__(self):
        raise RuntimeError("capture disconnected")
        yield


class DanmuManagerLifecycleTests(unittest.TestCase):
    def manager(self):
        manager = DigitalLiveManager({"danmu_bridge_url": "ws://127.0.0.1:1"}, ".")
        manager._runtime = object()
        return manager

    def wait_stopped(self, manager):
        deadline = time.monotonic() + 2
        while manager.is_capturing and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(manager.is_capturing)

    def test_natural_end_and_error_release_capture_for_restart(self):
        manager = self.manager()
        first = FakeCapture()
        with patch("recovered.digital_live_manager.DanmuBridge", return_value=first):
            self.assertTrue(manager.start_danmu("unused"))
            self.wait_stopped(manager)
        self.assertGreaterEqual(first.stops, 1)

        failed = RaisingCapture()
        with patch("recovered.digital_live_manager.DanmuBridge", return_value=failed):
            self.assertTrue(manager.start_danmu("unused"))
            self.wait_stopped(manager)
        self.assertEqual(manager.last_error, "capture disconnected")
        self.assertGreaterEqual(failed.stops, 1)

    def test_stop_failure_is_reported_but_state_is_not_stuck(self):
        manager = self.manager()
        capture = FakeCapture(stop_error=OSError("close failed"))
        manager._danmu_capture = capture
        self.assertFalse(manager.stop_danmu())
        self.assertFalse(manager.is_capturing)
        self.assertIsNone(manager._danmu_worker)
        self.assertEqual(manager.last_error, "close failed")

    def test_platform_names_select_native_bridges_after_normalization(self):
        cases = (
            (" Kuaishou ", "recovered.digital_live_manager.KuaishouDanmuBridge"),
            ("PDD", "recovered.digital_live_manager.PinduoduoDanmuBridge"),
        )
        for platform, target in cases:
            with self.subTest(platform=platform):
                manager = self.manager()
                manager.config.pop("danmu_bridge_url")
                capture = FakeCapture()
                with patch(target, return_value=capture) as bridge, patch(
                        "recovered.digital_live_manager.OCRDanmuBridge") as ocr:
                    self.assertTrue(manager.start_danmu("https://example/room", platform))
                    self.wait_stopped(manager)
                bridge.assert_called_once_with("https://example/room")
                ocr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
