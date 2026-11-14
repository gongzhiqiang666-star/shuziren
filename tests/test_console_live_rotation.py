import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from scripts.console_live import ConsoleLive
from scripts.product_store import Conflict, ProductStore


class LiveRotationTests(unittest.TestCase):
    def test_video_insert_cleanup_error_preserves_scene_failure_record(self):
        with tempfile.TemporaryDirectory() as directory:
            live = ConsoleLive(Mock(), directory)
            live.tts.runtime = directory
            live.status = {'id': 'scene', 'status': 'preparing', 'mode': 'local_video',
                           'requested_at': 100, 'frames': 0, 'insert_pending': True}
            live.video_insert_snapshot = 'insert.wav'
            with (patch('scripts.console_live.subprocess.Popen', side_effect=OSError('worker unavailable')),
                  patch('scripts.console_live.Path.unlink', side_effect=PermissionError('file in use')),
                  self.assertLogs(level='ERROR')):
                live._run_video('scene', 1, 'input.mp4', 'cuda')
            self.assertEqual(live.status['status'], 'failed')
            self.assertIsNone(live.video_insert_snapshot)
            self.assertFalse(live.status['insert_pending'])
            recorded = live.tts.products.record_live_session.call_args.kwargs
            self.assertEqual(recorded['status'], 'failed')
            self.assertEqual(recorded['failure_reason'], 'worker unavailable')
            self.assertNotIn('video_counters', recorded)

    def test_video_failure_records_last_observed_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            live = ConsoleLive(Mock(), directory)
            live.status = {'id': 'scene', 'status': 'failed', 'mode': 'local_video',
                           'requested_at': 100, 'ended_at': 104, 'frames': 72,
                           'error': 'worker exited', 'reused_frames': 2, 'queue_length': 4}
            live._record_session()
            recorded = live.tts.products.record_live_session.call_args.kwargs
            self.assertEqual(recorded['video_counters'], {'reused_frames': 2, 'queue_length': 4})

    def test_failed_preparation_application_keeps_pending_rotation_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            tts.products.get.return_value = {'title': '测试商品', 'version': 1}
            tts.products.selected_script.return_value = 'script'
            tts.products.scripts.return_value = [{'id': 'script', 'text': '主讲。'}]
            live = ConsoleLive(tts, directory)
            live.status = {'id': 'scene', 'status': 'running'}
            live.session = Mock()
            live.session.control_state.return_value = {}
            live.configure_rotation('scene', ['current'])
            current_rotation = live.rotation
            current_rotation['task_id'] = 'pending-audio'
            tts.products.record_preparation_application.side_effect = Conflict('准备包已变化')

            with self.assertRaisesRegex(Conflict, '准备包已变化'):
                live.configure_rotation('scene', ['replacement'], preparation={'id': 'package'})

            self.assertIs(live.rotation, current_rotation)
            self.assertEqual(live.status['rotation_products'], ['current'])
            live.session.discard_pending.assert_not_called()

    def test_stop_cancels_rtmp_worker_after_start(self):
        with tempfile.TemporaryDirectory() as directory:
            live = ConsoleLive(Mock(), directory)
            live.status = {'id': 'scene', 'status': 'running', 'input_mode': 'rtmp'}
            live.client = Mock()

            def check_cancel():
                self.assertTrue(live.cancel.is_set())
                self.assertEqual(live.state()['status'], 'stopping')

            live.client.close.side_effect = check_cancel
            self.assertEqual(live.stop('scene')['status'], 'stopping')
            live.client.close.assert_called_once_with()

    def test_preparation_improvements_are_bound_to_the_running_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductStore(directory)
            product = store.save(title='茶杯', content='商品说明', product_index=1)
            script = store.add_script(product, '这是一只茶杯。')
            store.select_script(product['id'], script)
            store.record_live_session('source', 1)
            store.record_queued_reply('source', 'reply', product, '材质是什么？', '请核对规格', 2)
            store.save_reply_improvement('source', 'reply', '运营', '补充材质', adopted=True)
            store.save_live_preparation(product_ids=[product['id']])
            revision = store.build_live_preparation()['revision']
            store.save_live_preparation_review(revision, '已核对')
            snapshot = store.live_preparation_rotation(revision, include_improvements=True)
            store.record_live_session('target', 3, started_at=4, status='running')
            live = ConsoleLive(Mock(products=store), directory)
            live.status = {'id': 'target', 'status': 'running'}
            live.session = Mock()
            live.session.control_state.return_value = {}
            for _ in range(2):
                live.configure_rotation('target', [product['id']], preparation=snapshot)
            store.save_reply_improvement('source', 'reply', '运营', '补充材质', adopted=False)
            self.assertEqual(store.live_preparation_applications('target'), [snapshot])
            self.assertEqual(store.live_preparation_applications('source'), [])

    def test_rotation_exposes_sourced_zero_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            tts.products.get.return_value = {'title': '茶杯', 'version': 1, 'extra': {'product_facts': {
                '库存': {'value': 0, 'status': 'verified', 'source': '商家盘点'},
            }}}
            tts.products.selected_script.return_value = 'script'
            tts.products.scripts.return_value = [{'id': 'script', 'text': '茶杯'}]
            live = ConsoleLive(tts, directory)
            live.status = {'id': 'scene', 'status': 'running'}
            live.session = Mock()
            live.session.control_state.return_value = {}
            state = live.configure_rotation('scene', ['product'])
            self.assertEqual(state['rotation_stock_evidence']['source'], '商家盘点')
            tts.products.get.return_value['extra']['product_facts']['库存'] = {'status': 'unknown'}
            self.assertNotIn('rotation_stock_evidence', live.configure_rotation('scene', ['product']))

    def test_rotation_enqueue_passes_earliest_fact_deadline_to_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            tts.state.return_value = {'id': 'clip', 'fact_deadline': 110}
            live = ConsoleLive(tts, directory)
            live.status = {'id': 'scene', 'status': 'running'}
            live.session = Mock()
            live.session.queue_full.return_value = False
            live.session.control_state.return_value = {'manual': False}
            live.ingress = Mock()
            live.assembler = Mock()
            item = {'fact_deadline': 100}
            utterance = live.enqueue('scene', 'clip', rotation_item=item)
            live.session.submit.assert_called_once_with(
                utterance, priority=False, manual_revision=None, reply_guard=None, fact_deadline=100)

    def test_expired_queued_rotation_does_not_wait_for_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            live = ConsoleLive(tts, directory)
            live.status = {'id': 'scene', 'status': 'running'}
            live.session = Mock()
            live.session.control_state.return_value = {'manual': True}
            item = {'product_id': 'product', 'product_version': 1, 'script_id': 'script', 'fact_deadline': 100}
            live.rotation = {'items': [item], 'index': 0, 'task_id': 'queued'}
            with patch('scripts.console_live.time.time', return_value=100), self.assertLogs(level='ERROR'):
                live._rotate('scene', Mock(wait=Mock(side_effect=[False, True])))
            live.session.discard_pending.assert_called_once_with('queued')
            self.assertIsNone(live.rotation)
            self.assertEqual(live.status['rotation_fault']['fact_expired_at'], 100)

    def test_rotation_rejects_expired_product_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            tts = Mock()
            tts.products.get.return_value = {'version': 1}
            live = ConsoleLive(tts, directory)
            item = {'product_id': 'product', 'product_version': 1, 'script_id': 'script', 'fact_deadline': 100}
            with patch('scripts.console_live.time.time', return_value=100):
                with self.assertRaisesRegex(Conflict, '商品事实已到期'):
                    live._check_rotation_item(item)
            tts.products.selected_script.assert_not_called()

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
            with patch('scripts.console_live.time.monotonic', return_value=103):
                self.assertEqual(live.state()['shift_waiting_for_boundary'], {
                    'product_id': 'first', 'product_version': 1, 'script_id': 'script', 'duration_seconds': 3,
                    'shift_started_at_monotonic': 100,
                })
                live.session.control_state.return_value = {'manual': True}
                self.assertNotIn('shift_waiting_for_boundary', live.state())
                live.session.control_state.return_value = {}
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
            with patch('scripts.console_live.time.monotonic', return_value=now + 3):
                waiting = live.state()['shift_waiting_for_boundary']
                self.assertEqual(waiting['product_id'], 'first')
                self.assertEqual(waiting['shift_started_at_monotonic'], now)

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
