import queue
import types
import unittest
from unittest.mock import patch

from recovered.auto_live_action import LiveControlAPI


class Capture:
    def rect(self):
        return (100, 200, 500, 400)


class OCR:
    def __init__(self, values):
        self.values = values

    def recognize_text(self, _image):
        return self.values


class AutoLiveActionSafetyTests(unittest.TestCase):
    def api(self, ocr):
        api = object.__new__(LiveControlAPI)
        api.is_positioning = True
        api.capture_cmd_queue = queue.Queue()
        api.capture_res_queue = queue.Queue()
        api.capture_res_queue.put(object())
        api.capture_window = Capture()
        api.capture_window_thread = object()
        api.ocr_processor = OCR(ocr)
        api.positions = {}
        api.live_action = None
        api.control_running = False
        api.is_danmu_running = False
        api.config = {"danmu_list": [], "allow_unsafe_coordinate_fallback": False}
        return api

    def test_missing_input_hint_fails_closed_without_guessed_click(self):
        api = self.api([{"text": "发送", "box": [[300, 50], [340, 50], [340, 80], [300, 80]]}])
        result = api.confirm_position()
        self.assertFalse(result["success"])
        self.assertIn("避免误触", result["message"])
        self.assertIsNone(api.live_action)
        self.assertFalse(api.is_positioning)
        self.assertEqual(api.capture_cmd_queue.get_nowait(), "capture")
        self.assertEqual(api.capture_cmd_queue.get_nowait(), "stop")

    def test_recognized_input_uses_box_center_and_starts_control(self):
        api = self.api([{"text": "说点什么", "box": [[20, 30], [180, 30], [180, 70], [20, 70]]}])
        with patch.object(api, "start_control", return_value={"success": True}) as start:
            result = api.confirm_position()
        self.assertTrue(result["success"])
        self.assertEqual(api.positions["target"], (200, 250))
        self.assertEqual(api.live_action.target_coords, (200, 250))
        start.assert_called_once_with()

    def test_legacy_coordinate_fallback_requires_explicit_opt_in(self):
        api = self.api([])
        api.config["allow_unsafe_coordinate_fallback"] = True
        with patch.object(api, "start_control", return_value={"success": True}):
            result = api.confirm_position()
        self.assertTrue(result["success"])
        self.assertEqual(api.positions["target"], (470, 300))


if __name__ == "__main__":
    unittest.main()
