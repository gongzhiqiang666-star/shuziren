import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from scripts.console_comment_reply import ConsoleCommentReply
from scripts.console_taobao import ConsoleTaobao


class AutomaticReplyTests(unittest.TestCase):
    def test_only_new_fresh_comments_are_dispatched_and_stop_invalidates_job(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = ConsoleTaobao(directory)
            capture.status = 'capturing'
            capture.capture_id = 'capture'
            capture.count = 1
            capture.comments.append({'id': 1, 'received_at': time.monotonic()})
            live = Mock()
            live.reply_context.return_value = ('session', 0, 'voice', {})
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
