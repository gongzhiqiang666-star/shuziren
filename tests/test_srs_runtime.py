import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from recovered import srs_runtime


class FakeProcess:
    def __init__(self, poll_values=(None,), pid=4321):
        self._poll_values = iter(poll_values)
        self._last = None
        self.pid = pid
        self.waited = False

    def poll(self):
        self._last = next(self._poll_values, self._last)
        return self._last

    def wait(self, timeout=None):
        self.waited = True
        self._last = 0
        return 0


class SrsRuntimeTests(unittest.TestCase):
    def _runtime(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "assets" / "srs"
        (root / "objs").mkdir(parents=True)
        (root / "conf").mkdir()
        (root / "objs" / "srs.exe").touch()
        (root / "conf" / "live.conf").write_text("listen 1935;", encoding="utf-8")
        return temporary

    @mock.patch.object(srs_runtime.sys, "platform", "win32")
    def test_missing_bundle_does_not_start(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(srs_runtime.subprocess, "Popen") as popen:
            self.assertIsNone(srs_runtime.start_bundled_srs(root))
            popen.assert_not_called()

    @mock.patch.object(srs_runtime.sys, "platform", "win32")
    def test_port_conflict_does_not_take_ownership(self):
        temporary = self._runtime()
        with temporary, mock.patch.object(srs_runtime, "_port_is_listening", return_value=True), \
                mock.patch.object(srs_runtime.subprocess, "Popen") as popen:
            self.assertIsNone(srs_runtime.start_bundled_srs(temporary.name))
            popen.assert_not_called()

    @mock.patch.object(srs_runtime.sys, "platform", "win32")
    def test_early_exit_is_reported(self):
        temporary = self._runtime()
        process = FakeProcess((17,))
        with temporary, mock.patch.object(srs_runtime, "_port_is_listening", return_value=False), \
                mock.patch.object(srs_runtime.subprocess, "Popen", return_value=process):
            self.assertIsNone(srs_runtime.start_bundled_srs(temporary.name, startup_timeout=0.1))

    @mock.patch.object(srs_runtime.sys, "platform", "win32")
    def test_ready_process_is_returned(self):
        temporary = self._runtime()
        process = FakeProcess((None,))
        with temporary, mock.patch.object(srs_runtime, "_port_is_listening", side_effect=[False] * 3 + [True] * 3), \
                mock.patch.object(srs_runtime.subprocess, "Popen", return_value=process):
            self.assertIs(process, srs_runtime.start_bundled_srs(temporary.name, startup_timeout=0.1))

    @mock.patch.object(srs_runtime.sys, "platform", "win32")
    def test_shutdown_targets_only_owned_pid(self):
        process = FakeProcess((None,), pid=2468)
        with mock.patch.object(srs_runtime.subprocess, "run") as run:
            srs_runtime.stop_srs_process(process)
        command = run.call_args.args[0]
        self.assertEqual(command, ["taskkill", "/F", "/T", "/PID", "2468"])
        self.assertNotIn("/IM", command)
        self.assertTrue(process.waited)

    def test_status(self):
        self.assertEqual(srs_runtime.srs_process_status(None), "unavailable")
        self.assertEqual(srs_runtime.srs_process_status(FakeProcess((None,))), "running")
        self.assertEqual(srs_runtime.srs_process_status(FakeProcess((0,))), "stopped")


if __name__ == "__main__":
    unittest.main()
