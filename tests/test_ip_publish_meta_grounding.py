import unittest
from unittest import mock

from recovered.main import Api


class IpPublishMetaGroundingTests(unittest.TestCase):
    def api(self):
        api = Api.__new__(Api)
        api._load_ip_agent_project = lambda _project_id: {
            "rewritten_script": "青瓷杯容量530毫升，适合日常喝水泡茶。",
            "benchmark_url": "https://example.invalid/video",
        }
        api.saved = []
        api._save_ip_agent_project = lambda project_id, data: api.saved.append((project_id, data)) or data
        return api

    def test_ungrounded_title_returns_error_without_saving_project(self):
        api = self.api()
        with mock.patch("recovered.generate_title.base_chat", return_value='{"title":"99人都在买","tags":["青瓷杯"]}'):
            result = api.generate_ip_agent_publish_meta("project", {})
        self.assertIn("不存在的数字", result["error"])
        self.assertEqual(api.saved, [])

    def test_grounded_title_and_tags_save_only_native_fields(self):
        api = self.api()
        with mock.patch("recovered.generate_title.base_chat", return_value='{"title":"530毫升青瓷杯","tags":["#青瓷杯","日常饮水"]}'):
            result = api.generate_ip_agent_publish_meta("project", {})
        self.assertEqual(result["status"], "success")
        self.assertEqual(api.saved, [("project", {
            "publish_title": "530毫升青瓷杯",
            "publish_tags_text": "#青瓷杯 #日常饮水",
        })])


if __name__ == "__main__":
    unittest.main()
