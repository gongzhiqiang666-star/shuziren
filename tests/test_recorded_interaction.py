from pathlib import Path
import tempfile
import unittest

from pydub import AudioSegment
from pydub.generators import Sine

from scripts.recorded_interaction import mix_replacements, validate_replacements


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


if __name__ == "__main__":
    unittest.main()
