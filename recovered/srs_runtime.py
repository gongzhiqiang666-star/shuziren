"""Lifecycle helpers for the bundled Windows SRS media server."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path


SRS_PORTS = (1935, 1985, 8080)


def _port_is_listening(port, host="127.0.0.1", timeout=0.15):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def bundled_srs_paths(runtime_dir):
    root = Path(runtime_dir).expanduser().resolve() / "assets" / "srs"
    return root, root / "objs" / "srs.exe", root / "conf" / "live.conf"


def start_bundled_srs(runtime_dir, startup_timeout=5.0, poll_interval=0.05):
    """Start the exact bundled SRS instance and return its ``Popen`` handle.

    A pre-existing listener is treated as a conflict instead of silently taking
    ownership of another application's SRS process.
    """
    if sys.platform != "win32":
        return None
    root, executable, config = bundled_srs_paths(runtime_dir)
    missing = [str(path) for path in (executable, config) if not path.is_file()]
    if missing:
        print("警告: 未找到随包SRS文件: " + ", ".join(missing))
        return None
    occupied = [port for port in SRS_PORTS if _port_is_listening(port)]
    if occupied:
        print("启动SRS服务器失败: 端口已占用: " + ", ".join(map(str, occupied)))
        return None
    try:
        process = subprocess.Popen(
            [str(executable), "-c", str(config.relative_to(root))],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        print(f"启动SRS服务器失败: {error}")
        return None
    deadline = time.monotonic() + max(0.0, float(startup_timeout))
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            print(f"启动SRS服务器失败: 进程提前退出，退出码 {return_code}")
            return None
        if all(_port_is_listening(port) for port in SRS_PORTS):
            return process
        time.sleep(max(0.01, float(poll_interval)))
    stop_srs_process(process)
    print("启动SRS服务器失败: 等待本地 1935/1985/8080 端口就绪超时")
    return None


def stop_srs_process(process, timeout=3.0):
    """Stop only the SRS process tree represented by *process*."""
    if process is None or process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(0.1, float(timeout)),
            check=False,
        )
        try:
            process.wait(timeout=max(0.1, float(timeout)))
        except subprocess.TimeoutExpired:
            process.kill()
    else:
        process.terminate()
        try:
            process.wait(timeout=max(0.1, float(timeout)))
        except subprocess.TimeoutExpired:
            process.kill()


def srs_process_status(process):
    if process is None:
        return "unavailable"
    return "running" if process.poll() is None else "stopped"
