import unittest
from unittest.mock import Mock, patch

from recovered.face_hand_player import FaceHandVideoStreamManager
from recovered.output_mode import normalize_output_mode
from recovered.video_player import Player


class OutputModeTests(unittest.TestCase):
    def test_virtual_camera_aliases_are_shared_by_both_players(self):
        for value in ("cam", "camera", "vcam", "virtual_cam", " VCam "):
            with self.subTest(value=value):
                self.assertEqual(normalize_output_mode(value), "virtual_cam")
                self.assertEqual(Player(output_mode=value).output_mode, "virtual_cam")
                self.assertEqual(
                    FaceHandVideoStreamManager(
                        face_videos=[], hand_videos=[], image_output_mode=value
                    ).image_output_mode,
                    "virtual_cam",
                )

    def test_window_and_unknown_modes_are_deterministic(self):
        self.assertEqual(normalize_output_mode(" WINDOW "), "window")
        with self.assertRaisesRegex(ValueError, "不支持的视频输出模式"):
            Player(output_mode="silent-no-output")
        with self.assertRaisesRegex(ValueError, "不支持的视频输出模式"):
            FaceHandVideoStreamManager(
                face_videos=[], hand_videos=[], image_output_mode="silent-no-output"
            )

    def test_recorded_virtual_camera_keeps_independent_audio_output(self):
        audio = Mock(sample_rate=48000)
        worker = Mock(last_error="", finished=False)
        worker.has_media_packets.return_value = True
        play_thread = Mock()
        player = Player(output_mode="virtual_cam")
        with patch("recovered.video_player._AudioOutput", return_value=audio) as audio_type, patch(
                "recovered.video_player._SourceWorker", return_value=worker) as worker_type, patch(
                "recovered.video_player._probe_fps", return_value=25.0), patch(
                "recovered.video_player.Thread", return_value=play_thread):
            player.start("source.mp4")

        audio_type.assert_called_once_with()
        worker_type.assert_called_once_with(
            "source.mp4", True, frame_processor=None, audio_sample_rate=48000
        )
        worker.start.assert_called_once_with()
        worker.wait_until_ready.assert_called_once_with(timeout_seconds=0.75)
        self.assertIs(player._audio_output, audio)
        play_thread.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
