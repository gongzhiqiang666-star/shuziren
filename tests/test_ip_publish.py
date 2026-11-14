import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from recovered.ip_publish import build_publish_plan
from recovered.main import Api


class IpPublishTests(unittest.TestCase):
    def _api(self, root, info):
        api = Api.__new__(Api)
        api.runtime_dir = Path(root)
        api._load_ip_agent_project = lambda project_id: dict(info)
        api._save_ip_agent_project = lambda project_id, value: value
        return api

    def test_plan_normalizes_platform_accounts_tags_and_stable_id(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            first = build_publish_plan(video, " 标题 ", ["#标签", "标签"],
                                       ["Douyin", "douyin", "kuaishou"], {"douyin": "account_1"})
            second = build_publish_plan(video, "标题", ["标签"],
                                        ["douyin", "kuaishou"], {"douyin": "account_1"})
            self.assertEqual(first["platforms"], ["douyin", "kuaishou"])
            self.assertEqual(first["account_names"], {"douyin": "account_1", "kuaishou": "default"})
            self.assertEqual(first["request_id"], second["request_id"])

    def test_rejects_unknown_platform_path_like_account_and_bad_content(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            with self.assertRaisesRegex(ValueError, "不支持"):
                build_publish_plan(video, "标题", [], ["unknown"])
            with self.assertRaisesRegex(ValueError, "账号"):
                build_publish_plan(video, "标题", [], ["douyin"], {"douyin": "../cookie"})
            with self.assertRaisesRegex(ValueError, "标题"):
                build_publish_plan(video, "", [], ["douyin"])
            with self.assertRaisesRegex(ValueError, "标签"):
                build_publish_plan(video, "标题", [str(index) for index in range(21)], ["douyin"])

    def test_schedule_must_be_future_and_thumbnail_must_exist(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            plan = build_publish_plan(video, "标题", [], ["douyin"], publish_date=future.isoformat())
            self.assertEqual(plan["publish_date_value"], future)
            with self.assertRaisesRegex(ValueError, "晚于"):
                build_publish_plan(video, "标题", [], ["douyin"], publish_date="2020-01-01T00:00:00Z")
            with self.assertRaisesRegex(FileNotFoundError, "封面"):
                build_publish_plan(video, "标题", [], ["douyin"], thumbnail_path=Path(root) / "missing.png")

    def test_api_dry_run_validates_media_without_loading_uploader(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            api = self._api(root, {"name": "项目", "final_video_path": str(video)})
            with mock.patch("recovered.douyin_benchmark.resolve_ffprobe", return_value="ffprobe"), \
                    mock.patch("recovered.douyin_benchmark.probe_video") as probe:
                result = api.publish_ip_agent_video("id", {"platforms": ["douyin"], "dry_run": True})
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["publish_plan"]["platforms"], ["douyin"])
            probe.assert_called_once()

    def test_api_returns_previous_success_for_same_request(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            plan = build_publish_plan(video, "项目", [], ["douyin"])
            previous = {"success": True, "results": {"douyin": {"success": True}}}
            api = self._api(root, {"name": "项目", "final_video_path": str(video),
                                   "publish_last_request_id": plan["request_id"],
                                   "publish_last_result": previous})
            with mock.patch("recovered.douyin_benchmark.resolve_ffprobe", return_value="ffprobe"), \
                    mock.patch("recovered.douyin_benchmark.probe_video"):
                result = api.publish_ip_agent_video("id", {"platforms": ["douyin"]})
            self.assertTrue(result["already_published"])
            self.assertEqual(result["publish_result"], previous)


if __name__ == "__main__":
    unittest.main()
