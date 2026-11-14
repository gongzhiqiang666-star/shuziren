import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recovered.main_plugins import PluginInstallerService


class PluginIntegrityTests(unittest.TestCase):
    def _service_and_installer(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        installer = root / "assets" / "plugin" / "tools" / "setup.exe"
        installer.parent.mkdir(parents=True)
        installer.write_bytes(b"trusted installer")
        service = PluginInstallerService(root)
        return temporary, service, installer

    def _write_manifest(self, service, installer, *, digest=None, size=None):
        relative = installer.relative_to(Path(service.plugin_dir)).as_posix()
        payload = {"version": 1, "files": {relative: {
            "sha256": digest or hashlib.sha256(installer.read_bytes()).hexdigest(),
            "size": installer.stat().st_size if size is None else size,
        }}}
        (Path(service.plugin_dir) / "installer-manifest.json").write_text(
            json.dumps(payload), encoding="utf-8")

    def test_verified_installer_passes(self):
        temporary, service, installer = self._service_and_installer()
        with temporary:
            self._write_manifest(service, installer)
            result = service._verify_bundled_installer(installer)
            self.assertEqual(result["relative_path"], "tools/setup.exe")

    def test_missing_unknown_or_changed_installer_is_rejected(self):
        temporary, service, installer = self._service_and_installer()
        with temporary:
            with self.assertRaisesRegex(FileNotFoundError, "完整性清单"):
                service._verify_bundled_installer(installer)
            (Path(service.plugin_dir) / "installer-manifest.json").write_text(
                json.dumps({"version": 1, "files": {}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "未登记"):
                service._verify_bundled_installer(installer)
            self._write_manifest(service, installer)
            installer.write_bytes(b"tampered installer")
            with self.assertRaisesRegex(ValueError, "大小校验失败|SHA-256"):
                service._verify_bundled_installer(installer)

    def test_installer_outside_plugin_root_is_rejected(self):
        temporary, service, installer = self._service_and_installer()
        with temporary:
            outside = Path(temporary.name) / "outside.exe"
            outside.write_bytes(b"outside")
            with self.assertRaisesRegex(ValueError, "受信任"):
                service._verify_bundled_installer(outside)

    @mock.patch("recovered.main_plugins.sys.platform", "win32")
    def test_elevation_happens_only_after_integrity_check(self):
        temporary, service, installer = self._service_and_installer()
        with temporary, mock.patch.object(service, "_verify_bundled_installer", side_effect=ValueError("bad")), \
                mock.patch("recovered.main_plugins.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "bad"):
                service._run_elevated_process(installer)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
