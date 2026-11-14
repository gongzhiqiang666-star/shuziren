import json
import unittest
from unittest import mock

from recovered.main import Api


class IpRewriteGroundingTests(unittest.TestCase):
    def api(self):
        api = Api.__new__(Api)
        api.config = {"llm_config": {"vendor": "test"}}
        return api

    def rewrite(self, response, original="这款杯子容量530毫升，青瓷材质。"):
        with mock.patch("recovered.llm_base_chat.base_chat", return_value=json.dumps(response, ensure_ascii=False)):
            return self.api().rewrite_ip_script({"text": original})

    def test_any_version_with_invented_number_rejects_whole_result(self):
        result = self.rewrite({"versions": [
            {"name": "事实版", "text": "这款杯子容量530毫升，青瓷材质。"},
            {"name": "编造版", "text": "这款杯子有99项优惠，赶紧看看。"},
        ]})
        self.assertIn("不存在的数字", result["error"])
        self.assertNotIn("versions", result)

    def test_fallback_text_with_invented_price_is_rejected(self):
        result = self.rewrite({"rewritten_text": "这款杯子现在九十九元，适合日常使用。"})
        self.assertIn("不存在的价格", result["error"])

    def test_all_grounded_versions_and_analysis_are_preserved(self):
        response = {
            "analysis": {"hook": "容量切入"},
            "versions": [
                {"name": "容量版", "text": "530毫升容量，青瓷材质，日常使用很方便。"},
                {"name": "口语版", "text": "青瓷杯容量530毫升，喝水泡茶都合适。"},
            ],
            "keywords": ["青瓷", "容量"],
        }
        result = self.rewrite(response)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["analysis"], response["analysis"])
        self.assertEqual(result["versions"], response["versions"])


if __name__ == "__main__":
    unittest.main()
