import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import yaml

from recovered.main import Api


class LiveStickerStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="贴片项目存储-")
        self.addCleanup(self.temporary.cleanup)
        self.api = Api.__new__(Api); self.api.runtime_dir = Path(self.temporary.name)
        self.project = self.api.create_live_sticker_project("中文贴片项目")["project"]
        self.project_id = self.project["id"]

    def test_concurrent_distinct_fields_survive_reopen(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda index: self.api.update_live_sticker_project(
                    self.project_id, {f"custom_{index}": f"值{index}"}), range(24)))
        self.assertTrue(all(item.get("status") == "success" for item in results))
        reopened = self.api.get_live_sticker_project(self.project_id)["project"]
        for index in range(24):
            self.assertEqual(reopened[f"custom_{index}"], f"值{index}")

    def test_replace_failure_keeps_previous_yaml_and_no_scratch(self):
        path = Path(self.api._get_live_sticker_project_info_path(self.project_id))
        before = path.read_bytes()
        with mock.patch("recovered.main_config.os.replace", side_effect=PermissionError("locked")):
            result = self.api.update_live_sticker_project(self.project_id, {"name": "不应写入"})
        self.assertIn("locked", result["error"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_corrupt_yaml_is_visible_and_not_overwritten_by_update(self):
        path = Path(self.api._get_live_sticker_project_info_path(self.project_id))
        damaged = b"name: [unterminated\n"; path.write_bytes(damaged)
        self.assertIn("error", self.api.get_live_sticker_project(self.project_id))
        self.assertIn("error", self.api.update_live_sticker_project(self.project_id, {"name": "repair"}))
        self.assertEqual(path.read_bytes(), damaged)


if __name__ == "__main__":
    unittest.main()
