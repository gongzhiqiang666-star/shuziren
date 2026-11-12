import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from scripts.console_live import ConsoleLive
from scripts.product_store import Conflict


class LiveRotationTests(unittest.TestCase):
    def test_manual_transition_records_only_changed_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            live = ConsoleLive(tts, directory)
            live.status = {'id': 'scene', 'status': 'running'}
            live.session = Mock()
            live.session.control_state.return_value = {'manual': True, 'control_revision': 1}
            live.set_manual('scene', True, 0)
            live.set_manual('scene', True, 1)
            self.assertEqual(tts.products.record_live_control.call_count, 1)
            self.assertEqual(tts.products.record_live_control.call_args.args[:3], ('scene', 1, True))

    def test_timed_shifts_cycle_at_product_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            tts.products.get.return_value = {'title': '测试商品', 'version': 1}
            tts.products.selected_script.return_value = 'script'
            tts.products.scripts.return_value = [{'id': 'script', 'text': '主讲。{助：补充说明。}'}]
            live = ConsoleLive(tts, directory)
            live.status = {'id': 'scene', 'status': 'running'}
            live.session = Mock()
            live.session.control_state.return_value = {}
            stale = [{'product_id': 'first', 'product_version': 1, 'script_id': 'old-script'}]
            with self.assertRaisesRegex(Conflict, '商品或话术已变化'):
                live.configure_rotation('scene', ['first'], expected_items=stale)
            self.assertIsNone(live.rotation)
            live.configure_rotation('scene', ['first', 'second'], shift_durations=[3, 5],
                                    shift_voice_ids=[None, 'next-host'])
            tts.voices.get.assert_called_once_with('next-host')
            rotation = live.rotation
            now = 100
            live._tick_rotation_shift(rotation, now)
            for _ in range(20):
                index = rotation['index']
                now += (3, 5)[index]
                live._advance_rotation(rotation)
                live._tick_rotation_shift(rotation, now)
                self.assertEqual(rotation['index'], index)
                live._advance_rotation(rotation)
                live._tick_rotation_shift(rotation, now)
                self.assertEqual(live.state()['shift_index'], 1 - index)
                self.assertEqual(rotation['items'][rotation['index']].get('shift_voice_id'),
                                 'next-host' if index == 0 else None)

    def test_segment_completion_keeps_product_until_last_segment(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            tts.products.get.return_value = {'title': '测试商品', 'version': 1}
            tts.products.selected_script.return_value = 'script'
            tts.products.scripts.return_value = [{'id': 'script', 'text': '主讲。{助：补充说明。}'}]
            live = ConsoleLive(tts, directory)
            live.status = {'id': 'scene', 'status': 'running', 'assistant_voice_id': 'assistant'}
            live.session = Mock()
            live.session.control_state.return_value = {}
            live.configure_rotation('scene', ['product'])
            for index, task_id in enumerate(('host-task', 'assistant-task')):
                live.rotation['task_id'] = task_id
                live.completed.put((task_id, index * 960, (index + 1) * 960))
                live._record_completed()
                self.assertEqual(live.state()['rotation_completed'], index)
            self.assertEqual(live.state()['last_rotation_product_id'], 'product')

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
            tts.products.scripts.return_value=[{'id':'script','text':'测试话术'}]
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
            fault = live.state()['rotation_fault']
            self.assertEqual((fault['product_id'], fault['product_version'], fault['script_id']), ('product', 1, 'script'))
            tts.products.record_rotation_fault.assert_called_once_with(
                'scene', fault['occurred_at'], '合成超时',
                item={'product_id': 'product', 'product_version': 1, 'script_id': 'script'})
            self.assertEqual(live.state()['rotation_products'],[])
            self.assertEqual(live.state()['rotation_retry_products'],['product'])
            live.enqueue.assert_not_called()

            live.configure_rotation('scene',['product'])
            self.assertNotIn('rotation_fault', live.state())
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

            live.enqueue.reset_mock()
            live.configure_rotation('scene', ['product'])
            tts.start.side_effect = None
            tts.start.return_value = {'id': 'changed'}

            def change_selected_script():
                tts.products.selected_script.return_value = 'replacement'
                tts.state.return_value = {'id': 'changed', 'status': 'succeeded'}
                return False

            ticks = iter((lambda: False, change_selected_script, lambda: True))
            with self.assertLogs(level='ERROR'):
                live._rotate('scene', Mock(wait=lambda _: next(ticks)()))
            live.enqueue.assert_not_called()
            self.assertEqual(live.state()['rotation_error'], '选用话术已变化，请重新设置轮播')
