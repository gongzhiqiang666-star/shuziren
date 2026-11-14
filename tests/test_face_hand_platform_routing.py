import time
import unittest
from unittest.mock import patch

from recovered.face_hand_live_manager import FaceHandLiveManager


class _Capture:
    def __init__(self):
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1

    def __iter__(self):
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
                manager._interaction_llm_executor.shutdown(wait=True)

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
        manager._interaction_llm_executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
