from pathlib import Path
import tempfile
import unittest

from recovered.main import Api


class MainIdentityAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'assets/web').mkdir(parents=True)
        self.api = Api.__new__(Api)
        self.api.runtime_dir = self.root
        self.api.base_dir = str(self.root)

    def test_asset_lookup_rejects_absolute_and_parent_paths(self):
        for value in ('../secret', 'assets/../secret', str((self.root/'x').resolve())):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '资源路径无效'):
                self.api._find_asset(value)

    def test_identity_assets_are_bounded_without_large_reads(self):
        web = self.root/'assets/web'
        (web/'id.txt').write_bytes(b'1' * 129)
        self.assertIn('error', self.api.get_admin_id())
        (web/'oem_config.json').write_bytes(b' ' * (1024 * 1024 + 1))
        result = self.api.get_oem_config()
        self.assertEqual((result['status'], result['config']), ('error', {}))
        self.assertIn('大小限制', result['message'])
        (web/'bg.png').write_bytes(b'x' * (16 * 1024 * 1024 + 1))
        result = self.api.get_background_image()
        self.assertIn('大小限制', result['error'])

    def test_valid_oem_and_background_keep_original_response_shape(self):
        web = self.root/'assets/web'
        (web/'id.txt').write_text('021', encoding='utf-8')
        (web/'oem_config.json').write_text('{"window_name":"品牌"}', encoding='utf-8')
        (web/'bg.png').write_bytes(b'\x89PNG\r\n')
        self.assertEqual(self.api.get_admin_id(), {'status':'success', 'admin_id':21})
        self.assertEqual(self.api.get_oem_config(), {
            'status':'success', 'config':{'window_name':'品牌'}})
        self.assertTrue(self.api.get_background_image()['image_data'].startswith('data:image/png;base64,'))


if __name__ == '__main__':
    unittest.main()
