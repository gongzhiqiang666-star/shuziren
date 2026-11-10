"""Archive fidelity stays strict while explicitly scoped runtime inputs are audited."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import build_v122_proof, verify_v122_package
from scripts.v122_package_policy import POLICY, REQUIRED_RUNTIME_FILES, RUNTIME_PREFIX, derived_reason


class IntegrityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.records = []
        for relative in REQUIRED_RUNTIME_FILES:
            self.add(RUNTIME_PREFIX + relative, b"original-input")
        self.add(RUNTIME_PREFIX + "_internal/assets/pretrained_models/image_infer_v2/unet_v2.onnx", b"weights")
        self.add("proof/scripts/main.py", b"proof-code")
        self.write_manifest()

    def add(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.records.append({"path": relative, "bytes": len(content),
                             "sha256": hashlib.sha256(content).hexdigest()})
        return path

    def write_manifest(self, records=None, **metadata):
        path = self.root / "proof/manifests/package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"format": 1, "files": self.records if records is None else records,
                                    **metadata}), encoding="utf-8")

    def test_exact_archive_and_runtime_accept_unchanged_inputs(self):
        for profile in ("archive", "runtime"):
            result = verify_v122_package.verify(self.root, profile)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["checked"], len(self.records))
            self.assertEqual(result["derived_data"], [])

    def test_isolated_cli_loads_own_policy_and_keeps_manifest_unchanged(self):
        manifest = self.root / "proof/manifests/package.json"
        before = manifest.read_bytes()
        report = self.root / "reports/health.json"
        process = subprocess.run([sys.executable, "-I", "-X", "utf8", verify_v122_package.__file__,
                                  "--root", str(self.root), "--profile", "runtime", "--output", str(report)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(report.read_bytes())
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["profile"], "runtime")
        self.assertEqual(before, manifest.read_bytes())

    def test_derived_changes_fail_archive_and_are_visible_in_runtime_report(self):
        names = ["_internal/env/Lib/site-packages/x/__pycache__/m.cpython-310.pyc",
                 "_internal/env/Lib/site-packages/x/__pycache__/m.fn.py310.1.nbc",
                 "_internal/temp/audio_cache_index.txt",
                 "_internal/assets/pretrained_models/image_infer_v2/trt_cache_full/gpu_info.txt"]
        for name in names:
            self.add(RUNTIME_PREFIX + name, b"initial")
        engine = self.add(RUNTIME_PREFIX + "_internal/assets/pretrained_models/image_infer_v2/trt_cache_full/local.engine", b"cache")
        self.write_manifest()
        for name in names:
            (self.root / (RUNTIME_PREFIX + name)).write_bytes(b"regenerated")
        engine.unlink()
        strict = verify_v122_package.verify(self.root)
        self.assertEqual(strict["status"], "failed")
        self.assertEqual(len(strict["changed"]), 4)
        self.assertEqual(len(strict["missing"]), 1)
        health = verify_v122_package.verify(self.root, "runtime")
        self.assertEqual(health["status"], "passed")
        self.assertEqual(len(health["derived_data"]), 5)
        self.assertTrue(all(not item["hash_verified"] for item in health["derived_data"]))
        self.assertIn("generated data unverified", health["scope"])

    def test_source_config_models_and_program_changes_always_fail(self):
        relatives = [RUNTIME_PREFIX + "_internal/start.py", RUNTIME_PREFIX + "_internal/config/config.yaml",
                     RUNTIME_PREFIX + "_internal/env/python.exe",
                     RUNTIME_PREFIX + "_internal/assets/pretrained_models/image_infer_v2/unet_v2.onnx",
                     "proof/scripts/main.py"]
        for relative in relatives:
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                # Same length, so SHA verification must catch the modification.
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                for profile in ("archive", "runtime"):
                    result = verify_v122_package.verify(self.root, profile)
                    self.assertEqual(result["status"], "failed")
                    self.assertIn(relative, result["changed"])
                path.write_bytes(original)

    def test_missing_required_program_config_and_weight_fail_both_profiles(self):
        relatives = [RUNTIME_PREFIX + relative for relative in REQUIRED_RUNTIME_FILES]
        relatives.append(RUNTIME_PREFIX + "_internal/assets/pretrained_models/image_infer_v2/unet_v2.onnx")
        for relative in relatives:
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.unlink()
                for profile in ("archive", "runtime"):
                    result = verify_v122_package.verify(self.root, profile)
                    self.assertEqual(result["status"], "failed")
                    self.assertIn(relative, result["missing"])
                path.write_bytes(original)

    def test_unlisted_required_runtime_record_cannot_pass_runtime_health(self):
        self.write_manifest(self.records[1:])
        result = verify_v122_package.verify(self.root, "runtime")
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("required runtime record absent" in item for item in result["errors"]))

    def test_malformed_empty_duplicate_or_escaping_manifest_fails(self):
        malformed = [[], [{"path": "../outside", "bytes": 1, "sha256": "a"*64}],
                     [{"path": "C:/outside", "bytes": 1, "sha256": "a"*64}],
                     [{"path": "x\\..\\outside", "bytes": 1, "sha256": "a"*64}],
                     [{"path": "x", "bytes": True, "sha256": "a"*64}],
                     [{"path": "x", "bytes": 1, "sha256": "not-a-hash"}],
                     self.records + [copy.deepcopy(self.records[0])], [None]]
        for records in malformed:
            with self.subTest(records=records):
                self.write_manifest(records)
                for profile in ("archive", "runtime"):
                    self.assertEqual(verify_v122_package.verify(self.root, profile)["status"], "failed")

    def test_scope_is_not_inferred_from_arbitrary_cache_names(self):
        immutable = ["proof/__pycache__/main.pyc", RUNTIME_PREFIX + "_internal/temp/config.yaml",
                     RUNTIME_PREFIX + "_internal/env/__pycache__/injected.py",
                     RUNTIME_PREFIX + "_internal/assets/pretrained_models/required.engine",
                     RUNTIME_PREFIX + "_internal/assets/pretrained_models/image_infer_v2/trt_cache_full/unet.onnx"]
        self.assertTrue(all(derived_reason(name) is None for name in immutable))
        for name in immutable:
            path = self.add(name, b"original")
            path.write_bytes(b"modified")
        self.write_manifest()
        result = verify_v122_package.verify(self.root, "runtime")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(set(result["changed"]), set(immutable))

    def test_format_two_rejects_unknown_policy_or_immutable_cache_records(self):
        self.write_manifest(format=2, runtime_policy="unknown")
        self.assertEqual(verify_v122_package.verify(self.root)["status"], "failed")
        self.add(RUNTIME_PREFIX + "_internal/env/__pycache__/x.pyc", b"generated")
        self.write_manifest(format=2, runtime_policy=POLICY)
        self.assertEqual(verify_v122_package.verify(self.root)["status"], "failed")

    def test_new_package_omits_generated_data_and_stays_strict_after_cache_creation(self):
        source = self.root / "source"
        proof = self.root / "proof-source"
        source.mkdir(); proof.mkdir()
        for name, data in [("_internal/start.py", b"code"),
                           ("_internal/env/__pycache__/m.pyc", b"compiled"),
                           ("_internal/temp/audio_cache_index.txt", b"index"),
                           ("_internal/._start.py", b"metadata")]:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        (proof / "tool.py").write_text("tool", encoding="utf-8")
        destination = self.root / "new-package"
        manifest = build_v122_proof.build_package(source, proof, destination)
        self.assertEqual(manifest["format"], 2)
        self.assertEqual(manifest["runtime_policy"], POLICY)
        self.assertEqual(sum(manifest["omitted_generated_files"].values()), 3)
        self.assertEqual(verify_v122_package.verify(destination)["status"], "passed")
        cache = destination / (RUNTIME_PREFIX + "_internal/env/__pycache__/m.pyc")
        self.assertFalse(cache.exists())
        cache.parent.mkdir(parents=True); cache.write_bytes(b"new compiled data")
        self.assertEqual(verify_v122_package.verify(destination)["status"], "passed")
        (destination / (RUNTIME_PREFIX + "_internal/start.py")).write_bytes(b"bad!")
        self.assertEqual(verify_v122_package.verify(destination)["status"], "failed")

    def test_refresh_legacy_archive_does_not_convert_or_rehash_runtime(self):
        repository = Path(__file__).resolve().parents[1]
        release = self.root / "legacy-release"
        runtime = release / "runtime/yunchuang_v122"
        runtime.mkdir(parents=True)
        item = runtime / "_internal/start.py"
        item.parent.mkdir(); item.write_bytes(b"legacy code")
        record = {"path": RUNTIME_PREFIX + "_internal/start.py", "bytes": len(b"legacy code"),
                  "sha256": hashlib.sha256(b"legacy code").hexdigest()}
        manifest_path = release / "proof/manifests/package.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps({"format": 1, "files": [record]}), encoding="utf-8")
        item.write_bytes(b"changed code")
        result = build_v122_proof.refresh_release_tools(repository, release)
        self.assertEqual(result["format"], 1)
        self.assertEqual(next(row for row in result["files"] if row["path"] == record["path"]), record)
        self.assertEqual(verify_v122_package.verify(release)["changed"], [record["path"]])

    def test_builder_rejects_empty_inputs_and_nested_destination(self):
        source = self.root / "empty-source"
        proof = self.root / "empty-proof"
        source.mkdir(); proof.mkdir()
        with self.assertRaisesRegex(build_v122_proof.BuildError, "no immutable files"):
            build_v122_proof.build_package(source, proof, self.root / "empty-package")
        (source / "source.py").write_text("source", encoding="utf-8")
        with self.assertRaisesRegex(build_v122_proof.BuildError, "overlap"):
            build_v122_proof.build_package(source, proof, source / "nested-package")


if __name__ == "__main__":
    unittest.main()
