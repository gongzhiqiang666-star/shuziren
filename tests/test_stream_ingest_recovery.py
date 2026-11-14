import threading
import unittest
from unittest.mock import Mock

from recovered.stream_ingest import LiveStreamIngestProcess


class StreamIngestRecoveryTests(unittest.TestCase):
    def ingest(self):
        ingest = object.__new__(LiveStreamIngestProcess)
        ingest.config = {"douyin_ingest_restart_delay": 0.01}
        ingest.process = None
        ingest.stderr_thread = None
        ingest.monitor_thread = None
        ingest.stderr_lines = []
        ingest._stop_requested = False
        ingest._stop_event = threading.Event()
        ingest._room_url = "https://live.douyin.com/123"
        ingest.last_error = ""
        return ingest

    def test_monitor_re_resolves_and_restarts_dead_relay(self):
        ingest = self.ingest()
        ingest.is_running = Mock(side_effect=(False, True))
        ingest._stop_process = Mock()
        ingest.resolver = Mock()
        data = {"candidates": [("https://media.example/live.flv", "copy")]}
        ingest.resolver.resolve.return_value = data

        def launch(value):
            self.assertIs(value, data)
            ingest._stop_event.set()
            return True

        ingest._launch_candidates = Mock(side_effect=launch)
        ingest._monitor_loop()

        ingest._stop_process.assert_called_once_with()
        ingest.resolver.resolve.assert_called_once_with(
            "https://live.douyin.com/123"
        )
        ingest._launch_candidates.assert_called_once_with(data)

    def test_stop_cancels_monitor_and_relay(self):
        ingest = self.ingest()
        exited = threading.Event()

        def monitor():
            ingest._stop_event.wait()
            exited.set()

        thread = threading.Thread(target=monitor)
        ingest.monitor_thread = thread
        ingest._stop_process = Mock()
        thread.start()

        ingest.stop()

        self.assertTrue(ingest._stop_requested)
        self.assertTrue(exited.is_set())
        self.assertIsNone(ingest.monitor_thread)
        ingest._stop_process.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
