import unittest
from unittest.mock import Mock

from recovered.kuaishou_v2.hq import Tool


class KuaishouRoomToolTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
