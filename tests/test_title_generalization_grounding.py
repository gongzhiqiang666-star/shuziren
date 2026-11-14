import unittest
from unittest import mock

from recovered import generalize_sentences, generate_title


class TitleGeneralizationGroundingTests(unittest.TestCase):
    def test_title_rejects_invented_number_and_price(self):
        for response in (
            '{"title":"99人都在买的青瓷杯","tags":["茶杯"]}',
            '{"title":"青瓷杯","tags":["只要九十九元"]}',
        ):
            with self.subTest(response=response), \
                    mock.patch.object(generate_title, "base_chat", return_value=response):
                with self.assertRaises(RuntimeError):
                    generate_title.generate_title_and_tags("青瓷杯，容量530毫升")

    def test_title_allows_numbers_and_price_already_in_script(self):
        response = '{"title":"530毫升青瓷杯99元","tags":["青瓷杯"]}'
        with mock.patch.object(generate_title, "base_chat", return_value=response):
            result = generate_title.generate_title_and_tags("青瓷杯容量530毫升，资料价格99元")
        self.assertIn("530", result["title"])

    def test_generalization_retries_invented_claim(self):
        responses = ["这款杯子有99项优惠。", "这款杯子容量530毫升，日常使用方便。"]
        with mock.patch.object(generalize_sentences, "optimize_script", side_effect=responses) as optimize, \
                mock.patch.object(generalize_sentences.RateLimiter, "wait_if_needed"):
            result = generalize_sentences.generalize_sentences("这款杯子容量530毫升。", variations=1)
        self.assertIn(responses[1], result)
        self.assertEqual(optimize.call_count, 2)


if __name__ == "__main__":
    unittest.main()
