from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from scripts.continuous_session import ContinuousSession


class SessionLifecycleTests(unittest.TestCase):
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
