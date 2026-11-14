import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from recovered.main import Api


class MainLlmConfigTests(unittest.TestCase):
    def setUp(self):
        self.responses = [(200, "好")]
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                status, content = owner.responses.pop(0)
                body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop_server)
        self.config = {
            "vendor": "deepseek", "model": "deepseek-chat", "api_key": "secret-sentinel",
            "endpoint": f"http://127.0.0.1:{self.server.server_port}/chat/completions", "timeout": 2,
        }

    def stop_server(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def api(self):
        api = Api.__new__(Api); api.config = {}
        api._digital_live_manager = SimpleNamespace(config=None)
        api._record_live_manager = SimpleNamespace(config=None)
        api._face_hand_live_manager = SimpleNamespace(config=None)
        api._save_user_config = lambda value: setattr(api, "saved", value)
        return api

    def test_deepseek_config_saves_and_successful_probe_is_reported(self):
        api = self.api()
        self.assertEqual(api.save_llm_config(dict(self.config))["status"], "success")
        self.assertEqual(api.saved, {"llm_config": self.config})
        self.assertEqual(api.test_llm_availability(self.config), {
            "status": "success", "message": "大模型服务正常", "is_available": True,
            "is_recommended_provider": True, "provider": "deepseek",
        })

    def test_http_failure_and_connection_failure_are_not_false_success(self):
        api = self.api(); self.responses = [(401, "secret-sentinel")]
        failed = api.test_llm_availability(self.config)
        self.assertFalse(failed["is_available"])
        self.assertNotIn("secret-sentinel", failed["message"])
        unavailable = api.test_llm_availability({**self.config, "endpoint": "http://127.0.0.1:1/chat/completions"})
        self.assertFalse(unavailable["is_available"])

    def test_remote_plain_http_and_embedded_query_are_rejected(self):
        api = self.api()
        for endpoint in ("http://api.deepseek.com/chat/completions", "https://api.deepseek.com/chat/completions?key=secret-sentinel"):
            result = api.test_llm_availability({**self.config, "endpoint": endpoint})
            self.assertFalse(result["is_available"])
            self.assertNotIn("secret-sentinel", result["message"])


if __name__ == "__main__":
    unittest.main()
