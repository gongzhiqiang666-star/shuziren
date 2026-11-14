import unittest
from unittest import mock

from recovered import generate_structured_speech as speech


class StructuredSpeechGroundingTests(unittest.TestCase):
    def test_invented_number_retries_then_accepts_grounded_claim(self):
        responses = [
            "这款杯子容量足，今天给大家准备了99个优惠名额。",
            "这款杯子容量是530毫升，青瓷材质，日常喝水泡茶都方便。",
        ]
        with mock.patch.object(speech, "base_chat", side_effect=responses) as chat:
            result = speech.generate_structured_speech({"容量": "530毫升", "材质": "青瓷"})
        self.assertIn("530毫升", result)
        self.assertEqual(chat.call_count, 2)

    def test_price_is_rejected_when_product_has_no_price(self):
        response = "这款青瓷杯现在只要九十九元，容量够用，日常泡茶很方便。"
        with mock.patch.object(speech, "base_chat", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "不存在的价格"):
                speech.generate_structured_speech({"容量": "530毫升", "材质": "青瓷"})

    def test_supplied_price_and_numbers_are_allowed(self):
        response = "这款杯子容量530毫升，商品资料标价99元，青瓷材质适合日常使用。"
        with mock.patch.object(speech, "base_chat", return_value=response):
            result = speech.generate_structured_speech({"容量": "530毫升", "价格": "99元"})
        self.assertEqual(result, response)


if __name__ == "__main__":
    unittest.main()
