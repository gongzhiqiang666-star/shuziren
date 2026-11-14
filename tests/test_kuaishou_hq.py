import unittest
from unittest.mock import Mock, patch
import sys
from types import SimpleNamespace

from recovered.kuaishou_v2.hq import Tool


class KuaishouRoomToolTests(unittest.TestCase):
    def room_tool(self):
        tool = object.__new__(Tool)
        tool.liveUrl = "https://live.kuaishou.com/u/demo/"
        tool.cookie = "cookie-value"
        return tool

    def test_missing_ocr_provider_fails_explicitly_without_attribute_error(self):
        tool = object.__new__(Tool)
        tool.det = None
        with self.assertRaisesRegex(RuntimeError, "独立平台工具环境"):
            tool.slide_match(b"target", b"background")

    def test_slide_match_uses_single_provider_boundary(self):
        tool = object.__new__(Tool)
        tool.det = Mock()
        tool.det.slide_match.return_value = {"target": [123, 0]}
        result = tool.slide_match(b"target", b"background")
        self.assertEqual(result, {"target": [123, 0]})
        tool.det.slide_match.assert_called_once_with(
            b"target", b"background", simple_target=True)

    def test_captcha_compatible_provider_does_not_require_simple_target_keyword(self):
        tool = object.__new__(Tool)
        tool.det = Mock()
        tool.det.slide_match.return_value = {"target": [123, 0]}
        result = tool._slide_match(b"target", b"background", False)
        self.assertEqual(result, {"target": [123, 0]})
        tool.det.slide_match.assert_called_once_with(b"target", b"background")

    def test_room_id_has_timeout_and_validates_response(self):
        calls = []

        class Response:
            status_code = 200

            def json(self):
                return {"data": {"liveStream": {"liveStreamId": "stream-1"}}}

        requests = SimpleNamespace(get=lambda url, **kwargs: (calls.append((url, kwargs)) or Response()))
        with patch.dict(sys.modules, {"requests": requests}):
            self.assertEqual(self.room_tool().getLiveRoomId(), "stream-1")
        self.assertEqual(calls[0][1]["timeout"], 10)
        self.assertEqual(calls[0][1]["params"], {"principalId": "demo"})

    def test_room_id_network_and_payload_failures_are_stable(self):
        def failed(*_args, **_kwargs):
            raise OSError("secret upstream detail")

        with patch.dict(sys.modules, {"requests": SimpleNamespace(get=failed)}):
            with self.assertRaisesRegex(RuntimeError, "地址、网络或登录状态") as raised:
                self.room_tool().getLiveRoomId()
        self.assertNotIn("secret upstream detail", str(raised.exception))

        response = SimpleNamespace(status_code=200, json=lambda: {"data": {"liveStream": {}}})
        with patch.dict(sys.modules, {"requests": SimpleNamespace(get=lambda *_args, **_kwargs: response)}):
            with self.assertRaisesRegex(RuntimeError, "地址、网络或登录状态"):
                self.room_tool().getLiveRoomId()


if __name__ == "__main__":
    unittest.main()
