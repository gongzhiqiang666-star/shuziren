import io
import queue
import threading
import unittest
from unittest.mock import Mock, patch

from recovered.image_rtmp_face_reader import RtmpFaceReader


class RtmpFirstFrameTests(unittest.TestCase):
    def test_probe_rejects_audio_only_and_preserves_odd_video_dimensions(self):
        reader = RtmpFaceReader.__new__(RtmpFaceReader)
        with patch('recovered.image_rtmp_face_reader.subprocess.run') as run:
            run.return_value = Mock(returncode=0, stdout='{"streams":[]}')
            with self.assertRaisesRegex(RuntimeError, '没有视频轨'):
                reader._get_video_properties('rtmp://127.0.0.1/live/audio')
            run.return_value.stdout = '{"streams":[{"width":321,"height":241,"avg_frame_rate":"0/0"}]}'
            self.assertEqual(reader._get_video_properties('rtmp://127.0.0.1/live/video'), (321, 241, 25.0))

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
