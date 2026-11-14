import tempfile
import unittest
import base64
import io
from pathlib import Path

from PIL import Image

from recovered.main import Api


class LiveStickerProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.api = Api.__new__(Api)
        self.api.runtime_dir = Path(self.temp.name)
        self.project = self.api.create_live_sticker_project('事务贴片')['project']

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def png(path, colour):
        Image.new('RGB', (96, 160), colour).save(path, 'PNG')

    def generate(self, colours, fail_at=None):
        calls = 0
        ratios = []
        def provider(*, dest, aspect_ratio='9:16', **_):
            nonlocal calls
            calls += 1
            ratios.append(aspect_ratio)
            if calls == fail_at: raise RuntimeError('provider interrupted')
            self.png(dest, colours[calls - 1])
        self.api._generate_live_sticker_image_file = provider
        result = self.api.generate_live_sticker_images({
            'project_id': self.project['id'], 'runninghub_api_key': 'local-test-key',
            'background_prompt': 'background', 'foreground_prompt': 'foreground',
            'cover_prompt': 'cover',
        })
        result['requested_ratios'] = ratios
        return result

    def asset_bytes(self):
        outputs = self.api._get_live_sticker_output_paths(self.project['id'])
        return {key: Path(path).read_bytes() for key, path in outputs.items()}

    def test_incomplete_batch_keeps_last_complete_assets_and_records_error(self):
        self.assertEqual(self.generate(['red', 'green', 'blue'])['status'], 'success')
        before = self.asset_bytes()
        failed = self.generate(['yellow', 'purple', 'black'], fail_at=3)
        self.assertEqual(failed['status'], 'error')
        self.assertEqual(self.asset_bytes(), before)
        current = self.api.get_live_sticker_project(self.project['id'])['project']
        self.assertEqual(current['status'], 'error')
        self.assertIn('provider interrupted', current['last_error'])

    def test_second_complete_batch_archives_first_without_overwriting_history(self):
        self.assertEqual(self.generate(['red', 'green', 'blue'])['status'], 'success')
        first = self.asset_bytes()
        self.assertEqual(self.generate(['yellow', 'purple', 'black'])['status'], 'success')
        second = self.asset_bytes()
        self.assertNotEqual(first['bg'], second['bg'])
        self.assertEqual(self.generate(['white', 'orange', 'grey'])['status'], 'success')
        history = Path(self.api._get_live_sticker_history_dir(self.project['id']))
        archived = list(history.rglob('背景.png'))
        self.assertEqual(len(archived), 2)
        self.assertEqual({item.read_bytes() for item in archived}, {first['bg'], second['bg']})
        self.assertEqual(self.api.get_live_sticker_project(self.project['id'])['project']['status'], 'success')

    def test_complete_project_exposes_all_previews_and_expected_provider_ratios(self):
        result = self.generate(['red', 'green', 'blue'])
        self.assertEqual(result['requested_ratios'], ['9:16', '9:16', '1:1'])
        project = self.api.get_live_sticker_project(self.project['id'])['project']
        for field in ('bg', 'fg_white', 'fg_alpha', 'cover'):
            url = project[field + '_preview_url']
            self.assertTrue(url.startswith('data:image/png;base64,'), field)
            with Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1]))) as image:
                self.assertGreater(image.width, 0)
                self.assertGreater(image.height, 0)
        with Image.open(project['cover_path']) as cover:
            self.assertEqual(cover.size, (750, 750))


if __name__ == '__main__': unittest.main()
