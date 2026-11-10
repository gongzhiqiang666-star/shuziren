from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.continuous_session import ContinuousSession


class SessionLifecycleTests(unittest.TestCase):
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
