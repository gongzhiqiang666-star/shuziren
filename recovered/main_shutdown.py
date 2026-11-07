"""SRS process cleanup recovered from main.pyd at 0x180010d30."""

import os
import subprocess
import sys


def _shutdown_srs(proc):
    if not proc:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/IM", "srs.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif proc.poll() is None:
        proc.terminate()


api_for_exit = None


def force_exit(signum, frame):
    """Clean up the registered SRS process and exit from a signal handler."""
    if api_for_exit:
        _shutdown_srs(api_for_exit.srs_process)
        api_for_exit.srs_process = None
    os._exit(0)


def make_on_closed(api):
    """Build the no-argument window callback that captures the window's API."""
    def on_closed():
        _shutdown_srs(api.srs_process)
        os._exit(0)

    return on_closed
