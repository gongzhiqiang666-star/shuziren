import unittest
from unittest import mock

from recovered import replace_forbidden_words as replacement


class ForbiddenWordsBoundaryTests(unittest.TestCase):
    def test_empty_catalog_entry_is_not_registered_or_matched(self):
        registered = []
        with mock.patch.object(replacement.jieba, "initialize"), \
                mock.patch.object(replacement.jieba, "add_word", side_effect=registered.append), \
                mock.patch.object(replacement.jieba, "cut", side_effect=lambda text: [text]):
            result = replacement.replace_forbidden_words("普通描述", ["", None, "   "])
        self.assertEqual(result, "普通描述")
        self.assertNotIn("", registered)

    def test_ascii_words_are_replaced_case_insensitively(self):
        self.assertNotIn("qq", replacement.replace_forbidden_words("请加qq联系").lower())
        self.assertEqual(replacement.replace_forbidden_words("Super SALE now", ["sale"]), "Super **** now")

    def test_overlapping_user_words_use_longest_first(self):
        result = replacement.replace_forbidden_words("领取优惠券", ["优惠", "优惠券"])
        self.assertEqual(result, "领取***")


if __name__ == "__main__":
    unittest.main()
