import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from scripts.console_comment_reply import ConsoleCommentReply, LLMError, generate_reply
from scripts.console_taobao import ConsoleTaobao


class AutomaticReplyTests(unittest.TestCase):
    def test_reply_uses_scene_language_for_prompt_and_synthesis(self):
        product = {'title': '茶杯', 'content': '容量300毫升'}
        binding = ('session', 0, 'voice', product, 'vi-VN')
        live = Mock()
        live.lock = threading.RLock()
        live.tts.lock = threading.RLock()
        live.reply_context.return_value = binding
        live.tts.state.side_effect = [None, {'id': 'speech', 'status': 'succeeded'}]
        live.tts.start_reply.return_value = {'id': 'speech'}
        live.session.queue_full.return_value = False
        replies = ConsoleCommentReply()
        with patch('recovered.llm_base_chat.base_chat', return_value='Dung tích 300 ml.') as model:
            replies._run(live, {'id': 1, 'content': 'Dung tích bao nhiêu?'}, (), binding, {})
        self.assertIn('用越南语', model.call_args.args[1])
        live.tts.start_reply.assert_called_once_with(product, 'voice', 'Dung tích 300 ml.', language='vi-VN')
        self.assertEqual(replies.state()['status'], 'queued')

    def test_reply_is_rejected_when_facts_expire_during_generation(self):
        product = {'title': '茶杯', 'content': '活动说明'}
        with patch('scripts.console_comment_reply.product_prompt_info', side_effect=[
            {'title': '茶杯', 'content': '活动有效'},
            {'title': '茶杯', 'content': '{}'},
        ]), patch('recovered.llm_base_chat.base_chat', return_value='活动仍有效') as model:
            with self.assertRaisesRegex(LLMError, '商品事实已到期'):
                generate_reply(product, '活动还有效吗', {})
            model.assert_called_once()

    def test_only_new_fresh_comments_are_dispatched_and_stop_invalidates_job(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = ConsoleTaobao(directory)
            capture.status = 'capturing'
            capture.capture_id = 'capture'
            capture.count = 1
            capture.comments.append({'id': 1, 'received_at': time.monotonic()})
            live = Mock()
            live.reply_context.return_value = ('session', 0, 'voice', {}, 'vi-VN')
            replies = ConsoleCommentReply()
            self.addCleanup(replies.close)
            dispatched = threading.Event()
            with patch('scripts.console_comment_reply.environment_config', return_value={}), patch.object(replies, 'start') as start:
                start.side_effect = lambda *args, **kwargs: dispatched.set()
                self.assertTrue(replies.start_automatic(capture, live)['automatic'])
                with capture.lock:
                    capture.comments.append({'id': 2, 'received_at': time.monotonic() - 31})
                    capture.comments.append({'id': 3, 'received_at': time.monotonic()})
                    capture.count = 3
                self.assertTrue(dispatched.wait(2))
                self.assertFalse(replies.stop_automatic()['automatic'])
                start.assert_called_once()
                self.assertEqual(start.call_args.args[2:], ('capture', 3))
                self.assertTrue(start.call_args.kwargs['automatic_stop'].is_set())
