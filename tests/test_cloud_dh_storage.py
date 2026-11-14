import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from recovered.main import Api


class CloudDhStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="云数字人项目-")
        self.addCleanup(self.temporary.cleanup)
        self.api = Api.__new__(Api); self.api.runtime_dir = Path(self.temporary.name); self.api.config = {}
        self.project = self.api.create_cloud_dh_project("中文云项目")["project"]
        self.project_id = self.project["id"]

    def test_concurrent_distinct_updates_all_survive(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda index: self.api.update_cloud_dh_project(
                    self.project_id, {f"custom_{index}": f"值{index}"}), range(24)))
        self.assertTrue(all(item.get("status") == "success" for item in results))
        reopened = self.api.get_cloud_dh_project(self.project_id)["project"]
        for index in range(24):
            self.assertEqual(reopened[f"custom_{index}"], f"值{index}")

    def test_replace_failure_preserves_old_yaml_and_removes_pending(self):
        path = Path(self.api._get_cloud_dh_project_info_path(self.project_id))
        before = path.read_bytes()
        with mock.patch("recovered.main.os.replace", side_effect=PermissionError("locked")):
            result = self.api.update_cloud_dh_project(self.project_id, {"name": "不应写入"})
        self.assertEqual(result["status"], "error")
        self.assertIn("locked", result["message"])
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent/".project_info.yaml.pending").exists())

    def test_corrupt_yaml_cannot_be_silently_repaired_by_update(self):
        path = Path(self.api._get_cloud_dh_project_info_path(self.project_id))
        damaged = b"name: [unterminated\n"; path.write_bytes(damaged)
        self.assertEqual(self.api.get_cloud_dh_project(self.project_id)["status"], "error")
        self.assertEqual(self.api.update_cloud_dh_project(self.project_id, {"name": "repair"})["status"], "error")
        self.assertEqual(path.read_bytes(), damaged)


if __name__ == "__main__":
    unittest.main()
