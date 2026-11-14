import unittest
from unittest import mock

from recovered import llm_base_chat, llm_reply


class TranslationGroundingTests(unittest.TestCase):
    def test_han_output_retries_instead_of_silently_deleting_text(self):
        responses = ["容量是530毫升。", "The capacity is 530 millilitres."]
        with mock.patch.object(llm_base_chat, "base_chat", side_effect=responses) as chat:
            result = llm_reply.translate_text_llm("容量是530毫升。", "en-US", raise_on_failure=True)
        self.assertEqual(result, responses[1])
        self.assertEqual(chat.call_count, 2)

    def test_changed_number_retries_and_preserves_original_number(self):
        responses = ["The capacity is 500 millilitres.", "The capacity is 530 millilitres."]
        with mock.patch.object(llm_base_chat, "base_chat", side_effect=responses):
            result = llm_reply.translate_text_llm("容量是530毫升。", "en-US", raise_on_failure=True)
        self.assertIn("530", result)
        self.assertNotIn("500", result)

    def test_two_invalid_outputs_fail_without_partial_translation(self):
        with mock.patch.object(llm_base_chat, "base_chat", return_value="还是中文530毫升"):
            with self.assertRaisesRegex(RuntimeError, "禁止的中文"):
                llm_reply.translate_text_llm("容量是530毫升。", "vi-VN", raise_on_failure=True)


if __name__ == "__main__":
    unittest.main()
