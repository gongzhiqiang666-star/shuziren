from threading import current_thread
import unittest
from unittest.mock import Mock

from recovered.taobao_control_capture import TaobaoControlDanmuCapture
from recovered.taobao_live_control import TaobaoLiveControl


class TaobaoCaptureLifecycleTests(unittest.TestCase):
    def test_control_page_is_accessed_on_the_owning_thread(self):
        controller = TaobaoLiveControl()
        self.addCleanup(controller.shutdown)
        seen = []

        class Page:
            def is_closed(self):
                return True

            @property
            def url(self):
                seen.append(current_thread())
                return 'https://liveplatform.taobao.com/restful/index/live/control?liveId=123456'

        controller._page = Page()
        self.assertTrue(controller.open_control_page('123456'))
        self.assertEqual(seen, [controller._thread])

    def test_initial_and_recovered_snapshots_are_not_replayed(self):
        old = {'content': 'old', 'nickname': 'a'}
        missed = {'content': 'missed', 'nickname': 'b'}
        fresh = {'content': 'fresh', 'nickname': 'c'}
        controller = Mock()
        controller.fetch_comments.side_effect = [[old], OSError('interrupted'), [old, missed], [old, missed, fresh]]
        capture = TaobaoControlDanmuCapture._configured(controller=controller, poll_interval_sec=0, prime_existing=True)
        capture.start()
        with self.assertLogs('recovered.taobao_control_capture', 'ERROR'):
            stream = iter(capture)
            self.assertEqual(next(stream)['content'], 'fresh')
            capture.stop()
            self.assertEqual(list(stream), [])
