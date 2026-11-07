import copy
import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
