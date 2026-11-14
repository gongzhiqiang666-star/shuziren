import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import yaml

from recovered.main import Api


class IpProjectStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="IP项目存储-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)/"项目"
        self.api = Api.__new__(Api)
        self.api._get_ip_agent_base_dir = lambda: str(self.root)
        self.project = self.api.create_ip_agent_project("中文项目")['project']
        self.project_id = self.project['id']

    def test_concurrent_distinct_updates_are_merged_without_yaml_corruption(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda index: self.api.update_ip_agent_project(self.project_id, {f"field_{index}": index}),
                range(24),
            ))
        self.assertTrue(all(result.get('status') == 'success' for result in results))
        reopened = self.api.get_ip_agent_project(self.project_id)['project']
        for index in range(24):
            self.assertEqual(reopened[f"field_{index}"], index)
        persisted = yaml.safe_load(Path(self.api._get_ip_agent_project_info_path(self.project_id)).read_text(encoding='utf-8'))
        self.assertIsInstance(persisted, dict)

    def test_replace_failure_preserves_previous_project_and_cleans_temporary(self):
        info_path = Path(self.api._get_ip_agent_project_info_path(self.project_id))
        before = info_path.read_bytes()
        with mock.patch('recovered.main_config.os.replace', side_effect=PermissionError('locked')):
            result = self.api.update_ip_agent_project(self.project_id, {'name': '不应写入'})
        self.assertIn('locked', result['error'])
        self.assertEqual(info_path.read_bytes(), before)
        self.assertEqual(list(info_path.parent.glob('*.tmp')), [])

    def test_corrupt_project_is_reported_and_never_silently_reset(self):
        info_path = Path(self.api._get_ip_agent_project_info_path(self.project_id))
        damaged = b'name: [unterminated\n'
        info_path.write_bytes(damaged)
        result = self.api.get_ip_agent_project(self.project_id)
        self.assertIn('error', result)
        self.assertEqual(info_path.read_bytes(), damaged)
        update = self.api.update_ip_agent_project(self.project_id, {'name': 'repair without consent'})
        self.assertIn('error', update)
        self.assertEqual(info_path.read_bytes(), damaged)


if __name__ == '__main__':
    unittest.main()
