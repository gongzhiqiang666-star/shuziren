import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recovered.main import Api


class AudioClipApiTests(unittest.TestCase):
    def test_uses_available_asr_path_and_isolates_each_output(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Path(root)
            model = runtime / "assets" / "pretrained_models" / "asr"
            model.mkdir(parents=True)
            source = runtime / "source.mp3"
            source.write_bytes(b"media")
            api = Api.__new__(Api)
            api.runtime_dir = runtime
            calls = []

            def split(file_path, output_dir, asr_weight_path, **options):
                output = Path(output_dir)
                output.mkdir(parents=True)
                (output / "segment_0001.wav").write_bytes(b"wav")
                calls.append((Path(file_path), output, Path(asr_weight_path), options))
                return [{"audio_path": str(output / "segment_0001.wav"), "text": "文本"}]

            with mock.patch("recovered.audio_clip.process_and_split_audio", side_effect=split):
                first = api.process_audio_clip(source, 4, 10)
                second = api.process_audio_clip(source, 4, 10)
            self.assertEqual((first["status"], second["status"]), ("success", "success"))
            self.assertNotEqual(first["output_dir"], second["output_dir"])
            self.assertEqual([call[2] for call in calls], [model.resolve(), model.resolve()])
            self.assertEqual(calls[0][3], {"min_seconds": 4, "max_seconds": 10})

    def test_failed_task_removes_only_its_own_output(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Path(root)
            (runtime / "assets" / "pretrained_models" / "asr").mkdir(parents=True)
            source = runtime / "source.wav"
            source.write_bytes(b"media")
            preserved = runtime / "utils" / "audio_clip" / "temp" / "other-task"
            preserved.mkdir(parents=True)
            (preserved / "keep.txt").write_text("keep", encoding="utf-8")
            api = Api.__new__(Api)
            api.runtime_dir = runtime
            failed_output = []

            def fail(_source, output_dir, _model, **_options):
                output = Path(output_dir)
                output.mkdir(parents=True)
                (output / "partial.wav").write_bytes(b"partial")
                failed_output.append(output)
                raise RuntimeError("识别失败")

            with mock.patch("recovered.audio_clip.process_and_split_audio", side_effect=fail):
                result = api.process_audio_clip(source)
            self.assertEqual(result, {"status": "error", "message": "识别失败"})
            self.assertFalse(failed_output[0].exists())
            self.assertEqual((preserved / "keep.txt").read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
