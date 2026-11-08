import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

try:
    from scripts import v122_proof
except ImportError:
    v122_proof = None
try:
    from scripts import v122_proof_server
except ImportError:
    v122_proof_server = None


PROJECT = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def test_runtime_map_names_every_required_stage(self):
        path = PROJECT / "docs/evidence/v122-runtime-map.md"
        self.assertTrue(path.is_file())
        source = path.read_text(encoding="utf-8")
        for stage in (
            "environment",
            "avatar_preprocess",
            "voice_generate",
            "avatar_drive",
            "mp4_output",
        ):
            with self.subTest(stage=stage):
                self.assertIn(f"`{stage}`", source)
        for field in ("入口", "输入", "输出", "证据", "置信状态"):
            with self.subTest(field=field):
                self.assertIn(field, source)


class ConfigTests(unittest.TestCase):
    def test_example_is_valid_and_selects_standard_environment_for_3060(self):
        self.assertIsNotNone(v122_proof)
        config = v122_proof.load_config(PROJECT / "config/v122-proof.example.json")
        v122_proof.validate_config(config)
        self.assertEqual(v122_proof.select_environment("NVIDIA GeForce RTX 3060"), "env")

    def test_rejects_unknown_sensitive_and_escaping_values(self):
        self.assertIsNotNone(v122_proof)
        base = v122_proof.example_config()
        for mutate in (
            lambda data: data.update({"unexpected": True}),
            lambda data: data.update({"api_key": "secret"}),
            lambda data: data["paths"].update({"runs": "../outside"}),
            lambda data: data["paths"].update({"runs": "C:/outside"}),
        ):
            data = json.loads(json.dumps(base))
            mutate(data)
            with self.assertRaises(v122_proof.ProofError):
                v122_proof.validate_config(data)

    def test_resolve_package_path_stays_beneath_root(self):
        self.assertIsNotNone(v122_proof)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(v122_proof.resolve_package_path(root, "runs/demo"), (root / "runs/demo").resolve())
            with self.assertRaises(v122_proof.ProofError):
                v122_proof.resolve_package_path(root, "../escape")


class WebWizardTests(unittest.TestCase):
    def test_wizard_contains_recording_fallback_progress_and_result_controls(self):
        web = PROJECT / "scripts/v122-proof/web"
        html = (web / "index.html").read_text(encoding="utf-8")
        script = (web / "app.js").read_text(encoding="utf-8")
        for text in (
            "开始摄像头录制", "选择已有视频", "开始麦克风录音", "选择已有WAV",
            "检查并开始生成", "删除本次素材", "参考录音逐字稿", "新验证话术",
        ):
            self.assertIn(text, html)
        for token in ("getUserMedia", "MediaRecorder", "__v122Test", "/api/state", "/api/generate"):
            self.assertIn(token, script)
        combined = (html + script).lower()
        for forbidden in ("https://", "http://", "cdn", "analytics", "websocket"):
            self.assertNotIn(forbidden, combined)

    def test_recording_transitions_are_explicit(self):
        script = (PROJECT / "scripts/v122-proof/web/app.js").read_text(encoding="utf-8")
        for state in ("idle", "countdown", "recording", "preview", "confirmed", "fallback"):
            self.assertIn(f"'{state}'", script)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(v122_proof_server)
        self.temp = tempfile.TemporaryDirectory()
        web = PROJECT / "scripts/v122-proof/web"
        self.server = v122_proof_server.create_server(Path(self.temp.name), web, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown(); self.server.server_close()
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def request(self, path, method="GET", body=None, content_type="application/json"):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"Content-Type": content_type, "X-V122-Proof": "1",
                                                  "Origin": self.base})
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())

    def test_state_upload_confirm_and_text_flow(self):
        status, state = self.request("/api/state")
        self.assertEqual(status, 200); self.assertEqual(state["bind"], "127.0.0.1")
        self.request("/api/materials/person", "POST", b"video", "video/webm")
        self.request("/api/materials/voice", "POST", b"audio", "audio/webm")
        self.request("/api/materials/person/confirm", "POST")
        self.request("/api/materials/voice/confirm", "POST")
        self.request("/api/text", "PUT", {"reference_transcript": "参考文字", "new_script": "新话术"})
        _, state = self.request("/api/state")
        self.assertTrue(state["materials"]["person"]["confirmed"])
        self.assertEqual(state["text"]["new_script"], "新话术")

    def test_generate_rejects_incomplete_and_delete_requires_confirmation(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/generate", "POST")
        self.assertEqual(caught.exception.code, 409)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/current-run", "DELETE", {"confirm": False})
        self.assertEqual(caught.exception.code, 400)
        status, _ = self.request("/api/current-run", "DELETE", {"confirm": True})
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
