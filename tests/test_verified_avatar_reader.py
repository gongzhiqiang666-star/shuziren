import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from scripts.avatar_store import AvatarStore, AvatarError
from scripts.verified_avatar_reader import VerifiedAvatarReader
from test_avatar_store import fixture


class VerifiedReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.store = AvatarStore(root/'owned')
        self.record = self.store.import_prepared(fixture(root/'source'), '测试')
        self.directory = self.store.directory(self.record['id'])
        self.reader = VerifiedAvatarReader(self.directory, 2)

    def test_decodes_verified_bytes_and_native_metadata(self):
        frame, metadata = self.reader.load(2)
        np.testing.assert_array_equal(frame, cv2.imread(str(self.directory/'frames/000000.jpg')))
        np.testing.assert_array_equal(metadata['bounding_box'], [2, 20, 3, 22])
        self.assertFalse(metadata['is_no_face'])

    def test_changed_frame_or_metadata_rejected_before_decode(self):
        for relative in ['frames/000000.jpg', 'positions/000000.txt']:
            with self.subTest(relative=relative):
                path = self.directory/relative
                original = path.read_bytes()
                path.write_bytes(original+b'changed')
                with self.assertRaises(AvatarError):
                    self.reader.load(0)
                with self.assertRaises(AvatarError):
                    self.store.get(self.record['id'])
                path.write_bytes(original)

    def test_hot_identity_reads_only_manifest_and_detects_change(self):
        from scripts.avatar_store import digest
        with patch('scripts.avatar_store.digest', wraps=digest) as called:
            self.assertEqual(self.store.identity(self.record['id']), self.record)
            self.assertEqual(called.call_count, 1)
            self.assertEqual(called.call_args.args[0].name, 'manifest.json')
        with (self.directory/'manifest.json').open('a') as stream:
            stream.write(' ')
        with self.assertRaises(AvatarError):
            self.store.identity(self.record['id'])
