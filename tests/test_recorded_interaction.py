from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from pydub import AudioSegment
from pydub.generators import Sine

from scripts.recorded_interaction import mix_replacements, render_replacements, validate_replacements


class RecordedInteractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root / "first.wav"
        self.second = self.root / "second.wav"
        with Sine(800).to_audio_segment(duration=200).export(self.first, format="wav"):
            pass
        with Sine(1200).to_audio_segment(duration=300).export(self.second, format="wav"):
            pass

    def plan(self):
        return [
            {"start_ms": 200, "end_ms": 500, "reply_audio": str(self.first), "source_id": "comment-1"},
            {"start_ms": 700, "end_ms": 1100, "reply_audio": str(self.second), "source_id": "comment-2"},
        ]

    def test_multiple_replies_keep_original_duration_and_outside_audio(self):
        original = Sine(300).to_audio_segment(duration=1500)
        replacements = validate_replacements(self.plan(), duration_ms=len(original))
        mixed = mix_replacements(original, replacements)
        self.assertEqual(len(mixed), len(original))
        self.assertEqual(mixed[:150].raw_data, original[:150].raw_data)
        self.assertEqual(mixed[550:650].raw_data, original[550:650].raw_data)
        self.assertNotEqual(mixed[250:400].raw_data, original[250:400].raw_data)
        self.assertNotEqual(mixed[750:1000].raw_data, original[750:1000].raw_data)

    def test_overlap_order_bounds_duplicates_and_unknown_fields_rejected(self):
        cases = []
        overlap = self.plan(); overlap[1]["start_ms"] = 450; cases.append(overlap)
        reverse = self.plan(); reverse[0]["end_ms"] = 100; cases.append(reverse)
        beyond = self.plan(); beyond[1]["end_ms"] = 1600; cases.append(beyond)
        duplicate = self.plan(); duplicate[1]["source_id"] = "comment-1"; cases.append(duplicate)
        extra = self.plan(); extra[0]["unexpected"] = True; cases.append(extra)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_replacements(value, duration_ms=1500)

    def test_missing_symlink_and_excessive_reply_rejected(self):
        missing = self.plan(); missing[0]["reply_audio"] = str(self.root / "missing.wav")
        with self.assertRaises(ValueError):
            validate_replacements(missing, duration_ms=1500)
        link = self.root / "link.wav"
        try:
            link.symlink_to(self.first)
        except OSError:
            link = None
        if link is not None:
            linked = self.plan(); linked[0]["reply_audio"] = str(link)
            with self.assertRaises(ValueError):
                validate_replacements(linked, duration_ms=1500)
        long_reply = self.root / "long.wav"
        with Sine(600).to_audio_segment(duration=500).export(long_reply, format="wav"):
            pass
        plan = self.plan(); plan[0]["reply_audio"] = str(long_reply)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            mix_replacements(Sine(300).to_audio_segment(duration=1500),
                             validate_replacements(plan, duration_ms=1500))

    def test_empty_plan_is_exact_noop(self):
        original = Sine(300).to_audio_segment(duration=500)
        self.assertEqual(mix_replacements(original, validate_replacements([], duration_ms=500)).raw_data,
                         original.raw_data)

    def test_real_mp4_render_is_atomic_and_keeps_video_track(self):
        bundled = Path(sys.executable).parent / "ffmpeg" / "bin" / "ffmpeg.exe"
        ffmpeg = Path(os.environ.get("SHUZIREN_TEST_FFMPEG") or bundled)
        if not ffmpeg.is_file():
            located = shutil.which("ffmpeg")
            if not located:
                self.skipTest("FFmpeg is not available")
            ffmpeg = Path(located)
        ffprobe = ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if not ffprobe.is_file():
            self.skipTest("FFprobe is not available")
        source, output = self.root / "source.mp4", self.root / "result.mp4"
        subprocess.run([
            str(ffmpeg), "-nostdin", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=1.5",
            "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000:duration=1.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
        ], check=True, capture_output=True, timeout=30)
        source_probe = json.loads(subprocess.check_output([
            str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source),
        ], timeout=30))
        result = render_replacements(source, self.plan(), output, ffmpeg=ffmpeg, timeout=30)
        self.assertEqual(result["replacement_count"], 2)
        self.assertGreaterEqual(result["duration_ms"], 1500)
        self.assertLessEqual(result["duration_ms"], 1530)
        self.assertEqual(len(result["sha256"]), 64)
        probe = json.loads(subprocess.check_output([
            str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output),
        ], timeout=30))
        self.assertEqual({item["codec_type"] for item in probe["streams"]}, {"video", "audio"})
        video = next(item for item in probe["streams"] if item["codec_type"] == "video")
        source_video = next(item for item in source_probe["streams"] if item["codec_type"] == "video")
        self.assertEqual((video["width"], video["height"]), (320, 240))
        self.assertEqual(int(video.get("nb_frames") or 0), int(source_video.get("nb_frames") or 0))
        self.assertAlmostEqual(float(probe["format"]["duration"]),
                               float(source_probe["format"]["duration"]), delta=0.03)
        previous = output.read_bytes()
        invalid = self.plan(); invalid[1]["start_ms"] = 400
        with self.assertRaises(ValueError):
            render_replacements(source, invalid, output, ffmpeg=ffmpeg, timeout=30)
        self.assertEqual(output.read_bytes(), previous)
        with self.assertRaises(InterruptedError):
            render_replacements(source, self.plan(), output, ffmpeg=ffmpeg, timeout=30,
                                cancel_check=lambda: True)
        self.assertEqual(output.read_bytes(), previous)
        self.assertFalse(list(self.root.glob("*.pending.mp4")))
        self.assertFalse(list(self.root.glob("recorded-interaction-*")))


if __name__ == "__main__":
    unittest.main()
