import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

from recovered.main import Api
from recovered.audio_clip import process_and_split_audio


class AudioClipApiTests(unittest.TestCase):
    def test_split_writes_atomic_hash_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / "source.mp3"
            source.write_bytes(b"source-media")
            output = root / "output"
            model = root / "asr"
            model.mkdir()
            cleaned = []

            def run(command, **_kwargs):
                target = Path(command[-1])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(("media:" + target.name).encode("utf-8"))
                return mock.Mock(returncode=0)

            runtime = (lambda path: {"model": path},
                       lambda _model, _path: [{"sentence_info": [
                           {"text": "第一句", "start": 0, "end": 4500},
                           {"text": "第二句", "start": 7500, "end": 12000},
                       ]}],
                       lambda value: cleaned.append(value))
            with mock.patch("recovered.audio_clip.shutil.which", return_value="ffmpeg"), \
                    mock.patch("recovered.audio_clip.subprocess.run", side_effect=run), \
                    mock.patch("recovered.audio_clip._runtime_functions", return_value=runtime):
                files = process_and_split_audio(source, output, model, 4, 10)
            self.assertEqual(len(files), 2)
            manifest_path = output / "manifest.json"
            self.assertTrue(manifest_path.is_file())
            self.assertFalse((output / ".manifest.json.pending").exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_name"], "source.mp3")
            self.assertEqual(len(manifest["source_sha256"]), 64)
            self.assertEqual([(item["start"], item["end"]) for item in manifest["segments"]],
                             [(0, 4500), (7500, 12000)])
            self.assertTrue(all(len(item["audio_sha256"]) == 64 and len(item["text_sha256"]) == 64
                                for item in manifest["segments"]))
            self.assertEqual(cleaned, [{"model": str(model)}])

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
