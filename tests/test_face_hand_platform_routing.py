import time
import unittest
from unittest.mock import patch

from recovered.face_hand_live_manager import FaceHandLiveManager


class _Capture:
    def __init__(self, start_error=None, iterate_error=None):
        self.starts = 0
        self.stops = 0
        self.start_error = start_error
        self.iterate_error = iterate_error

    def start(self):
        self.starts += 1
        if self.start_error:
            raise self.start_error

    def stop(self):
        self.stops += 1

    def __iter__(self):
        if self.iterate_error:
            raise self.iterate_error
        return iter(())


class FaceHandPlatformRoutingTests(unittest.TestCase):
    def manager(self, platform):
        manager = FaceHandLiveManager({})
        manager._live_config = {
            "live_platform": platform,
            "live_url": "https://example/room",
        }
        return manager

    def wait_worker(self, manager):
        worker = manager._danmu_thread
        if worker is not None:
            worker.join(timeout=1)

    def close_manager(self, manager):
        manager.stop_danmu()
        manager._interaction_llm_executor.shutdown(wait=True)

    def test_kuaishou_and_pdd_aliases_use_owned_bridges(self):
        cases = (
            (" Kuaishou ", "recovered.danmu_bridge.KuaishouDanmuBridge"),
            ("PDD", "recovered.danmu_bridge.PinduoduoDanmuBridge"),
        )
        for platform, target in cases:
            with self.subTest(platform=platform):
                manager = self.manager(platform)
                capture = _Capture()
                with patch(target, return_value=capture) as bridge, patch(
                        "recovered.ws_capture.BarrageCapture") as generic:
                    self.assertTrue(manager.start_danmu())
                    self.wait_worker(manager)
                bridge.assert_called_once_with("https://example/room")
                generic.assert_not_called()
                self.close_manager(manager)

    def test_shopee_alias_uses_control_capture(self):
        manager = self.manager("shoppe")
        capture = _Capture()
        with patch(
                "recovered.shopee_control_capture.ShopeeControlDanmuCapture",
                return_value=capture) as bridge, patch(
                "recovered.ws_capture.BarrageCapture") as generic:
            self.assertTrue(manager.start_danmu())
            self.wait_worker(manager)
        bridge.assert_called_once_with()
        generic.assert_not_called()
        self.close_manager(manager)

    def test_natural_end_and_failure_release_for_restart(self):
        manager = self.manager("kuaishou")
        first = _Capture()
        second = _Capture(iterate_error=RuntimeError("capture ended"))
        with patch(
                "recovered.danmu_bridge.KuaishouDanmuBridge",
                side_effect=(first, second)):
            self.assertTrue(manager.start_danmu())
            self.wait_worker(manager)
            self.assertIsNone(manager._danmu_capturer)
            self.assertGreaterEqual(first.stops, 1)

            self.assertTrue(manager.start_danmu())
            self.wait_worker(manager)
            self.assertIsNone(manager._danmu_capturer)
            self.assertEqual(manager._last_error, "capture ended")
            self.assertGreaterEqual(second.stops, 1)
        self.close_manager(manager)

    def test_start_failure_stops_partial_capture(self):
        manager = self.manager("kuaishou")
        capture = _Capture(start_error=OSError("start failed"))
        with patch(
                "recovered.danmu_bridge.KuaishouDanmuBridge",
                return_value=capture):
            self.assertFalse(manager.start_danmu())
        self.assertEqual(manager._last_error, "start failed")
        self.assertEqual(capture.stops, 1)
        self.assertIsNone(manager._danmu_capturer)
        self.close_manager(manager)


if __name__ == "__main__":
    unittest.main()
