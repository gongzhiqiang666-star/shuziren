import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts.local_console_config import ConfigError, ConfigStore, preflight, validate
from scripts.v122_package_policy import REQUIRED_RUNTIME_FILES
from scripts.media_runtime import (
    INDEPENDENT, LEGACY_PYTHON, MANIFEST_NAME, MEDIA_FILES, MODEL_FILES, PROVIDER_FILES,
    ORIGIN_VIDEO_FILES, inspect_runtime, pinned_requirements, runtime_fingerprints, runtime_python,
    software_report, verify_fingerprints, wheelhouse_report,
)


class ConsoleConfigTests(unittest.TestCase):
    def test_product_media_distributions_are_explicitly_pinned(self):
        locked = pinned_requirements()
        required = {
            'pandas': '2.2.3',
            'pycuda': '2024.1.2',
            'ultralytics': '8.3.70',
        }
        self.assertEqual({name: locked[name]['version'] for name in required}, required)
        platform = (Path(__file__).resolve().parents[1] / 'recovered' /
                    'requirements-kuaishou-ocr.txt').read_text(encoding='utf-8')
        self.assertIn('ddddocr==1.5.6', platform.splitlines())
        self.assertIn('opencv-python-headless==4.10.0.84', platform.splitlines())
        self.assertNotIn('ddddocr', locked)

    def test_software_report_separates_pins_from_dependency_health(self):
        requirements = self.root / 'requirements'
        requirements.mkdir()
        for filename, value in zip(
                ('requirements-core.txt', 'requirements-ai-cu118.txt', 'requirements-windows.txt'),
                ('numpy==1.24.0\n', 'torch==2.6.0+cu118\n', 'PyAudio==0.2.14\n')):
            (requirements / filename).write_text(value, encoding='utf-8')
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(json.dumps({**INDEPENDENT, 'python': LEGACY_PYTHON}),
                                             encoding='utf-8')
        python = runtime / LEGACY_PYTHON
        python.parent.mkdir(parents=True)
        python.write_bytes(b'python fixture')
        measured = {'python': '3.10.16', 'packages': {
            'numpy': '1.24.0', 'torch': '2.6.0+cu118', 'pyaudio': '0.2.14'}}
        with patch('scripts.media_runtime.subprocess.run', side_effect=[
                SimpleNamespace(returncode=0, stdout=json.dumps(measured), stderr=''),
                SimpleNamespace(returncode=1, stdout='missing indirect dependency', stderr=''),
        ]):
            report = software_report(runtime, requirements)
        self.assertTrue(report['versions_verified'])
        self.assertFalse(report['dependency_check_ok'])
        self.assertFalse(report['ready'])
        self.assertTrue(report['core_isolated'])
        self.assertIn('missing indirect dependency', report['dependency_check'])
        self.assertEqual(len(report['packages']), 3)

    def test_software_report_rejects_conflicting_tool_packages_in_core(self):
        requirements = self.root / 'requirements'
        requirements.mkdir()
        for filename, value in zip(
                ('requirements-core.txt', 'requirements-ai-cu118.txt', 'requirements-windows.txt'),
                ('numpy==1.24.0\n', 'torch==2.6.0+cu118\n', 'PyAudio==0.2.14\n')):
            (requirements / filename).write_text(value, encoding='utf-8')
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(json.dumps({**INDEPENDENT, 'python': LEGACY_PYTHON}),
                                             encoding='utf-8')
        python = runtime / LEGACY_PYTHON
        python.parent.mkdir(parents=True)
        python.write_bytes(b'python fixture')
        measured = {'python': '3.10.16', 'packages': {
            'numpy': '1.24.0', 'torch': '2.6.0+cu118', 'pyaudio': '0.2.14',
            'jax': '0.5.0', 'streamlit': '1.42.0'}}
        with patch('scripts.media_runtime.subprocess.run', side_effect=[
                SimpleNamespace(returncode=0, stdout=json.dumps(measured), stderr=''),
                SimpleNamespace(returncode=0, stdout='No broken requirements found.', stderr=''),
        ]):
            report = software_report(runtime, requirements)
        self.assertTrue(report['versions_verified'])
        self.assertTrue(report['dependency_check_ok'])
        self.assertFalse(report['core_isolated'])
        self.assertFalse(report['ready'])
        self.assertEqual(report['forbidden_core_packages'], [
            {'name': 'jax', 'installed': '0.5.0'},
            {'name': 'streamlit', 'installed': '1.42.0'},
        ])

    def test_requirement_lock_rejects_ranges_and_duplicates(self):
        requirements = self.root / 'requirements'
        requirements.mkdir()
        names = ('requirements-core.txt', 'requirements-ai-cu118.txt', 'requirements-windows.txt')
        for name in names:
            (requirements / name).write_text('# empty\n', encoding='utf-8')
        (requirements / names[0]).write_text('numpy>=1.24\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '精确锁定'):
            pinned_requirements(requirements)
        (requirements / names[0]).write_text('numpy==1.24.0\n', encoding='utf-8')
        (requirements / names[1]).write_text('NumPy==1.24.0\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '重复'):
            pinned_requirements(requirements)

    def test_wheelhouse_gate_is_offline_and_does_not_install(self):
        requirements = self.root / 'requirements'
        requirements.mkdir()
        for filename, value in zip(
                ('requirements-core.txt', 'requirements-ai-cu118.txt', 'requirements-windows.txt'),
                ('numpy==1.24.0\n', 'torch==2.6.0+cu118\n', 'PyAudio==0.2.14\n')):
            (requirements / filename).write_text(value, encoding='utf-8')
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(json.dumps({**INDEPENDENT, 'python': LEGACY_PYTHON}),
                                             encoding='utf-8')
        python = runtime / LEGACY_PYTHON
        python.parent.mkdir(parents=True)
        python.write_bytes(b'python fixture')
        wheelhouse = self.root / 'wheelhouse'
        wheelhouse.mkdir()

        def resolved(command, **kwargs):
            report = Path(command[command.index('--report') + 1])
            report.write_text(json.dumps({'install': [{}, {}, {}]}), encoding='utf-8')
            return SimpleNamespace(returncode=0, stdout='resolved', stderr='', args=command)

        with patch('scripts.media_runtime.subprocess.run', side_effect=resolved) as run:
            report = wheelhouse_report(runtime, wheelhouse, requirements)
        command = run.call_args.args[0]
        self.assertTrue(report['ready'])
        self.assertEqual(report['resolved_distributions'], 3)
        self.assertEqual(report['wheel_files'], 0)
        self.assertEqual(report['direct_present'], 0)
        self.assertEqual(report['direct_missing'], ['numpy', 'torch', 'PyAudio'])
        self.assertIn('--dry-run', command)
        self.assertIn('--no-index', command)
        self.assertIn('--ignore-installed', command)
        self.assertNotIn('--upgrade', command)
        self.assertEqual(command.count('-r'), 3)

    def test_wheelhouse_gate_reports_missing_offline_dependency(self):
        requirements = self.root / 'requirements'
        requirements.mkdir()
        for filename in ('requirements-core.txt', 'requirements-ai-cu118.txt', 'requirements-windows.txt'):
            (requirements / filename).write_text('' if filename != 'requirements-core.txt' else 'numpy==1.24.0\n',
                                                 encoding='utf-8')
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(json.dumps({**INDEPENDENT, 'python': LEGACY_PYTHON}),
                                             encoding='utf-8')
        python = runtime / LEGACY_PYTHON
        python.parent.mkdir(parents=True)
        python.write_bytes(b'python fixture')
        wheelhouse = self.root / 'wheelhouse'
        wheelhouse.mkdir()
        failed = SimpleNamespace(returncode=1, stdout='', stderr='No matching distribution', args=[])
        with patch('scripts.media_runtime.subprocess.run', return_value=failed):
            report = wheelhouse_report(runtime, wheelhouse, requirements)
        self.assertFalse(report['ready'])
        self.assertIsNone(report['resolved_distributions'])
        self.assertIn('No matching distribution', report['diagnostic'])

    def test_wheelhouse_gate_inventories_all_direct_pins_before_resolution(self):
        requirements = self.root / 'requirements'
        requirements.mkdir()
        for filename, value in zip(
                ('requirements-core.txt', 'requirements-ai-cu118.txt', 'requirements-windows.txt'),
                ('numpy==1.24.0\nPillow==10.4.0\n', 'torch==2.6.0+cu118\n', '')):
            (requirements / filename).write_text(value, encoding='utf-8')
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(
            json.dumps({**INDEPENDENT, 'python': LEGACY_PYTHON}), encoding='utf-8')
        python = runtime / LEGACY_PYTHON
        python.parent.mkdir(parents=True)
        python.write_bytes(b'python fixture')
        wheelhouse = self.root / 'wheelhouse'
        wheelhouse.mkdir()
        (wheelhouse / 'numpy-1.24.0-cp310-cp310-win_amd64.whl').write_bytes(b'fixture')
        (wheelhouse / 'torch-2.6.0+cu118-cp310-cp310-win_amd64.whl').write_bytes(b'fixture')
        failed = SimpleNamespace(returncode=1, stdout='', stderr='Pillow unavailable', args=[])
        with patch('scripts.media_runtime.subprocess.run', return_value=failed):
            report = wheelhouse_report(runtime, wheelhouse, requirements)
        self.assertEqual(report['wheel_files'], 2)
        self.assertEqual(report['direct_present'], 2)
        self.assertEqual(report['direct_missing'], ['Pillow'])
        self.assertEqual(report['direct_pins'][0]['candidates'],
                         ['numpy-1.24.0-cp310-cp310-win_amd64.whl'])
        self.assertFalse(report['ready'])

    def test_kuaishou_ocr_wheelhouse_uses_only_platform_lock(self):
        requirements = self.root / 'requirements'
        requirements.mkdir()
        (requirements / 'requirements-kuaishou-ocr.txt').write_text(
            'ddddocr==1.5.6\nopencv-python-headless==4.10.0.84\n', encoding='utf-8')
        runtime = self.root / 'runtime'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(
            json.dumps({**INDEPENDENT, 'python': LEGACY_PYTHON}), encoding='utf-8')
        python = runtime / LEGACY_PYTHON
        python.parent.mkdir(parents=True)
        python.write_bytes(b'python fixture')
        wheelhouse = self.root / 'wheelhouse'
        wheelhouse.mkdir()
        completed = SimpleNamespace(returncode=1, stdout='', stderr='ddddocr unavailable')
        with patch('scripts.media_runtime.subprocess.run', return_value=completed) as run:
            report = wheelhouse_report(runtime, wheelhouse, requirements, 'kuaishou-ocr')
        command = run.call_args.args[0]
        self.assertIn('--no-index', command)
        self.assertNotIn('--index-url', command)
        self.assertEqual(command.count('-r'), 1)
        self.assertIn(str(requirements / 'requirements-kuaishou-ocr.txt'), command)
        self.assertNotIn(str(requirements / 'requirements-core.txt'), command)
        self.assertEqual(report['profile'], 'kuaishou-ocr')
        self.assertEqual(report['requirements'], ['requirements-kuaishou-ocr.txt'])
        self.assertFalse(report['ready'])
        self.assertIsNone(report['resolved_distributions'])
        self.assertIn('ddddocr unavailable', report['diagnostic'])

    def test_media_inventory_survives_relocation_and_detects_changes(self):
        runtime = self.root / 'media'
        runtime.mkdir()
        (runtime / MANIFEST_NAME).write_text(json.dumps(INDEPENDENT), encoding='utf-8')
        for name in (*MEDIA_FILES, *MODEL_FILES, *PROVIDER_FILES):
            file = runtime / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(name.encode())
        inventory = runtime_fingerprints(runtime)
        missing = inspect_runtime(runtime, include_origin_video=True)
        self.assertFalse(missing['ready'])
        self.assertEqual([item['path'] for item in missing['checks'] if not item['present']],
                         list(ORIGIN_VIDEO_FILES))
        for name in ORIGIN_VIDEO_FILES:
            file = runtime / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(name.encode())
        video_inventory = runtime_fingerprints(runtime, include_origin_video=True)
        moved = runtime.rename(self.root / 'moved media')
        self.assertTrue(verify_fingerprints(moved, inventory)['verified'])
        self.assertTrue(verify_fingerprints(moved, video_inventory)['verified'])
        (moved / ORIGIN_VIDEO_FILES[0]).write_bytes(b'changed provider')
        self.assertEqual(verify_fingerprints(moved, video_inventory)['mismatches'], [ORIGIN_VIDEO_FILES[0]])
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
