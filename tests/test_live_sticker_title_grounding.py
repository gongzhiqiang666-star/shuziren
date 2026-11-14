import unittest
from unittest import mock

from recovered import live_sticker_titles as titles


class LiveStickerTitleGroundingTests(unittest.TestCase):
    def test_invalid_primary_title_falls_back_to_grounded_ark_titles(self):
        product = {"product_name": "青瓷杯", "product_content": "容量530毫升"}
        with mock.patch.object(titles, "base_chat", return_value='["99项优惠青瓷杯"]'), \
                mock.patch.object(titles, "_chat_ark", return_value='["530毫升青瓷杯","青瓷杯日常饮水","喝水泡茶青瓷杯"]'):
            result = titles.generate_room_titles(product, ark_api_key="test-key")
        self.assertEqual(result["title_model"], f"ark: {titles.ARK_TITLE_MODEL}")
        self.assertEqual(len(result["room_titles"]), 3)

    def test_both_providers_ungrounded_fail_with_provider_diagnostics(self):
        product = {"product_name": "青瓷杯"}
        with mock.patch.object(titles, "base_chat", return_value='["99项优惠"]'), \
                mock.patch.object(titles, "_chat_ark", return_value='["只要九十九元"]'):
            with self.assertRaisesRegex(ValueError, "llm_config.*ark"):
                titles.generate_room_titles(product, ark_api_key="test-key")

    def test_grounded_primary_does_not_call_ark(self):
        product = {"product_name": "青瓷杯", "product_price": "99元"}
        with mock.patch.object(titles, "base_chat", return_value='["青瓷杯99元","青瓷日常杯","喝水泡茶杯"]'), \
                mock.patch.object(titles, "_chat_ark") as ark:
            result = titles.generate_room_titles(product, ark_api_key="test-key")
        self.assertEqual(result["title_model"], "llm_config")
        ark.assert_not_called()


if __name__ == "__main__":
    unittest.main()
