"""Reconstruction from the embedded CPython 3.10 launcher bytecode."""
import ctypes
import os
import re
import subprocess
import sys
from pathlib import Path
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


def resolve_launch_plan(executable=None, gpu_50=None):
    """Resolve and validate launcher-owned paths without starting a process."""
    executable = Path(executable or sys.executable).resolve()
    internal_dir = executable.parent / "_internal"
    use_gpu_50 = get_gpu_info() if gpu_50 is None else bool(gpu_50)
    preferred = internal_dir / "env_50" if use_gpu_50 else internal_dir / "env"
    python_exe = preferred / "python.exe"
    selected = "env_50" if preferred.name == "env_50" else "env"
    if selected == "env_50" and not python_exe.is_file():
        preferred = internal_dir / "env"
        python_exe = preferred / "python.exe"
        selected = "env"
    start_script = internal_dir / "start.py"
    missing = [str(path) for path in (python_exe, start_script) if not path.is_file()]
    if missing:
        raise FileNotFoundError("启动文件缺失: " + ", ".join(missing))
    ffmpeg_dir = preferred / "ffmpeg"
    ffmpeg_bin = ffmpeg_dir / "bin"
    return {"internal_dir": internal_dir, "env_dir": preferred, "environment": selected,
            "python_exe": python_exe, "start_script": start_script,
            "ffmpeg_dir": ffmpeg_dir, "ffmpeg_bin": ffmpeg_bin}


def main():
    disable_execution_speed_throttling()
    try:
        plan = resolve_launch_plan()
    except Exception as error:
        print(f"数字人启动失败: {error}", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["FFMPEG_HOME"] = str(plan["ffmpeg_dir"])
    if plan["ffmpeg_bin"].is_dir():
        env["PATH"] = str(plan["ffmpeg_bin"]) + os.pathsep + env.get("PATH", "")

    try:
        process = subprocess.Popen(
            [str(plan["python_exe"]), str(plan["start_script"])],
            cwd=str(plan["internal_dir"]), env=env,
        )
        disable_execution_speed_throttling(process.pid)
        return process.wait()
    except Exception as error:
        print(f"数字人启动失败: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
