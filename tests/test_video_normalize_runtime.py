import unittest
from unittest import mock

from recovered import image_clone_video_normalize as normalize


class VideoNormalizeRuntimeTests(unittest.TestCase):
    @mock.patch("recovered.video_player._resolve_ffprobe_executable", return_value="bundled-ffprobe")
    @mock.patch.object(normalize.subprocess, "check_output")
    def test_rotation_uses_effective_dimensions_and_safe_fraction(self, check_output, resolve):
        check_output.return_value = b'''{"streams":[
          {"codec_type":"video","width":1920,"height":1080,"r_frame_rate":"30000/1001",
           "side_data_list":[{"rotation":90}]},
          {"codec_type":"audio","sample_rate":"48000","channels":2}
        ]}'''
        info = normalize.get_video_info("rotated.mp4")
        self.assertEqual((info["width"], info["height"], info["rotation"]), (1080, 1920, 90))
        self.assertAlmostEqual(info["fps"], 30000 / 1001)
        self.assertEqual((info["audio_sample_rate"], info["audio_channels"]), (48000, 2))
        self.assertEqual(check_output.call_args.args[0][0], "bundled-ffprobe")

    @mock.patch("recovered.video_player._resolve_ffprobe_executable", return_value="bundled-ffprobe")
    @mock.patch.object(normalize.subprocess, "check_output")
    def test_invalid_frame_rate_is_not_executed(self, check_output, resolve):
        check_output.return_value = b'''{"streams":[
          {"codec_type":"video","width":1280,"height":720,"r_frame_rate":"not-a-fraction"}
        ]}'''
        self.assertEqual(normalize.get_video_info("video.mp4")["fps"], 0.0)


if __name__ == "__main__":
    unittest.main()
