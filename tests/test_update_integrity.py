import hashlib
import ctypes
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from recovered import update_integrity


class FakeGui:
    def set_status(self, text, progress=None):
        pass


class UpdateIntegrityTests(unittest.TestCase):
    def test_loopback_update_service_returns_ordered_pending_versions(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps([
                    {"version": 3, "download_url": "http://127.0.0.1/package-3.zip", "sha256": "3" * 64},
                    {"version": 2, "download_url": "http://127.0.0.1/package-2.zip", "sha256": "2" * 64},
                ]).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as root:
                runtime = Path(root); (runtime/"config").mkdir()
                (runtime/"config/config.yaml").write_text(
                    f"version: v001\nupdate_url: http://127.0.0.1:{server.server_port}\n", encoding="utf-8")
                status = update_integrity.get_update_status(runtime)
            self.assertTrue(status["has_update"])
            self.assertEqual([item["version"] for item in status["pending_updates"]], [2, 3])
            self.assertEqual(status["latest_version"], "v003")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_update_urls_require_https_except_loopback(self):
        self.assertEqual(
            update_integrity._resolve_update_status_url({"update_url": "https://updates.example.com"}),
            "https://updates.example.com/get_latest",
        )
        self.assertEqual(
            update_integrity._resolve_update_status_url({"update_url": "http://127.0.0.1:5155"}),
            "http://127.0.0.1:5155/get_latest",
        )
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            update_integrity._resolve_update_status_url({"update_url": "http://updates.example.com"})

    def test_update_item_requires_trusted_url_and_digest(self):
        valid = {"version": 123, "download_url": "https://updates.example.com/v123.zip", "sha256": "a" * 64}
        update_integrity._validate_update_item(valid)
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            update_integrity._validate_update_item({**valid, "download_url": "http://updates.example.com/v123.zip"})
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            update_integrity._validate_update_item({**valid, "sha256": ""})

    def test_digest_gate_requires_and_matches_sha256(self):
        with tempfile.TemporaryDirectory() as root:
            package = Path(root) / "update.zip"
            package.write_bytes(b"verified update")
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            update_integrity._verify_download_digest(package, digest, "v123")
            with self.assertRaisesRegex(ValueError, "缺少有效"):
                update_integrity._verify_download_digest(package, None, "v123")
            with self.assertRaisesRegex(ValueError, "校验失败"):
                update_integrity._verify_download_digest(package, "0" * 64, "v123")

    def test_zip_members_reject_traversal_absolute_and_symlink(self):
        cases = ("../escape.txt", "/absolute.txt", "C:/drive.txt")
        with tempfile.TemporaryDirectory() as root:
            for index, name in enumerate(cases):
                path = Path(root) / f"bad-{index}.zip"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(name, b"bad")
                with zipfile.ZipFile(path) as archive, self.assertRaises(ValueError):
                    update_integrity._validated_zip_members(archive)
            path = Path(root) / "symlink.zip"
            info = zipfile.ZipInfo("_internal/link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(info, "target")
            with zipfile.ZipFile(path) as archive, self.assertRaises(ValueError):
                update_integrity._validated_zip_members(archive)

    def test_transaction_rolls_back_replaced_and_created_files(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "app"
            source = base / "temp_update"
            (source / "_internal").mkdir(parents=True)
            (base / "_internal").mkdir(exist_ok=True)
            (source / "_internal" / "a.txt").write_text("new-a", encoding="utf-8")
            (source / "_internal" / "b.txt").write_text("new-b", encoding="utf-8")
            (base / "_internal" / "a.txt").write_text("old-a", encoding="utf-8")
            updater = update_integrity.Updater(FakeGui(), base)
            original_replace = update_integrity.os.replace
            calls = 0

            def fail_second(source_path, destination_path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected replace failure")
                return original_replace(source_path, destination_path)

            with mock.patch.object(update_integrity.os, "replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "injected"):
                    updater.update_files("v123", 0, 1)
            self.assertEqual((base / "_internal" / "a.txt").read_text(encoding="utf-8"), "old-a")
            self.assertFalse((base / "_internal" / "b.txt").exists())

    def test_transaction_preserves_config_and_commits_verified_files(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "app"
            source = base / "temp_update"
            (source / "_internal" / "config").mkdir(parents=True)
            (base / "_internal" / "config").mkdir(parents=True)
            (source / "_internal" / "module.txt").write_text("new", encoding="utf-8")
            (source / "_internal" / "config" / "config.yaml").write_text("version: new", encoding="utf-8")
            config = base / "_internal" / "config" / "config.yaml"
            config.write_text("version: old", encoding="utf-8")
            updater = update_integrity.Updater(FakeGui(), base)
            updater.update_files("v123", 0, 1)
            self.assertEqual((base / "_internal" / "module.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual(config.read_text(encoding="utf-8"), "version: old")

    @unittest.skipUnless(sys.platform == "win32", "requires Windows sharing semantics")
    def test_locked_target_preserves_old_file_cleans_stage_and_retries(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)/"app"
            source = base/"temp_update"/"_internal"
            target = base/"_internal"/"module.txt"
            source.mkdir(parents=True); target.parent.mkdir(parents=True)
            (source/"module.txt").write_text("new", encoding="utf-8")
            target.write_text("old", encoding="utf-8")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateFileW.argtypes = (
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            )
            kernel32.CreateFileW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.CreateFileW(str(target), 0x80000000, 0x1, None, 3, 0, None)
            self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
            updater = update_integrity.Updater(FakeGui(), base)
            try:
                with self.assertRaises(OSError):
                    updater.update_files("v123", 0, 1)
                self.assertEqual(target.read_text(encoding="utf-8"), "old")
                self.assertFalse(target.with_name("module.txt.update-new").exists())
            finally:
                self.assertTrue(kernel32.CloseHandle(handle))
            updater.update_files("v123", 0, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "new")


if __name__ == "__main__":
    unittest.main()
