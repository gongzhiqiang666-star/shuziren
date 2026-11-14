import unittest
from unittest import mock

from recovered.generate_title import generate_title_and_tags


class GenerateTitleValidationTests(unittest.TestCase):
    def generate(self, response):
        with mock.patch("recovered.generate_title.base_chat", return_value=response):
            return generate_title_and_tags("口播稿")

    def test_standard_json_deduplicates_and_normalizes_tags(self):
        result = self.generate('{"title":" 青瓷杯 ","tags":["#茶杯","茶杯","青瓷"]}')
        self.assertEqual(result, {"title": "青瓷杯", "tags": ["茶杯", "青瓷"]})

    def test_string_tags_are_rejected_instead_of_becoming_characters(self):
        with self.assertRaisesRegex(RuntimeError, "文本数组"):
            self.generate('{"title":"青瓷杯","tags":"茶杯"}')

    def test_non_text_title_and_nested_tags_are_rejected(self):
        for response in (
            '{"title":{"text":"青瓷杯"},"tags":[]}',
            '{"title":"青瓷杯","tags":[["茶杯"]]}',
        ):
            with self.subTest(response=response), self.assertRaises(RuntimeError):
                self.generate(response)

    def test_legacy_lightly_broken_json_still_recovers_title_and_tags(self):
        result = self.generate("{'title':'青瓷杯','tags':['茶杯','青瓷']}")
        self.assertEqual(result, {"title": "青瓷杯", "tags": ["茶杯", "青瓷"]})


if __name__ == "__main__":
    unittest.main()
