import subprocess
import tempfile
import unittest
from pathlib import Path

from recovered.hold_product_video import (
    DRIVE_FPS, DRIVE_HEIGHT, DRIVE_WIDTH, is_drive_spec, make_pingpong_video,
    portrait_filter, probe_video, write_drive_video,
)


RUNTIME = Path(r"D:\TEMP\v122-minimum-proof-ready\runtime\yunchuang_v122")
FFMPEG = RUNTIME / "_internal/env/ffmpeg/bin/ffmpeg.exe"
FFPROBE = RUNTIME / "_internal/env/ffmpeg/bin/ffprobe.exe"


class HoldProductVideoTests(unittest.TestCase):
    def setUp(self):
        if not FFMPEG.is_file() or not FFPROBE.is_file():
            self.skipTest("需要随包 FFmpeg/FFprobe")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.mp4"
        subprocess.run([
            str(FFMPEG), "-y", "-f", "lavfi", "-i", "testsrc2=s=160x120:r=10:d=0.4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(self.source),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_normalizes_real_video_to_v179_drive_contract(self):
        output = write_drive_video(self.source, self.root / "drive.mp4",
                                   ffmpeg=FFMPEG, ffprobe=FFPROBE)
        info = probe_video(output, ffprobe=FFPROBE)
        self.assertEqual((info["width"], info["height"], round(info["fps"]), info["codec"]),
                         (DRIVE_WIDTH, DRIVE_HEIGHT, DRIVE_FPS, "h264"))
        self.assertFalse(info["has_audio"])
        self.assertTrue(is_drive_spec(info))
        self.assertEqual(portrait_filter(),
                         "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
                         "scale=trunc(iw/2)*2:trunc(ih/2)*2,pad=1080:1920:(ow-iw)/2:"
                         "(oh-ih)/2:color=black,setsar=1")

    def test_pingpong_is_about_twice_duration_and_failure_preserves_output(self):
        output = make_pingpong_video(self.source, self.root / "loop.mp4", ffmpeg=FFMPEG)
        info = probe_video(output, ffprobe=FFPROBE)
        self.assertTrue(is_drive_spec(info))
        self.assertFalse(info["has_audio"])
        self.assertGreaterEqual(info["duration"], 0.7)
        previous = output.read_bytes()
        with self.assertRaises(ValueError):
            write_drive_video(self.root / "missing.mp4", output, ffmpeg=FFMPEG, ffprobe=FFPROBE)
        self.assertEqual(output.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
