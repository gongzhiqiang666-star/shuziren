import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recovered.main import Api


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield self.content


class ObaIntegrityTests(unittest.TestCase):
    def _api(self, root, content=b"installer"):
        api = Api.__new__(Api)
        api.runtime_dir = Path(root)
        api.config = {
            "oba_live_installer_url": "https://downloads.example.com/oba.exe",
            "oba_live_installer_sha256": hashlib.sha256(content).hexdigest(),
        }
        return api

    def test_verified_download_is_atomically_published_and_reused(self):
        with tempfile.TemporaryDirectory() as root:
            content = b"verified oba installer"
            api = self._api(root, content)
            with mock.patch("requests.get", return_value=FakeResponse(content)) as get:
                path = Path(api._ensure_oba_live_installer())
                again = Path(api._ensure_oba_live_installer())
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path, again)
            get.assert_called_once()
            self.assertFalse(path.with_suffix(path.suffix + ".download").exists())

    def test_bad_digest_or_insecure_url_never_publishes_installer(self):
        with tempfile.TemporaryDirectory() as root:
            api = self._api(root, b"expected")
            with mock.patch("requests.get", return_value=FakeResponse(b"tampered")):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    api._ensure_oba_live_installer()
            self.assertFalse((Path(root) / "oba-live-tool-setup.exe").exists())
            api.config["oba_live_installer_url"] = "http://downloads.example.com/oba.exe"
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                api._ensure_oba_live_installer()

    def test_saved_executable_must_be_under_approved_install_root(self):
        with tempfile.TemporaryDirectory() as root:
            local = Path(root) / "local"
            approved = local / "Programs" / "oba-live-tool" / "oba-live-tool.exe"
            approved.parent.mkdir(parents=True)
            approved.write_bytes(b"exe")
            api = self._api(root)
            state = Path(root) / "state.txt"
            api._oba_state_path = lambda: state
            outside = Path(root) / "outside.exe"
            outside.write_bytes(b"exe")
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local), "PROGRAMFILES": str(Path(root) / "programs")}):
                state.write_text(str(outside), encoding="utf-8")
                self.assertEqual(api._find_oba_live_installed_exe(), str(approved.resolve()))


if __name__ == "__main__":
    unittest.main()
