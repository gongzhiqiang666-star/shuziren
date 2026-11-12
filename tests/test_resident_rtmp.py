import queue
import threading
import unittest
from unittest.mock import MagicMock, Mock

from scripts.resident_avatar import ResidentAvatar


class ResidentRtmpTests(unittest.TestCase):
    def setUp(self):
        self.engine = ResidentAvatar.__new__(ResidentAvatar)
        self.engine.rtmp_last = ('last', [])
        self.engine.rtmp_cancel = threading.Event()
        self.engine.rtmp_reconnect = self.engine.rtmp_error = None
        self.reader = self.engine.rtmp_reader = Mock(width=720, height=1280)
        self.reader.internal_buffer = []
        self.reader.processed_frames_queue = queue.Queue()

    def test_reconnect_does_not_block_output_and_switches_back_to_live_frames(self):
        release = threading.Event()
        self.reader.reconnect.side_effect = lambda cancel: release.wait(2)
        self.reader.processed_frames_queue.put(None)
        try:
            self.assertEqual(self.engine._load_live_frames([0, 1])[0], ['last', 'last'])
            self.assertTrue(self.engine.rtmp_reconnect.is_alive())
        finally:
            release.set()
            self.engine.rtmp_reconnect.join(2)
        self.reader.processed_frames_queue.put((['fresh'], [[]]))
        self.assertEqual(self.engine._load_live_frames([2])[0], ['fresh'])
        self.reader.reconnect.assert_called_once_with(self.engine.rtmp_cancel)

    def test_reconnect_rejects_resolution_change(self):
        self.reader.reconnect.side_effect = lambda _: setattr(self.reader, 'width', 640)
        self.engine._reconnect_rtmp(self.reader)
        with self.assertRaisesRegex(RuntimeError, '尺寸发生变化'):
            self.engine._load_live_frames([0])

    def test_reconnect_error_published_at_thread_exit_prevents_dequeue(self):
        def finish_reconnect():
            self.engine.rtmp_error = RuntimeError('RTMP 重连后输入尺寸发生变化')
            return False

        self.engine.rtmp_reconnect = Mock()
        self.engine.rtmp_reconnect.is_alive.side_effect = finish_reconnect
        self.reader.processed_frames_queue.put((['wrong-size'], [[]]))
        with self.assertRaisesRegex(RuntimeError, '尺寸发生变化'):
            self.engine._load_live_frames([0])
        self.assertEqual(self.reader.processed_frames_queue.get_nowait(), (['wrong-size'], [[]]))

    def test_close_releases_model_even_when_rtmp_cleanup_fails(self):
        synth = self.engine.synth = Mock()
        context = self.engine.context = MagicMock()
        self.reader.stop_capture.side_effect = OSError('capture cleanup failed')
        with self.assertRaisesRegex(OSError, 'capture cleanup failed'):
            self.engine.close()
        self.engine.close()
        self.assertTrue(self.engine.rtmp_cancel.is_set())
        synth.close.assert_called_once_with()
        context.__exit__.assert_called_once_with(None, None, None)

    def test_close_cancels_and_joins_pending_reconnect_before_stopping_reader(self):
        started = threading.Event()
        self.engine.synth = None

        def reconnect(cancel):
            started.set()
            cancel.wait(2)

        self.reader.reconnect.side_effect = reconnect
        self.reader.processed_frames_queue.put(None)
        self.engine._load_live_frames([0])
        self.assertTrue(started.wait(1))
        self.reader.stop_capture.side_effect = lambda: self.assertFalse(
            self.engine.rtmp_reconnect.is_alive())
        self.engine.close()
        self.assertTrue(self.engine.rtmp_cancel.is_set())
        self.reader.stop_capture.assert_called_once_with()
