"""SRS process cleanup recovered from main.pyd at 0x180010d30."""

import os
from .srs_runtime import stop_srs_process


def _shutdown_srs(proc):
    stop_srs_process(proc)


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
