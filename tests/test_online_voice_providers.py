import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from recovered.cosyvoice_config import resolve_dashscope_endpoints
from recovered.minimax import _runtime, synthesize_speech_minimax


class OnlineVoiceProviderTests(unittest.TestCase):
    def test_minimax_requires_secure_credential_free_endpoint(self):
        for endpoint in (
            "http://api.minimax.io", "https://user:secret@api.minimax.io",
            "https://api.minimax.io?token=leak", "https://api.minimax.io#fragment",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError, "HTTPS"):
                _runtime({"api_host": endpoint})
        self.assertEqual(_runtime({"api_host": "api.minimax.io"})[:2],
                         ("https://api.minimax.io", True))

    def test_dashscope_requires_https_and_wss_endpoints(self):
        for config in (
            {"base_http_api_url": "http://dashscope.aliyuncs.com/api/v1"},
            {"base_websocket_api_url": "ws://dashscope.aliyuncs.com/api-ws/v1/inference"},
            {"base_http_api_url": "https://u:p@dashscope.aliyuncs.com/api/v1"},
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                resolve_dashscope_endpoints(config)
        resolved = resolve_dashscope_endpoints({"region": "international"})
        self.assertTrue(resolved["base_http_api_url"].startswith("https://dashscope-intl."))
        self.assertTrue(resolved["base_websocket_api_url"].startswith("wss://dashscope-intl."))

    def test_minimax_synthesis_writes_decoded_audio_without_logging_key(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"base_resp": {"status_code": 0}, "data": {"audio": "494433"}}

        captured = {}

        def post(url, **kwargs):
            captured.update(url=url, kwargs=kwargs)
            return Response()

        with tempfile.TemporaryDirectory() as directory, \
                patch.dict("sys.modules", {"requests": types.SimpleNamespace(post=post)}):
            result = Path(synthesize_speech_minimax(
                text="测试", voice_id="voice-1",
                minimax_config={"api_key": "secret-key", "cache_dir": directory},
                use_cache=False,
            ))
            self.assertEqual(result.read_bytes(), b"ID3")
            self.assertEqual(captured["url"], "https://api.minimax.io/v1/t2a_v2")
            self.assertEqual(captured["kwargs"]["headers"]["Authorization"], "Bearer secret-key")
            self.assertNotIn("secret-key", result.name)


if __name__ == "__main__":
    unittest.main()
