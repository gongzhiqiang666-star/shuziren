import io
import queue
import threading
import unittest
from unittest.mock import Mock

from recovered.image_rtmp_face_reader import RtmpFaceReader


class RtmpFirstFrameTests(unittest.TestCase):
    def test_eof_does_not_count_as_first_frame(self):
        for payload in (b'', bytes(range(12))):
            with self.subTest(has_frame=bool(payload)):
                reader = RtmpFaceReader.__new__(RtmpFaceReader)
                reader.width = reader.height = 2
                reader.stop_event = threading.Event()
                reader.first_frame = threading.Event()
                reader.raw_frames_queue = queue.Queue()
                reader.ffmpeg_process = Mock(stdout=io.BytesIO(payload))
                reader.ffmpeg_process.poll.return_value = 0
                reader._capture_thread()
                self.assertEqual(reader._wait_for_initial_frame(.1), bool(payload))
                if payload:
                    self.assertEqual(reader.raw_frames_queue.get_nowait().tobytes(), payload)
                self.assertIsNone(reader.raw_frames_queue.get_nowait())
