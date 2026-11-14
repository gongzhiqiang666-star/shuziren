import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recovered import douyin_benchmark
from recovered.main import Api


class DouyinBenchmarkTests(unittest.TestCase):
    def test_normalizes_official_url_from_share_text(self):
        self.assertEqual(
            douyin_benchmark.normalize_douyin_url("复制口令 https://v.douyin.com/abc123/ 打开抖音"),
            "https://v.douyin.com/abc123/",
        )
        for value in ("http://v.douyin.com/a", "https://evil.example/video", "没有链接"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                douyin_benchmark.normalize_douyin_url(value)

    def test_selects_only_nonempty_video_inside_tool_directory(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside_root:
            directory = Path(root)
            video = directory / "output.mp4"
            video.write_bytes(b"video")
            outside = Path(outside_root) / "secret.mp4"
            outside.write_bytes(b"secret")
            output = f"log\n{outside}\noutput.mp4\n"
            self.assertEqual(douyin_benchmark.select_downloaded_video(output, directory), video.resolve())
            with self.assertRaises(RuntimeError):
                douyin_benchmark.select_downloaded_video(str(outside), directory)

    def test_probe_requires_decodable_video_track(self):
        success = mock.Mock(returncode=0, stdout='{"streams":[{"codec_type":"video"}],"format":{"duration":"1.2"}}')
        with mock.patch.object(douyin_benchmark.subprocess, "run", return_value=success):
            payload = douyin_benchmark.probe_video("video.mp4", "ffprobe.exe")
        self.assertEqual(payload["streams"][0]["codec_type"], "video")
        audio_only = mock.Mock(returncode=0, stdout='{"streams":[{"codec_type":"audio"}]}')
        with mock.patch.object(douyin_benchmark.subprocess, "run", return_value=audio_only), self.assertRaises(ValueError):
            douyin_benchmark.probe_video("audio.mp4", "ffprobe.exe")

    def test_project_archive_replaces_complete_benchmark_directory(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root) / "project"
            project.mkdir()
            old = project / "benchmark"
            old.mkdir()
            (old / "stale.txt").write_text("stale", encoding="utf-8")
            source = Path(root) / "download.mp4"
            source.write_bytes(b"video")
            api = Api.__new__(Api)
            api._get_ip_agent_project_dir = lambda project_id: str(project)
            api._load_ip_agent_project = lambda project_id: {"id": project_id}
            api.extract_douyin_benchmark = lambda url: {
                "status": "success", "video_path": str(source), "text": "转写内容",
                "source_url": "https://v.douyin.com/id/",
            }
            api._save_ip_agent_project = lambda project_id, info: info
            result = api.extract_ip_agent_benchmark("project-1", "share")
            self.assertEqual(result["status"], "success")
            self.assertEqual((old / "对标文案.txt").read_text(encoding="utf-8"), "转写内容")
            self.assertEqual((old / "对标视频.mp4").read_bytes(), b"video")
            self.assertFalse((old / "stale.txt").exists())
            self.assertFalse((project / ".benchmark-backup").exists())


if __name__ == "__main__":
    unittest.main()
