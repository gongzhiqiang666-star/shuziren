import unittest
from unittest import mock

from recovered import win_power_throttling as power


class FakeThread:
    def __init__(self, alive=True):
        self.alive = alive
        self.join_calls = []

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        self.alive = False


class WinPowerThrottlingTests(unittest.TestCase):
    def tearDown(self):
        power._KEEP_ALIVE_STOP.set()
        thread = power._KEEP_ALIVE_THREAD
        if thread is not None and hasattr(thread, "join"):
            thread.join(timeout=1)
        power._KEEP_ALIVE_THREAD = None
        power._KEEP_ALIVE_STOP.clear()

    def test_remote_pid_open_failure_does_not_call_set_process_information(self):
        kernel32 = mock.Mock()
        kernel32.OpenProcess.return_value = 0
        fake_ctypes = mock.Mock(windll=mock.Mock(kernel32=kernel32))
        with mock.patch.object(power.sys, "platform", "win32"), \
                mock.patch.object(power, "ctypes", fake_ctypes), \
                mock.patch.object(power, "_set_process_power_throttling") as setter:
            self.assertFalse(power.disable_execution_speed_throttling(99999999))
        setter.assert_not_called()
        kernel32.CloseHandle.assert_not_called()

    def test_stop_keep_alive_signals_joins_and_releases_worker(self):
        thread = FakeThread()
        power._KEEP_ALIVE_THREAD = thread
        self.assertTrue(power._stop_keep_alive(0.25))
        self.assertTrue(power._KEEP_ALIVE_STOP.is_set())
        self.assertEqual(thread.join_calls, [0.25])
        self.assertIsNone(power._KEEP_ALIVE_THREAD)

    def test_stop_keep_alive_reports_worker_that_does_not_exit(self):
        thread = FakeThread()
        thread.join = lambda timeout=None: thread.join_calls.append(timeout)
        power._KEEP_ALIVE_THREAD = thread
        self.assertFalse(power._stop_keep_alive(0.1))
        self.assertIs(power._KEEP_ALIVE_THREAD, thread)

    def test_keep_alive_can_restart_after_clean_stop(self):
        with mock.patch.object(power.sys, "platform", "win32"), \
                mock.patch.object(power, "disable_execution_speed_throttling", return_value=True):
            power.ensure_high_performance(True, 5)
            first = power._KEEP_ALIVE_THREAD
            self.assertTrue(first.is_alive())
            self.assertTrue(power._stop_keep_alive())
            power.ensure_high_performance(True, 5)
            second = power._KEEP_ALIVE_THREAD
            self.assertIsNot(first, second)
            self.assertTrue(second.is_alive())


if __name__ == "__main__":
    unittest.main()
