import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from scripts.console_live import ConsoleLive


class LiveRotationTests(unittest.TestCase):
    def test_live_start_validates_and_binds_assistant_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            live = ConsoleLive(tts, directory)
            with patch('scripts.console_live.threading.Thread') as worker:
                state = live.start(14, assistant_voice_id='assistant')
            tts.voices.get.assert_called_once_with('assistant')
            worker.return_value.start.assert_called_once()
            self.assertEqual(state['assistant_voice_id'], 'assistant')

    def test_failed_rotation_requires_new_request_and_never_enqueues_old_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            tts=Mock()
            tts.lock=threading.RLock()
            tts.products.get.return_value={'id':'product','title':'测试商品','version':1}
            tts.products.selected_script.return_value='script'
            tts.state.return_value=None
            tts.start.side_effect=[{'id':'expired'}, {'id':'fresh'}]
            live=ConsoleLive(tts,directory)
            live.status={'id':'scene','status':'running','rotation_language':'vi-VN'}
            live.session=Mock()
            live.session.frames_written=50
            live.session.control_state.return_value={'manual':False,'control_revision':0,'pending':0}
            live.session.queue_full.return_value=False
            live.ingress=Mock()
            live.ingress.context={'voice_id':'voice'}
            live.enqueue=Mock()
            live.configure_rotation('scene',['product'])

            def expire_after_dispatch():
                tts.state.return_value={'id':'expired','status':'failed','error':'合成超时'}
                return False

            ticks=iter((lambda: False,expire_after_dispatch,lambda: True))
            with self.assertLogs(level='ERROR'):
                live._rotate('scene',Mock(wait=lambda _: next(ticks)()))
            self.assertEqual(live.state()['status'],'running')
            self.assertEqual(live.state()['rotation_error'],'合成超时')
            self.assertEqual(live.state()['rotation_products'],[])
            self.assertEqual(live.state()['rotation_retry_products'],['product'])
            live.enqueue.assert_not_called()

            live.configure_rotation('scene',['product'])
            tts.state.return_value={'id':'expired','status':'succeeded'}

            def finish_fresh():
                tts.state.return_value={'id':'fresh','status':'succeeded'}
                return False

            ticks=iter((lambda: False,finish_fresh,lambda: True))
            live._rotate('scene',Mock(wait=lambda _: next(ticks)()))
            live.enqueue.assert_called_once_with('scene','fresh',rotation_item={
                'product_id':'product','product_version':1,'script_id':'script'})
            self.assertIsNone(live.state()['rotation_error'])
            self.assertNotIn('rotation_retry_products',live.state())
            self.assertEqual(tts.start.call_count,2)
            tts.start.assert_called_with('product','script','voice',language='vi-VN',use_cache=True,rotation=True)
