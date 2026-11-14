import tempfile
import types
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from recovered import voice_clone_infer_api as clone_api


class VoiceClonePreparationTests(unittest.TestCase):
    def test_windows_directory_publish_retries_transient_media_lock(self):
        source = Path("source")
        target = Path("target")
        with patch.object(clone_api.os, "name", "nt"), \
                patch.object(Path, "replace", side_effect=[PermissionError("busy"), None]) as replace, \
                patch.object(clone_api.time, "sleep") as sleep:
            clone_api._replace_directory_with_retry(source, target)
        self.assertEqual(replace.call_count, 2)
        sleep.assert_called_once_with(0.1)

    def test_failed_normalization_preserves_existing_voice_and_cleans_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "坏音频.wav"
            source.write_bytes(b"not-wave")
            existing = root / "voices" / "中文音色"
            existing.mkdir(parents=True)
            (existing / "ref_text.txt").write_text("旧版本", encoding="utf-8")
            failed = types.SimpleNamespace(returncode=1, stderr=b"invalid media")

            with patch.object(clone_api, "_resolve_ffmpeg_executable", return_value="ffmpeg"), \
                    patch.object(clone_api.subprocess, "run", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                    clone_api.clone_voice_local(
                        str(source), "中文音色", str(root / "voices"), "asr", "zh")

            self.assertEqual((existing / "ref_text.txt").read_text(encoding="utf-8"), "旧版本")
            self.assertEqual(list((root / "voices").glob(".*.pending-*")), [])
            self.assertEqual(list((root / "voices").glob(".*.backup-*")), [])

    def test_success_replaces_voice_and_publishes_final_manifest_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "输入.wav"
            source.write_bytes(b"source")
            existing = root / "voices" / "中文音色"
            existing.mkdir(parents=True)
            (existing / "old.txt").write_text("old", encoding="utf-8")

            def normalize(command, **_kwargs):
                Path(command[-1]).write_bytes(b"RIFF-normalized")
                return types.SimpleNamespace(returncode=0, stderr=b"")

            with patch.object(clone_api, "_resolve_ffmpeg_executable", return_value="ffmpeg"), \
                    patch.object(clone_api.subprocess, "run", side_effect=normalize), \
                    patch.object(clone_api, "process_audio_batch",
                                 side_effect=lambda _model, paths, _lang: [(paths[0], " 新文本 ")]):
                result = Path(clone_api.clone_voice_local(
                    str(source), "中文音色", str(root / "voices"), "asr", "zh"))

            self.assertFalse((result / "old.txt").exists())
            self.assertEqual((result / "ref_text.txt").read_text(encoding="utf-8"), "新文本")
            manifest_text = (result / "slice_manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(manifest_text)
            self.assertEqual(manifest[0]["audio_path"], str(result / "normalized_input.wav"))
            self.assertNotIn("pending-", manifest_text)
            self.assertEqual(list((root / "voices").glob(".*.backup-*")), [])


if __name__ == "__main__":
    unittest.main()
