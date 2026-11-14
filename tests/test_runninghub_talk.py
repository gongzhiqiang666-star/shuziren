import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recovered import runninghub_talk
from recovered.main import Api


class DownloadResponse:
    def __init__(self, chunks, declared=0):
        self.chunks = chunks
        self.headers = {"Content-Length": str(declared)} if declared else {}

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def raise_for_status(self): return None
    def iter_content(self, _size): return iter(self.chunks)


class RunningHubTalkTests(unittest.TestCase):
    def test_completed_without_url_is_not_success(self):
        response = unittest.mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"code": 0, "data": {"status": "COMPLETED", "outputs": []}}
        with patch.object(runninghub_talk.requests, "post", return_value=response):
            self.assertEqual(runninghub_talk.query_talk_task(api_key="key", task_id="task")["status"], "queued")

    def test_download_is_https_bounded_validated_and_atomic(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "video.mp4"
            target.write_bytes(b"old")
            with self.assertRaises(ValueError):
                runninghub_talk.download_file("http://example.test/video.mp4", target)
            invalid = DownloadResponse([b"not a movie payload"])
            with patch.object(runninghub_talk.requests, "get", return_value=invalid):
                with self.assertRaises(RuntimeError):
                    runninghub_talk.download_file("https://example.test/video.mp4", target)
            self.assertEqual(target.read_bytes(), b"old")
            oversized = DownloadResponse([b"\0\0\0\x18ftypmp42"], declared=100)
            with patch.object(runninghub_talk.requests, "get", return_value=oversized), \
                    patch.object(runninghub_talk, "MAX_DOWNLOAD_BYTES", 20):
                with self.assertRaises(RuntimeError):
                    runninghub_talk.download_file("https://example.test/video.mp4", target)
            valid = DownloadResponse([b"\0\0\0\x18ftypmp42" + b"x" * 32])
            with patch.object(runninghub_talk.requests, "get", return_value=valid):
                runninghub_talk.download_file("https://example.test/video.mp4", target)
            self.assertIn(b"ftyp", target.read_bytes()[:32])
            self.assertFalse(list(Path(root).glob("*.partial")))

    def test_poll_bounds_are_rejected_before_upload(self):
        with patch.object(runninghub_talk, "upload_file") as upload:
            with self.assertRaises(ValueError):
                runninghub_talk.generate_talk_video(api_key="key", image_path="a", audio_path="b",
                                                    dest="c", poll_interval=-1)
            upload.assert_not_called()

    def test_cloud_project_archives_only_after_new_video_is_ready(self):
        with tempfile.TemporaryDirectory() as root:
            api = Api.__new__(Api); api.runtime_dir = Path(root); api.config = {"runninghub_api_key": "key"}
            project = api.create_cloud_dh_project("test")["project"]
            outputs = api._get_cloud_dh_output_paths(project["id"])
            Path(outputs["avatar"]).write_bytes(b"png")
            Path(outputs["audio"]).write_bytes(b"wav")
            Path(outputs["video"]).write_bytes(b"old-video")

            def fail(**_kwargs):
                raise RuntimeError("network failed")
            with patch.object(runninghub_talk, "generate_talk_video", side_effect=fail):
                result = api.generate_cloud_dh_video({"project_id": project["id"]})
            self.assertEqual(result["status"], "error")
            self.assertEqual(Path(outputs["video"]).read_bytes(), b"old-video")
            self.assertFalse(list(Path(outputs["video"]).parent.glob("*.pending.mp4")))
            self.assertFalse(Path(api._get_cloud_dh_history_dir(project["id"])).exists())

            def succeed(**kwargs):
                Path(kwargs["dest"]).write_bytes(b"\0\0\0\x18ftypmp42-new")
                return {"task_id": "task-1", "status": "success", "video_path": str(kwargs["dest"])}
            with patch.object(runninghub_talk, "generate_talk_video", side_effect=succeed):
                result = api.generate_cloud_dh_video({"project_id": project["id"]})
            self.assertEqual(result["status"], "success")
            self.assertIn(b"ftyp", Path(outputs["video"]).read_bytes())
            archived = list(Path(api._get_cloud_dh_history_dir(project["id"])).glob("*/数字人口播.mp4"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_bytes(), b"old-video")


if __name__ == "__main__":
    unittest.main()
