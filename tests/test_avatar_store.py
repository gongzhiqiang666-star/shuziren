import tempfile
from pathlib import Path
import unittest

import cv2
import numpy as np

from scripts.avatar_store import AvatarStore, AvatarError


def fixture(root):
    root = Path(root)
    (root/'frames').mkdir(parents=True)
    (root/'positions').mkdir()
    for index in range(2):
        cv2.imwrite(str(root/'frames'/f'{index:06d}.jpg'), np.full((32, 24, 3), 90+index, np.uint8))
        (root/'positions'/f'{index:06d}.txt').write_text(
            'fps: 25\nwidth: 24\nheight: 32\nis_no_face: False\nbounding_box: [2, 20, 3, 22]\n', encoding='utf-8')
    return root


class AvatarTests(unittest.TestCase):
    def test_optional_source_assets_preserved_without_changing_name(self):
        (self.source/'model_info.yaml').write_text('fps: 25\n',encoding='utf-8')
        (self.source/'normalized_video.mp4').write_bytes(b'optional source fixture')
        avatar=self.store.import_prepared(self.source,'指定名称')
        self.assertEqual(avatar['name'],'指定名称')
        directory=self.store.directory(avatar['id'])
        self.assertEqual((directory/'model_info.yaml').read_text(),'fps: 25\n')
        self.assertEqual((directory/'normalized_video.mp4').read_bytes(),b'optional source fixture')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = fixture(self.root/'source')
        self.store = AvatarStore(self.root/'owned')

    def test_owned_copy_selection_and_reopen(self):
        avatar = self.store.import_prepared(self.source, '形象一')
        second = self.store.import_prepared(self.source, '形象二')
        self.store.select(second['id'])
        reopened = AvatarStore(self.root/'owned')
        self.assertEqual(reopened.selected(), second['id'])
        self.assertEqual(len(reopened.list()), 2)
        self.assertEqual(reopened.get(avatar['id'])['frames'], 2)
        (self.source/'frames/000000.jpg').unlink()
        self.assertTrue(reopened.sample(avatar['id']).startswith(b'\xff\xd8'))

    def test_changed_frame_and_missing_metadata_rejected(self):
        avatar = self.store.import_prepared(self.source, '形象')
        directory = self.store.directory(avatar['id'])
        path = directory/'frames/000000.jpg'
        original = path.read_bytes()
        path.write_bytes(original[:-1]+bytes([original[-1]^1]))
        with self.assertRaises(AvatarError): self.store.select(avatar['id'])
        path.write_bytes(original)
        (directory/'positions/000000.txt').unlink()
        with self.assertRaises(AvatarError): self.store.sample(avatar['id'])

    def test_failed_import_keeps_source_and_existing_avatar(self):
        avatar = self.store.import_prepared(self.source, '已有')
        (self.source/'positions/000001.txt').unlink()
        with self.assertRaises(AvatarError): self.store.import_prepared(self.source, '失败')
        self.assertTrue((self.source/'frames/000000.jpg').is_file())
        self.assertEqual([p.name for p in self.store.root.iterdir() if p.is_dir()], [avatar['id']])
        self.assertEqual(len(self.store.list()), 1)

    def test_corrupt_jpeg_and_wrong_rate_rejected(self):
        image = self.source/'frames/000000.jpg'
        original = image.read_bytes()
        image.write_bytes(b'not a jpeg')
        with self.assertRaises(AvatarError): self.store.import_prepared(self.source, '损坏')
        image.write_bytes(original)
        path = self.source/'positions/000000.txt'
        path.write_text(path.read_text().replace('fps: 25', 'fps: 30'))
        with self.assertRaises(AvatarError): self.store.import_prepared(self.source, '非25帧')
        self.assertEqual(self.store.list(), [])

    def test_no_face_and_path_traversal_rejected(self):
        for path in (self.source/'positions').glob('*.txt'):
            path.write_text(path.read_text().replace('False', 'True'))
        with self.assertRaises(AvatarError): self.store.import_prepared(self.source, '无人脸')
        for value in ('../source', 'bad', None):
            with self.assertRaises(AvatarError): self.store.get(value)


if __name__ == '__main__':
    unittest.main()
