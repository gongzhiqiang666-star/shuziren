import signal
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from recovered import main_shutdown, main_webview
from recovered.main import Api


class FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeManager:
    def __init__(self, broadcasting=True, error=None):
        self.is_broadcasting = broadcasting
        self.error = error
        self.calls = 0

    def stop_live(self):
        self.calls += 1
        if self.error:
            raise self.error
        self.is_broadcasting = False
        return True


class FakeProcess:
    def __init__(self):
        self.code = None
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.code = 0
        return 0


class MainWebviewLifecycleTests(unittest.TestCase):
    def test_environment_resolution_and_timestamp(self):
        config = {"debug_mode": "true"}
        with mock.patch.object(main_webview.time, "time", return_value=12.345):
            url = main_webview.resolve_webview_url(config)
        self.assertEqual(url, "http://localhost:5002/?t=12345")
        self.assertEqual(config["environment"], "development")

    def test_run_webview_binds_api_and_close_handler(self):
        closed = FakeEvent()
        window = SimpleNamespace(events=SimpleNamespace(closed=closed))
        fake_webview = SimpleNamespace(
            settings={},
            create_window=mock.Mock(return_value=window),
            start=mock.Mock(),
        )
        api = SimpleNamespace(shutdown=mock.Mock())
        config = {"environment": "development", "environments": {
            "development": {"webview_url": "http://127.0.0.1:5218/"}
        }}
        with tempfile.TemporaryDirectory() as root, \
                mock.patch.dict(sys.modules, {"webview": fake_webview}), \
                mock.patch.object(signal, "signal") as signal_call:
            main_webview.run_webview(api, config, root, debug=False)
        arguments = fake_webview.create_window.call_args
        self.assertIs(arguments.kwargs["js_api"], api)
        self.assertEqual(arguments.kwargs["min_size"], (1200, 750))
        self.assertRegex(arguments.args[1], r"^http://127\.0\.0\.1:5218/\?t=\d+$")
        fake_webview.start.assert_called_once_with(debug=False, private_mode=False)
        self.assertEqual(signal_call.call_count, 2)
        self.assertEqual(len(closed.handlers), 1)

    def test_close_callback_releases_before_exit(self):
        api = SimpleNamespace(shutdown=mock.Mock())
        callback = main_shutdown.make_on_closed(api)
        with mock.patch.object(main_shutdown.os, "_exit", side_effect=SystemExit) as exit_call:
            with self.assertRaises(SystemExit):
                callback()
        api.shutdown.assert_called_once_with()
        exit_call.assert_called_once_with(0)

    def test_api_shutdown_is_idempotent_and_continues_after_error(self):
        api = Api.__new__(Api)
        api._live_lifecycle_lock = __import__("threading").RLock()
        api._shutdown_complete = False
        bad = FakeManager(error=RuntimeError("stop failed"))
        good = FakeManager()
        idle = FakeManager(broadcasting=False)
        api._face_hand_live_manager = bad
        api._record_live_manager = good
        api._digital_live_manager = idle
        api._live_action_assistant_process = FakeProcess()
        api._audio_editor_process = FakeProcess()
        api.srs_process = object()
        with mock.patch("recovered.main._shutdown_srs") as stop_srs, \
                mock.patch("recovered.main._stop_keep_alive", return_value=True) as stop_power:
            first = api.shutdown()
            second = api.shutdown()
        self.assertEqual(first["status"], "partial")
        self.assertIn("stop failed", first["errors"][0])
        self.assertEqual(good.calls, 1)
        self.assertEqual(idle.calls, 0)
        stop_srs.assert_called_once()
        stop_power.assert_called_once_with()
        self.assertTrue(second["already_stopped"])


if __name__ == "__main__":
    unittest.main()
