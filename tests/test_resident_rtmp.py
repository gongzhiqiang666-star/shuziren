import unittest
from unittest.mock import Mock

from scripts.resident_avatar import ResidentAvatar


class ResidentRtmpTests(unittest.TestCase):
    def setUp(self):
        self.engine = ResidentAvatar.__new__(ResidentAvatar)
        self.reader = self.engine.rtmp_reader = Mock(width=720, height=1280)

    def test_reconnect_preserves_partial_batch(self):
        self.reader.read_ahead.side_effect = [(['before'], [[]]), (['after'], [[]])]
        frames, metadata = self.engine._load_live_frames([0, 1])
        self.assertEqual(frames, ['before', 'after'])
        self.assertEqual(metadata, [{'is_no_face': True}] * 2)
        self.reader.reconnect.assert_called_once()

    def test_reconnect_rejects_resolution_change(self):
        self.reader.read_ahead.return_value = ([], [])
        self.reader.reconnect.side_effect = lambda _: setattr(self.reader, 'width', 640)
        with self.assertRaisesRegex(RuntimeError, '尺寸发生变化'):
            self.engine._load_live_frames([0])
        self.reader.read_ahead.assert_called_once_with(1)

    def test_reconnect_fails_when_frames_still_missing(self):
        self.reader.read_ahead.return_value = ([], [])
        with self.assertRaisesRegex(RuntimeError, '未收到足够画面'):
            self.engine._load_live_frames([0])
        self.reader.reconnect.assert_called_once()
