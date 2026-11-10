from pathlib import Path
from queue import Full
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
import numpy as np
from types import SimpleNamespace

from scripts.continuous_session import ContinuousSession
from scripts.speech_assembler import Utterance


class SessionLifecycleTests(unittest.TestCase):
    def test_reply_dropped_if_capture_stops_or_control_revision_changes(self):
        for cause in ('capture', 'automatic', 'takeover', 'expiry'):
            with self.subTest(cause=cause), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                session = ContinuousSession('s', Mock(), Mock(), Mock(), root)
                path = root / 'reply.wav'
                path.touch()
                cancelled = threading.Event()
                automatic = threading.Event()
                deadline = time.monotonic() + (-1 if cause == 'expiry' else 30)
                session.submit(Utterance('s','reply','script',path,960,'wav','pcm'), priority=True,
                               reply_guard=((cancelled,automatic),0,deadline))
                if cause == 'capture':
                    cancelled.set()
                if cause == 'automatic':
                    automatic.set()
                if cause == 'takeover':
                    session.set_manual(True, 0)
                    session.set_manual(False, 1)
                self.assertIsNone(session._next_utterance())
                self.assertFalse(path.exists())

    def test_takeover_reserves_space_and_discards_unclaimed_manual_work_on_resume(self):
        for cycle in range(20):
            with self.subTest(cycle=cycle), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                session = ContinuousSession('s', Mock(), Mock(), Mock(), root)

                def utterance(task_id):
                    path = root / (task_id + '.wav')
                    path.touch()
                    return Utterance('s', task_id, 'script', path, 960, 'wav', 'pcm')

                for index in range(4):
                    session.submit(utterance(str(index)))
                session.set_manual(True, 0)
                self.assertIsNone(session._next_utterance())
                with self.assertRaises(ValueError):
                    session.submit(utterance('late-auto'), priority=True)
                manual = utterance('manual')
                session.submit(manual, manual_revision=1)
                self.assertEqual(session._next_utterance(), manual)
                pending = utterance('pending-manual')
                session.submit(pending, manual_revision=1)
                session.set_manual(False, 1)
                self.assertFalse(pending.path.exists())
                self.assertTrue(manual.path.exists())
                with self.assertRaises(ValueError):
                    session.submit(utterance('late-manual'), manual_revision=1)
                with self.assertRaises(ValueError):
                    session.set_manual(True, 1)
                self.assertEqual([session._next_utterance().task_id for _ in range(4)], ['0', '1', '2', '3'])
                session.stop()

    def test_priority_utterances_run_after_current_and_before_waiting_fifo(self):
        expected = ['current', 'urgent-1', 'urgent-2', 'normal-1', 'normal-2']
        for cycle in range(20):
            with self.subTest(cycle=cycle), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                client = Mock()
                session = ContinuousSession('s', client, Mock(), Mock(), root)
                session.pcm = Mock()
                started = threading.Event()
                resume = threading.Event()
                played = []

                def stream(operation, **options):
                    played.append(options['task_id'])
                    if len(played) == 1:
                        started.set()
                        if not resume.wait(2):
                            raise TimeoutError('Test did not release current utterance')
                    if len(played) == len(expected):
                        session.stop_event.set()

                def utterance(task_id):
                    path = root / (task_id + '.wav')
                    path.touch()
                    return Utterance('s', task_id, 'script', path, 960, 'wav', 'pcm')

                client.request.side_effect = stream
                session.submit(utterance('current'))
                producer = threading.Thread(target=session._produce)
                producer.start()
                try:
                    self.assertTrue(started.wait(2))
                    session.submit(utterance('normal-1'))
                    session.submit(utterance('urgent-1'), priority=True)
                    session.submit(utterance('normal-2'))
                    session.submit(utterance('urgent-2'), priority=True)
                    with self.assertRaises(Full):
                        session.submit(utterance('overflow'), priority=True)
                    self.assertEqual(played, ['current'])
                finally:
                    resume.set()
                    producer.join(3)
                    session.stop()
                self.assertFalse(producer.is_alive())
                self.assertEqual(session.errors, [])
                self.assertEqual(played, expected)
                with self.assertRaises(RuntimeError):
                    session.submit(utterance('late'), priority=True)

    def test_audio_input_sealed_before_slow_worker_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            order=[];receiver=Mock();receiver.full=threading.Event();receiver.full.set()
            receiver.take.side_effect=[SimpleNamespace(frame_index=i,session_id='s',task_id='idle',image=np.zeros((2,2,3),np.uint8)) for i in range(9)]
            client=Mock();client.close.side_effect=lambda:order.append('worker_close')
            sink=Mock();sink.clock_mode='audio';sink.finish_input.side_effect=lambda:order.append('seal_input')
            sink.close.side_effect=lambda:order.append('device_close')
            session=ContinuousSession('s',client,receiver,sink,Path(temporary));session._produce=lambda:None
            session.pcm=Mock();session.pcm.read.return_value=bytes(1920)
            session.run(frames=9)
            self.assertEqual(order,['seal_input','worker_close','device_close'])
            self.assertEqual(session.frames_written,9)

    def test_cancel_during_initial_frame_wait_does_not_wait_thirty_seconds(self):
        with tempfile.TemporaryDirectory() as temporary:
            entered=threading.Event();closed=threading.Event();errors=[]
            client=Mock()
            def request(*args,**kwargs):
                entered.set();closed.wait(3)
            client.request.side_effect=request;client.close.side_effect=closed.set
            receiver=Mock();receiver.full=threading.Event();sink=Mock()
            session=ContinuousSession('s',client,receiver,sink,Path(temporary))
            def run():
                try:session.run(frames=10)
                except RuntimeError as error:errors.append(str(error))
            thread=threading.Thread(target=run);thread.start()
            self.assertTrue(entered.wait(1));session.stop();thread.join(1)
            self.assertFalse(thread.is_alive());self.assertTrue(session.finished.is_set())
            self.assertEqual(errors,['Presentation stopped during startup']);sink.abort.assert_called_once()

    def test_stop_before_start_releases_owned_inputs_without_waiting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'owned.wav';path.write_bytes(b'owned')
            client=Mock();receiver=Mock();sink=Mock()
            session=ContinuousSession('s',client,receiver,sink,root)
            session.leases['task']={'path':path,'model':False,'audio':False}
            session.stop()
            self.assertTrue(session.finished.is_set());self.assertFalse(path.exists())
            self.assertEqual(session.leases,{})
            client.close.assert_called_once();receiver.close.assert_called_once();sink.abort.assert_called_once()
