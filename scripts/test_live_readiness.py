import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
