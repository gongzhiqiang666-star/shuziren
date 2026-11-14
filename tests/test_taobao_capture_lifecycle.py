from threading import Event, current_thread
import unittest
from unittest.mock import Mock, patch

from recovered.taobao_control_capture import TaobaoControlDanmuCapture
from recovered.taobao_live_control import TaobaoLiveControl, _wait_taobao_login_with_cancel


class TaobaoCaptureLifecycleTests(unittest.TestCase):
    def test_login_wait_stops_at_configured_deadline(self):
        page = Mock(url='https://login.taobao.com/')
        with patch('recovered.taobao_live_control.time.monotonic', side_effect=[10, 10, 12]):
            with self.assertRaises(TimeoutError):
                _wait_taobao_login_with_cancel(page, target_url='https://liveplatform.taobao.com/list',
                                               timeout_sec=2, cancel=Event())
        page.wait_for_timeout.assert_called_once_with(250)

    def test_login_wait_stops_when_cancelled_between_polls(self):
        cancel = Event()
        page = Mock(url='https://login.taobao.com/')
        page.wait_for_timeout.side_effect = lambda _: cancel.set()
        with self.assertRaises(InterruptedError):
            _wait_taobao_login_with_cancel(page, target_url='https://liveplatform.taobao.com/list',
                                           timeout_sec=600, cancel=cancel)
        page.wait_for_timeout.assert_called_once_with(250)

    def test_goods_id_prefers_label_over_numeric_product_name(self):
        item = Mock()
        item.inner_text.return_value = '20261111 纪念款 ID:123456789 开始讲解'
        self.assertEqual(TaobaoLiveControl._read_goods_id(item), 123456789)

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

    def test_owned_capture_recreates_browser_session_after_disconnect(self):
        first = Mock()
        first.open_control_page.return_value = True
        first.connected.return_value = False
        first.fetch_comments.side_effect = OSError('browser closed')
        second = Mock()
        second.open_control_page.return_value = True
        second.connected.return_value = True
        second.fetch_comments.return_value = [
            {'content': 'reconnected', 'nickname': 'buyer', 'time': '10:00'}]
        capture = TaobaoControlDanmuCapture._configured(
            storage_state='state.json', poll_interval_sec=0, prime_existing=False)
        with patch('recovered.taobao_control_capture.TaobaoLiveControl', side_effect=[first, second]), \
                self.assertLogs('recovered.taobao_control_capture', 'ERROR'):
            stream = iter(capture)
            capture.start()
            self.assertEqual(next(stream)['content'], 'reconnected')
            capture.stop()
            self.assertEqual(list(stream), [])
        first._connect_configured.assert_called_once_with(storage_state='state.json')
        second._connect_configured.assert_called_once_with(storage_state='state.json')
        first.shutdown.assert_called_once_with()
        second.shutdown.assert_called_once_with()

    def test_login_expiry_is_not_retried_forever(self):
        controller = Mock()
        controller._connect_configured.side_effect = __import__(
            'recovered.taobao_live_control', fromlist=['TaobaoLoginRequired']).TaobaoLoginRequired('login expired')
        capture = TaobaoControlDanmuCapture._configured(poll_interval_sec=0)
        capture.start()
        with patch('recovered.taobao_control_capture.TaobaoLiveControl', return_value=controller):
            with self.assertRaisesRegex(Exception, 'login expired'):
                next(iter(capture))
        controller.shutdown.assert_called_once_with()
