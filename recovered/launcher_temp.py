"""Reconstruction from the embedded CPython 3.10 launcher bytecode."""
import ctypes
import os
import re
import subprocess
import sys
from ctypes import wintypes


class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [
        ("Version", wintypes.DWORD),
        ("ControlMask", wintypes.DWORD),
        ("StateMask", wintypes.DWORD),
    ]


def disable_execution_speed_throttling(pid=None):
    if sys.platform != "win32":
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
        )
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = (
            kernel32.GetCurrentProcess()
            if pid is None
            else kernel32.OpenProcess(0x0200, False, int(pid))
        )
        if not handle:
            return False
        try:
            state = PROCESS_POWER_THROTTLING_STATE(1, 1, 0)
            set_info = kernel32.SetProcessInformation
            set_info.argtypes = (
                wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            )
            set_info.restype = wintypes.BOOL
            return bool(set_info(handle, 4, ctypes.byref(state), ctypes.sizeof(state)))
        finally:
            if pid is not None:
                kernel32.CloseHandle(handle)
    except Exception:
        return False


def get_gpu_info():
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    nvidia_smi = "nvidia-smi"
    for path in (
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        r"C:\Windows\System32\nvidia-smi.exe",
    ):
        if os.path.exists(path):
            nvidia_smi = path
            break

    for command in (
        [nvidia_smi, "--query-gpu=gpu_name", "--format=csv,noheader"],
        ["wmic", "path", "win32_VideoController", "get", "name"],
    ):
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=True, creationflags=flags
            )
            if re.search(r"50\d{2}", result.stdout.strip()):
                return True
        except Exception:
            pass
    return False


def main():
    disable_execution_speed_throttling()
    internal_dir = os.path.join(os.path.dirname(sys.executable), "_internal")
    env_dir = os.path.join(internal_dir, "env")
    if get_gpu_info():
        env_50_dir = os.path.join(internal_dir, "env_50")
        if os.path.exists(env_50_dir):
            env_dir = env_50_dir

    python_exe = os.path.join(env_dir, "python.exe")
    if not os.path.exists(python_exe) and env_dir.endswith("env_50"):
        env_dir = os.path.join(internal_dir, "env")
        python_exe = os.path.join(env_dir, "python.exe")

    start_script = os.path.join(internal_dir, "start.py")
    ffmpeg_dir = os.path.join(env_dir, "ffmpeg")
    ffmpeg_bin = os.path.join(ffmpeg_dir, "bin")
    env = os.environ.copy()
    env["FFMPEG_HOME"] = ffmpeg_dir
    if os.path.exists(ffmpeg_bin):
        env["PATH"] = ffmpeg_bin + os.pathsep + env.get("PATH", "")

    try:
        process = subprocess.Popen([python_exe, start_script], cwd=internal_dir, env=env)
        disable_execution_speed_throttling(process.pid)
        return process.wait()
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
