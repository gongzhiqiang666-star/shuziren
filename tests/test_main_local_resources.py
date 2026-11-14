import ctypes
import sys
import tempfile
import unittest
import wave
from ctypes import wintypes
from pathlib import Path

import yaml
from PIL import Image

from recovered.clone_manager import CloneManager
from recovered.main import Api


class MainLocalResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="数字人资源-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.images = self.root/"人物模型"
        self.voices = self.root/"参考音色"
        self.manager = CloneManager({
            "image_base_dir": str(self.images),
            "voice_base_dir": str(self.voices),
        })
        self.api = Api.__new__(Api)
        self.api._clone_manager = self.manager

    def create_model(self, resource_id="中文人物"):
        directory = self.images/resource_id
        directory.mkdir(parents=True)
        (directory/"model_info.yaml").write_text(yaml.safe_dump({
            "id": resource_id, "name": "中文人物名称", "width": 720, "height": 1280,
            "supported_versions": ["v2"],
        }, allow_unicode=True), encoding="utf-8")
        Image.new("RGB", (64, 96), (20, 120, 200)).save(directory/"sample.jpg")
        return directory

    def create_voice(self, resource_id="中文音色"):
        directory = self.voices/resource_id
        directory.mkdir(parents=True)
        (directory/"model_info.yaml").write_text(yaml.safe_dump({
            "id": resource_id, "name": "中文音色名称", "provider": "voice",
        }, allow_unicode=True), encoding="utf-8")
        with wave.open(str(directory/"ref_audio.wav"), "wb") as stream:
            stream.setparams((1, 2, 16000, 1600, "NONE", "not compressed"))
            stream.writeframes(b"\0\0" * 1600)
        return directory

    def test_unicode_resources_are_enumerated_previewed_and_removed(self):
        self.create_model(); self.create_voice()
        first = self.api.get_local_resources()
        self.assertEqual(first["status"], "success")
        self.assertEqual(first["models"][0]["name"], "中文人物名称")
        self.assertTrue(first["models"][0]["sample_data"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(first["voices"][0]["name"], "中文音色名称")
        self.assertTrue(first["voices"][0]["sample_data"].startswith("data:audio/wav;base64,"))
        self.assertEqual(self.api.delete_model("中文人物"), {"status": "success"})
        self.assertEqual(self.api.delete_voice("中文音色"), {"status": "success"})
        refreshed = self.api.get_local_resources()
        self.assertEqual((refreshed["models"], refreshed["voices"]), ([], []))

    @unittest.skipUnless(sys.platform == "win32", "requires Windows sharing semantics")
    def test_occupied_model_file_fails_then_deletes_after_handle_release(self):
        directory = self.create_model("occupied-model")
        sample = directory/"sample.jpg"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateFileW(str(sample), 0x80000000, 0x1, None, 3, 0, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value)
        try:
            failed = self.api.delete_model("occupied-model")
            self.assertIn("删除模型失败", failed["error"])
            self.assertTrue(directory.is_dir())
        finally:
            self.assertTrue(kernel32.CloseHandle(handle))
        self.assertEqual(self.api.delete_model("occupied-model"), {"status": "success"})
        self.assertFalse(directory.exists())

    def test_resource_ids_cannot_escape_managed_roots(self):
        for resource_id in ("../outside", "folder/name", str((self.root/"outside").resolve())):
            with self.subTest(resource_id=resource_id):
                self.assertIn("资源 ID 无效", self.api.delete_model(resource_id)["error"])
                self.assertIn("资源 ID 无效", self.api.delete_voice(resource_id)["error"])


if __name__ == "__main__":
    unittest.main()
