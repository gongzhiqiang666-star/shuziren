import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def test_runtime_map_names_every_required_stage(self):
        path = PROJECT / "docs/evidence/v122-runtime-map.md"
        self.assertTrue(path.is_file())
        source = path.read_text(encoding="utf-8")
        for stage in (
            "environment",
            "avatar_preprocess",
            "voice_generate",
            "avatar_drive",
            "mp4_output",
        ):
            with self.subTest(stage=stage):
                self.assertIn(f"`{stage}`", source)
        for field in ("入口", "输入", "输出", "证据", "置信状态"):
            with self.subTest(field=field):
                self.assertIn(field, source)


if __name__ == "__main__":
    unittest.main()
