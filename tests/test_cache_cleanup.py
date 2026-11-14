from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from recovered.cache_cleanup import clear_known_caches
from recovered.main import Api


class CacheCleanupTests(unittest.TestCase):
    def test_removes_known_cache_files_and_empty_directories_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / 'short_video' / 'nested' / 'one.bin'
            second = root / 'yunchuang_voice' / 'two.wav'
            unrelated = root / 'keep' / 'customer.txt'
            for path, content in ((first, b'123'), (second, b'4567'), (unrelated, b'keep')):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            result = clear_known_caches(root)
            self.assertEqual(result, {'status': 'success', 'removed': 2, 'removed_bytes': 7,
                                      'failures': [], 'message': '缓存清理完成'})
            self.assertFalse(first.parent.parent.exists())
            self.assertFalse(second.parent.exists())
            self.assertEqual(unrelated.read_bytes(), b'keep')

    def test_live_session_blocks_cleanup_before_touching_files(self):
        api = Api.__new__(Api)
        manager = type('Manager', (), {'is_broadcasting': True})()
        api._digital_live_manager = manager
        api._record_live_manager = type('Manager', (), {'is_broadcasting': False})()
        api._face_hand_live_manager = type('Manager', (), {'is_broadcasting': False})()
        with patch('recovered.cache_cleanup.clear_known_caches') as cleanup:
            result = api.clear_cache()
        cleanup.assert_not_called()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['removed'], 0)
        self.assertIn('请先停止', result['message'])

    def test_cleanup_result_is_forwarded_without_hiding_partial_failures(self):
        api = Api.__new__(Api)
        for name in ('_digital_live_manager', '_record_live_manager', '_face_hand_live_manager'):
            setattr(api, name, type('Manager', (), {'is_broadcasting': False})())
        expected = {'status': 'partial', 'removed': 1, 'removed_bytes': 9,
                    'failures': [{'path': 'locked', 'error': 'in use'}], 'message': '部分缓存无法清理'}
        with patch('recovered.cache_cleanup.clear_known_caches', return_value=expected):
            self.assertIs(api.clear_cache(), expected)

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics required')
    def test_locked_windows_cache_file_is_reported_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'short_video' / 'locked.bin'
            path.parent.mkdir()
            path.write_bytes(b'locked')
            with path.open('rb'):
                result = clear_known_caches(directory)
                self.assertEqual(result['status'], 'partial')
                self.assertEqual(result['removed'], 0)
                self.assertTrue(path.is_file())
                self.assertTrue(any('locked.bin' in failure['path'] for failure in result['failures']))
            retry = clear_known_caches(directory)
            self.assertEqual(retry['status'], 'success')
            self.assertEqual(retry['removed'], 1)
            self.assertFalse(path.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows junction semantics required')
    def test_windows_junction_is_removed_without_following_external_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root/'short_video'; cache.mkdir()
            external = root/'customer-data'; external.mkdir()
            keep = external/'keep.txt'; keep.write_text('do not delete', encoding='utf-8')
            junction = cache/'external-link'
            created = subprocess.run(
                ['cmd', '/c', 'mklink', '/J', str(junction), str(external)],
                capture_output=True, text=True,
            )
            self.assertEqual(created.returncode, 0, created.stderr or created.stdout)
            result = clear_known_caches(root)
            self.assertEqual(result['status'], 'success')
            self.assertFalse(junction.exists())
            self.assertEqual(keep.read_text(encoding='utf-8'), 'do not delete')


if __name__ == '__main__':
    unittest.main()
