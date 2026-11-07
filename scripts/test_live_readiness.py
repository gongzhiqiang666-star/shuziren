import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import live_readiness as readiness


PROJECT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_example_manifest_is_valid_and_secret_free(self):
        manifest = readiness.load_manifest(PROJECT / "config/live-readiness.example.json")
        readiness.validate_manifest(manifest)
        serialized = json.dumps(manifest).lower()
        for forbidden in ("password", "secret", "cookie", "session", "access_token"):
            self.assertNotIn(forbidden, serialized)

    def test_unknown_keys_are_rejected_without_echoing_values(self):
        manifest = readiness.example_manifest()
        manifest["credentials"] = {"cookie": "private-cookie-value"}
        with self.assertRaises(readiness.ReadinessError) as caught:
            readiness.validate_manifest(manifest)
        self.assertIn("unknown key", str(caught.exception))
        self.assertNotIn("private-cookie-value", str(caught.exception))

    def test_sensitive_keys_are_rejected_at_any_depth(self):
        manifest = readiness.example_manifest()
        manifest["tts"]["api_key"] = "private-key-value"
        with self.assertRaises(readiness.ReadinessError) as caught:
            readiness.validate_manifest(manifest)
        self.assertIn("sensitive key", str(caught.exception))
        self.assertNotIn("private-key-value", str(caught.exception))

    def test_exactly_one_tts_and_avatar_are_required(self):
        for field in ("tts", "avatar"):
            manifest = readiness.example_manifest()
            manifest[field] = [copy.deepcopy(manifest[field]), copy.deepcopy(manifest[field])]
            with self.subTest(field=field), self.assertRaisesRegex(readiness.ReadinessError, "exactly one"):
                readiness.validate_manifest(manifest)

    def test_output_is_fixed_to_first_proof_limits(self):
        invalid_values = (("width", 319), ("height", 2161), ("fps", 30))
        for field, value in invalid_values:
            manifest = readiness.example_manifest()
            manifest["output"][field] = value
            with self.subTest(field=field), self.assertRaises(readiness.ReadinessError):
                readiness.validate_manifest(manifest)

    def test_platform_may_be_explicitly_blocked(self):
        manifest = readiness.example_manifest()
        manifest["platform"] = {"required_for_this_run": False, "approval_status": "blocked"}
        readiness.validate_manifest(manifest)

    def test_inventory_reports_hashes_without_paths_or_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.bin"
            model.write_bytes(b"private model fixture")
            report = readiness.inventory_paths({"tts.model_dir": model})
            serialized = json.dumps(report)
            self.assertEqual(report[0]["sha256"], hashlib.sha256(model.read_bytes()).hexdigest())
            self.assertNotIn(str(root), serialized)
            self.assertNotIn("private model fixture", serialized)

    def test_directory_inventory_is_stable_and_ignores_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_dir = root / "model"
            model_dir.mkdir()
            (model_dir / "b.bin").write_bytes(b"b")
            (model_dir / "a.bin").write_bytes(b"a")
            try:
                (model_dir / "outside-link").symlink_to(root / "outside")
            except OSError:
                pass
            first = readiness.inventory_paths({"avatar.model_dir": model_dir})[0]
            second = readiness.inventory_paths({"avatar.model_dir": model_dir})[0]
            self.assertEqual(first, second)
            self.assertEqual(first["files"], 2)
            self.assertEqual(first["bytes"], 2)

    def test_missing_inventory_has_no_fake_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            report = readiness.inventory_paths({"runtime.root": missing})[0]
            self.assertEqual(report, {
                "label": "runtime.root", "kind": "missing", "present": False,
                "bytes": 0, "files": 0, "sha256": None,
            })


class GateTests(unittest.TestCase):
    def test_obs_gate_requires_audio_and_video_evidence(self):
        gate = {"status": "passed", "evidence": {"video": "obs-recording", "audio": ""}}
        with self.assertRaisesRegex(readiness.ReadinessError, "audio"):
            readiness.validate_gate("obs", gate)

    def test_generation_gate_requires_new_text_and_wav_hash(self):
        gate = {"status": "passed", "evidence": {"new_text": True, "wav_sha256": "short"}}
        with self.assertRaisesRegex(readiness.ReadinessError, "wav_sha256"):
            readiness.validate_gate("generation", gate)

    def test_platform_gate_requires_approval_and_viewer_evidence(self):
        gate = {"status": "passed", "evidence": {"approved": False, "viewer_record": "recording"}}
        with self.assertRaisesRegex(readiness.ReadinessError, "approved"):
            readiness.validate_gate("platform", gate)

    def test_local_conclusion_stops_at_obs_when_platform_is_blocked(self):
        gates = readiness.empty_gates()
        gates["install"] = {"status": "passed", "evidence": {"operator_record": "install"}}
        gates["generation"] = {"status": "passed", "evidence": {
            "new_text": True, "wav_sha256": "a" * 64,
        }}
        gates["obs"] = {"status": "passed", "evidence": {
            "video": "obs-recording", "audio": "obs-recording",
        }}
        self.assertEqual(readiness.conclusion(gates), "local_chain_passed_platform_blocked")

    def test_init_run_creates_all_gate_files_without_copying_manifest_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            required = {
                "runtime": {"root": assets, "python": assets / "python.exe"},
                "tts": {"model_dir": assets, "reference_audio": assets / "voice.wav", "reference_text": assets / "voice.txt"},
                "avatar": {"model_dir": assets, "character_dir": assets},
            }
            for section in required.values():
                for path in section.values():
                    path = Path(path)
                    if path.suffix and not path.exists():
                        path.write_bytes(b"fixture")
            manifest = readiness.example_manifest()
            for section, fields in required.items():
                for field, path in fields.items():
                    manifest[section][field] = "C:\\fixture\\" + (Path(path).name or "assets")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with mock.patch.object(readiness, "manifest_paths", return_value={"fixture": assets}):
                run_dir = readiness.init_run(manifest_path, root / "runs", run_id="20261107T120000Z")
            self.assertEqual(run_dir.name, "20261107T120000Z")
            self.assertTrue((run_dir / "metadata.json").is_file())
            for gate in readiness.GATE_NAMES:
                payload = json.loads((run_dir / "gates" / f"{gate}.json").read_text())
                self.assertEqual(payload["status"], "blocked")
            self.assertNotIn(str(root), (run_dir / "metadata.json").read_text())


class WindowsScriptTests(unittest.TestCase):
    def test_windows_preflight_has_required_checks_and_no_secret_dump(self):
        source = (PROJECT / "scripts/check-live-readiness.ps1").read_text(encoding="utf-8")
        for required in ("nvidia-smi", "Win32_SoundDevice", "obs64.exe", "srs-live.bat", "obs-virtualcam-module64.dll", "check-assets"):
            self.assertIn(required, source)
        for forbidden in ("Get-ChildItem Env:", "TAOBAO_APP_SECRET", "TAOBAO_SESSION", "APP_TOKEN"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
