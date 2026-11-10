from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
import numpy as np
from types import SimpleNamespace

from scripts.continuous_session import ContinuousSession


class SessionLifecycleTests(unittest.TestCase):
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
