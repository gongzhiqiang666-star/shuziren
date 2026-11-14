"""Recovered Windows execution-speed throttling control."""

import ctypes
import sys
from ctypes import wintypes

from threading import Event, Lock, Thread


PROCESS_SET_INFORMATION = 0x0200
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1


class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [("Version", wintypes.DWORD), ("ControlMask", wintypes.DWORD), ("StateMask", wintypes.DWORD)]


def _set_process_power_throttling(handle) -> bool:
    if sys.platform != "win32":
        return False
    state = PROCESS_POWER_THROTTLING_STATE(
        PROCESS_POWER_THROTTLING_CURRENT_VERSION,
        PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
        0,
    )
    setter = ctypes.windll.kernel32.SetProcessInformation
    setter.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    setter.restype = wintypes.BOOL
    return bool(setter(handle, 4, ctypes.byref(state), ctypes.sizeof(state)))


def disable_execution_speed_throttling(pid=None) -> bool:
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.windll.kernel32
    close_handle = False
    try:
        if pid is None:
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            handle = kernel32.GetCurrentProcess()
        else:
            kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            handle = kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, int(pid))
            close_handle = True
            if not handle:
                return False
        return _set_process_power_throttling(handle)
    except Exception:
        return False
    finally:
        if close_handle and locals().get("handle"):
            try: kernel32.CloseHandle(handle)
            except Exception: pass

_KEEP_ALIVE_LOCK = Lock()
_KEEP_ALIVE_THREAD = None
_KEEP_ALIVE_STOP = Event()


def _start_keep_alive(interval_seconds):
    global _KEEP_ALIVE_THREAD
    interval_seconds = max(5.0, float(interval_seconds or 30.0))

    def refresh():
        while not _KEEP_ALIVE_STOP.wait(interval_seconds):
            disable_execution_speed_throttling()

    with _KEEP_ALIVE_LOCK:
        if _KEEP_ALIVE_THREAD is None or not _KEEP_ALIVE_THREAD.is_alive():
            _KEEP_ALIVE_STOP.clear()
            _KEEP_ALIVE_THREAD = Thread(
                target=refresh,
                name="win-power-throttling-keepalive",
                daemon=True,
            )
            _KEEP_ALIVE_THREAD.start()


def _stop_keep_alive(timeout_seconds=2.0):
    """Stop and release the process-wide refresh worker, if one exists."""
    global _KEEP_ALIVE_THREAD
    with _KEEP_ALIVE_LOCK:
        thread = _KEEP_ALIVE_THREAD
        if thread is None:
            return True
        _KEEP_ALIVE_STOP.set()
    if thread is not __import__("threading").current_thread():
        thread.join(timeout=max(0.0, float(timeout_seconds)))
    stopped = not thread.is_alive()
    if stopped:
        with _KEEP_ALIVE_LOCK:
            if _KEEP_ALIVE_THREAD is thread:
                _KEEP_ALIVE_THREAD = None
    return stopped


def ensure_high_performance(keep_alive=True, interval_seconds=30.0):
    enabled = disable_execution_speed_throttling()
    if keep_alive and sys.platform == "win32":
        _start_keep_alive(interval_seconds)
    return enabled
