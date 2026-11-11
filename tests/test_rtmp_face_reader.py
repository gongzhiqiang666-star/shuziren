import io
import queue
import threading
import unittest
from unittest.mock import Mock

from recovered.image_rtmp_face_reader import RtmpFaceReader


class RtmpFirstFrameTests(unittest.TestCase):
    def test_rtmp_decode_preserves_input_frame_cadence(self):
        reader = RtmpFaceReader.__new__(RtmpFaceReader)
        command = reader._build_ffmpeg_command('rtmp://127.0.0.1/live/test', 25)
        self.assertEqual(command[command.index('-vf') + 1], 'null')
        self.assertEqual(command[command.index('-fps_mode') + 1], 'passthrough')

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
