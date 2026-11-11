import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.local_console_config import ConfigError, ConfigStore, preflight, validate
from scripts.v122_package_policy import REQUIRED_RUNTIME_FILES
from scripts.media_runtime import (
    INDEPENDENT, LEGACY_PYTHON, MANIFEST_NAME, MEDIA_FILES, MODEL_FILES, PROVIDER_FILES,
    runtime_fingerprints, runtime_python, verify_fingerprints,
)


class ConsoleConfigTests(unittest.TestCase):
    def test_media_inventory_survives_relocation_and_detects_changes(self):
        runtime = self.root / 'media'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(json.dumps(INDEPENDENT), encoding='utf-8')
        for name in (*MEDIA_FILES, *MODEL_FILES, *PROVIDER_FILES):
            file = runtime / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(name.encode())
        inventory = runtime_fingerprints(runtime)
        moved = runtime.rename(self.root / 'moved media')
        self.assertTrue(verify_fingerprints(moved, inventory)['verified'])
        (moved / MODEL_FILES[0]).write_bytes(b'changed')
        result = verify_fingerprints(moved, inventory)
        self.assertFalse(result['verified'])
        self.assertEqual(result['mismatches'], [MODEL_FILES[0]])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ConfigStore(self.root / "用户配置")

    def test_missing_config_does_not_create_or_start_anything(self):
        value = self.store.load()
        self.assertFalse(self.store.directory.exists())
        self.assertFalse(preflight(value)["ready"])

    def test_save_reopen_unicode_and_update(self):
        value = {"version": 1, "runtime_root": str(self.root / "人物资源"), "port": 5158}
        self.store.save(value)
        self.assertEqual(ConfigStore(self.store.directory).load(), value)
        value["port"] = 5160
        self.store.save(value)
        self.assertEqual(self.store.load(), value)
        self.assertEqual(list(self.store.directory.glob("*.tmp")), [])

    def test_corrupt_config_not_silently_reset(self):
        self.store.directory.mkdir()
        for content in ('{', '{"version":1,"version":1}', '[]'):
            self.store.path.write_text(content, encoding="utf-8")
            with self.assertRaises(ConfigError):
                self.store.load()
            self.assertEqual(self.store.path.read_text(encoding="utf-8"), content)

    def test_invalid_settings_rejected_without_overwriting(self):
        good = self.store.load()
        self.store.save(good)
        for update in ({"version": True}, {"port": True}, {"port": 1}, {"port": 65536},
                       {"runtime_root": "relative"}, {"runtime_root": "\x00"}, {"extra": 1}):
            with self.assertRaises(ConfigError):
                self.store.save({**good, **update})
            self.assertEqual(self.store.load(), good)

    def test_replace_failure_preserves_previous_config(self):
        old = self.store.load()
        self.store.save(old)
        with patch("scripts.local_console_config.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                self.store.save({**old, "port": 5160})
        self.assertEqual(self.store.load(), old)
        self.assertFalse(list(self.store.directory.glob("*.tmp")))

    def test_presence_does_not_claim_integrity_or_inference(self):
        runtime = self.root / "runtime"
        for relative in REQUIRED_RUNTIME_FILES:
            target = runtime / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"test fixture")
        config = {"version": 1, "runtime_root": str(runtime / "_internal"), "port": 5158}
        report = preflight(config)
        self.assertTrue(report["ready"])
        self.assertFalse(report["integrity_verified"])
        self.assertFalse(report["inference_verified"])
        target.unlink()
        self.assertFalse(preflight(config)["ready"])

    def test_independent_runtime_uses_venv_and_does_not_require_reference_app(self):
        runtime = self.root / 'media'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(json.dumps(INDEPENDENT), encoding='utf-8')
        for relative in (*MEDIA_FILES, *MODEL_FILES, *PROVIDER_FILES):
            target = runtime / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'test fixture')
        config = {'version':1, 'runtime_root':str(runtime), 'port':5158}
        self.assertTrue(preflight(config)['ready'])
        self.assertEqual(runtime_python(runtime), runtime / MEDIA_FILES[0])
        self.assertFalse(preflight(config)['inference_verified'])
        normalizers = [name for name in MODEL_FILES if '/wetext/' in name]
        self.assertEqual(len(normalizers), 4)
        tokenizer = '_internal/assets/pretrained_models/indextts/checkpoints/bpe.model'
        self.assertIn(tokenizer, MODEL_FILES)
        for name in [MODEL_FILES[0], tokenizer, *normalizers]:
            target = runtime / name
            target.unlink()
            report = preflight(config)
            self.assertFalse(report['ready'])
            self.assertEqual([item['path'] for item in report['checks'] if not item['present']], [name])
            target.write_bytes(b'test fixture')

    def test_independent_portable_interpreter_is_explicit_and_bounded(self):
        runtime = self.root / 'portable'
        runtime.mkdir()
        manifest = runtime / MANIFEST_NAME
        manifest.write_text(json.dumps({**INDEPENDENT, 'python':LEGACY_PYTHON}), encoding='utf-8')
        self.assertEqual(runtime_python(runtime), runtime / LEGACY_PYTHON)
        for invalid in ('../python.exe', ['python.exe']):
            manifest.write_text(json.dumps({**INDEPENDENT, 'python':invalid}), encoding='utf-8')
            with self.assertRaises(ValueError):
                runtime_python(runtime)


if __name__ == "__main__":
    unittest.main()
