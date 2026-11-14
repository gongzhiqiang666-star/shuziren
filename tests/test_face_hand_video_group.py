import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from recovered.face_hand_video_group import (
    load_face_hand_video_group,
    validate_face_hand_video_group,
)


class FaceHandVideoGroupTests(unittest.TestCase):
    def test_legacy_avi_and_manifest_entries_are_loaded(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "face").mkdir()
            (root / "hand").mkdir()
            (root / "face" / "legacy.AVI").write_bytes(b"legacy-face")
            (root / "hand" / "hand.mp4").write_bytes(b"legacy-hand")

            with patch(
                    "recovered.face_hand_video_group._probe_video_file",
                    return_value=(True, "")):
                valid, error, counts = validate_face_hand_video_group(root)
            self.assertTrue(valid, error)
            self.assertEqual(counts, {"face_count": 1, "hand_count": 1})
            group = load_face_hand_video_group(root)
            self.assertTrue(group["face"][0].lower().endswith("legacy.avi"))

    def test_empty_clip_is_rejected_before_broadcast(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "face").mkdir()
            (root / "hand").mkdir()
            (root / "face" / "empty.mp4").touch()
            (root / "hand" / "hand.mp4").write_bytes(b"hand")

            valid, error, counts = validate_face_hand_video_group(root)
            self.assertFalse(valid)
            self.assertIn("空的 face 素材", error)
            self.assertEqual(counts["face_count"], 1)

    def test_bad_manifest_and_missing_group_have_stable_errors(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "manifest.json").write_text("[]", encoding="utf-8")
            valid, error, counts = validate_face_hand_video_group(root)
            self.assertFalse(valid)
            self.assertIn("manifest 格式错误", error)
            self.assertEqual(counts, {})

            valid, error, counts = validate_face_hand_video_group(root / "missing")
            self.assertFalse(valid)
            self.assertIn("视频组目录不存在", error)
            self.assertEqual(counts, {})

    def test_nonempty_but_undecodable_clip_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "face").mkdir()
            (root / "hand").mkdir()
            (root / "face" / "broken.mp4").write_bytes(b"not-a-video")
            (root / "hand" / "hand.mp4").write_bytes(b"also-not-a-video")

            with patch(
                    "recovered.face_hand_video_group._probe_video_file",
                    return_value=(False, "视频素材无法解码：broken.mp4")):
                valid, error, _ = validate_face_hand_video_group(root)
            self.assertFalse(valid)
            self.assertEqual(error, "face 视频素材无法解码：broken.mp4")


if __name__ == "__main__":
    unittest.main()
