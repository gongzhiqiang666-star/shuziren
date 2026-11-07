"""Recovered distribution and bundled-runtime environment initialization."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def get_distribution_root(base_dir):
    base = Path(base_dir).expanduser().resolve()
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve().parent
        return str(executable)
    if base.name == "_internal": return str(base.parent)
    return str(base)


def get_gpu_info():
    result = {"cuda_available": False, "device_name": None, "total_vram_gb": 0,
              "is_50_series": False, "error": None}
    command = ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        line = completed.stdout.splitlines()[0]; name, memory = [part.strip() for part in line.rsplit(",", 1)]
        result.update(cuda_available=True, device_name=name,
                      total_vram_gb=round(float(memory) / 1024, 2),
                      is_50_series=bool(re.search(r"(?:RTX\s*)?50\d{2}", name, re.I)))
    except Exception as error: result["error"] = str(error)
    return result


def _resolve_environment_dir(is_50_series=False, base_dir=None):
    root = Path(get_distribution_root(base_dir or Path.cwd()))
    internal = root / "_internal" if (root / "_internal").is_dir() else root
    preferred = internal / ("env_50" if is_50_series else "env")
    fallback = internal / "env"
    return str(preferred if preferred.is_dir() else fallback)


def resolve_environment_dir(is_50_series):
    return _resolve_environment_dir(is_50_series)


def _initialize_environment(base_dir=None, is_50_series=None):
    gpu = get_gpu_info() if is_50_series is None else {"is_50_series": bool(is_50_series)}
    environment = Path(_resolve_environment_dir(gpu.get("is_50_series", False), base_dir))
    ffmpeg_home = environment / "ffmpeg"; ffmpeg_bin = ffmpeg_home / "bin"
    if ffmpeg_home.is_dir(): os.environ["FFMPEG_HOME"] = str(ffmpeg_home)
    additions = [ffmpeg_bin, environment / "DLLs", environment / "Library/bin"]
    existing = os.environ.get("PATH", "").split(os.pathsep)
    for path in reversed(additions):
        if path.is_dir() and str(path) not in existing: existing.insert(0, str(path))
        if sys.platform == "win32" and path.is_dir() and hasattr(os, "add_dll_directory"):
            try: os.add_dll_directory(str(path))
            except OSError: pass
    os.environ["PATH"] = os.pathsep.join(existing)
    return {"environment_dir": str(environment), "ffmpeg_home": str(ffmpeg_home), **gpu}


def initialize_environment():
    return _initialize_environment()


def read_startup_admin_id(base_dir=None):
    root = Path(get_distribution_root(base_dir or Path.cwd()))
    for path in (root / "_internal/assets/web/id.txt", root / "assets/web/id.txt"):
        try:
            value = path.read_text(encoding="utf-8").strip()
            if value.isdigit(): return int(value)
        except OSError: pass
    return None


def configure_cmd_window_content(show=True):
    """Preserve the console and optionally silence its regular output."""
    if show: return True
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        sink = open(os.devnull, "w")
        sys.stdout = sink; sys.stderr = sink
    return False
