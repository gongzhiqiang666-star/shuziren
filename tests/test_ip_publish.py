import tempfile
import threading
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from recovered.ip_publish import build_publish_plan
from recovered.main import Api


class IpPublishTests(unittest.TestCase):
    @staticmethod
    def _uploader_modules(function):
        tools_module = types.ModuleType("tools")
        tools_module.__path__ = []
        package = types.ModuleType("tools.social_auto_upload")
        package.__path__ = []
        module = types.ModuleType("tools.social_auto_upload.test")
        module.publish_video_to_platforms = function
        tools_module.social_auto_upload = package
        package.test = module
        return {"tools": tools_module, "tools.social_auto_upload": package,
                "tools.social_auto_upload.test": module}, module

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

    def test_uploader_failure_is_persisted_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            state = {"name": "项目", "final_video_path": str(video)}
            api = self._api(root, state)
            api._load_ip_agent_project = lambda project_id: dict(state)
            api._save_ip_agent_project = lambda project_id, value: state.update(value) or dict(state)

            async def fail_upload(**kwargs):
                raise RuntimeError("登录已失效")

            modules, module = self._uploader_modules(fail_upload)
            with mock.patch.dict("sys.modules", modules), \
                    mock.patch("recovered.douyin_benchmark.resolve_ffprobe", return_value="ffprobe"), \
                    mock.patch("recovered.douyin_benchmark.probe_video"):
                result = api.publish_ip_agent_video("id", {"platforms": ["douyin"]})
            self.assertEqual(result["status"], "error")
            self.assertIn("publish_task", state, result)
            self.assertEqual(state["publish_task"]["status"], "failed")
            self.assertIn("登录已失效", state["publish_task"]["error"])
            self.assertEqual(len(state["publish_attempts"]), 1)

            async def succeed_upload(**kwargs):
                return {"success": True, "results": {"douyin": {"success": True}}}

            module.publish_video_to_platforms = succeed_upload
            with mock.patch.dict("sys.modules", {"tools.social_auto_upload.test": module}), \
                    mock.patch("recovered.douyin_benchmark.resolve_ffprobe", return_value="ffprobe"), \
                    mock.patch("recovered.douyin_benchmark.probe_video"):
                retried = api.publish_ip_agent_video("id", {"platforms": ["douyin"]})
            self.assertEqual(retried["status"], "success")
            self.assertEqual(state["publish_task"]["status"], "success")
            self.assertEqual([item["status"] for item in state["publish_attempts"]], ["failed", "success"])

    def test_concurrent_publish_for_same_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / "video.mp4"
            video.write_bytes(b"video")
            state = {"name": "项目", "final_video_path": str(video)}
            api = self._api(root, state)
            api._load_ip_agent_project = lambda project_id: dict(state)
            api._save_ip_agent_project = lambda project_id, value: state.update(value) or dict(state)
            entered = threading.Event()
            release = threading.Event()

            async def wait_upload(**kwargs):
                entered.set()
                release.wait(5)
                return {"success": True, "results": {"douyin": {"success": True}}}

            modules, module = self._uploader_modules(wait_upload)
            results = []
            patches = [mock.patch.dict("sys.modules", modules),
                       mock.patch("recovered.douyin_benchmark.resolve_ffprobe", return_value="ffprobe"),
                       mock.patch("recovered.douyin_benchmark.probe_video")]
            for item in patches:
                item.start()
            try:
                worker = threading.Thread(target=lambda: results.append(
                    api.publish_ip_agent_video("id", {"platforms": ["douyin"]})))
                worker.start()
                self.assertTrue(entered.wait(2), results)
                duplicate = api.publish_ip_agent_video("id", {"platforms": ["douyin"]})
                self.assertEqual(duplicate.get("code"), "publish_in_progress")
                release.set()
                worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(results[0]["status"], "success")
            finally:
                release.set()
                for item in reversed(patches):
                    item.stop()


if __name__ == "__main__":
    unittest.main()
