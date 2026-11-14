import unittest

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


if __name__ == "__main__":
    unittest.main()
