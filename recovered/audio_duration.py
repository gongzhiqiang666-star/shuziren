"""Recovered ``tools.cloud_dh.audio_duration`` helpers."""

from __future__ import annotations

import os
import subprocess
from typing import Optional


def _find_ffprobe() -> Optional[str]:
    """Locate and validate the packaged ffprobe executable."""
    here = os.path.dirname(os.path.abspath(__file__))
    client_root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    cands = [
        os.path.join(client_root, "_internal", "env", "ffmpeg", "bin", "ffprobe.exe"),
        os.path.join(client_root, "_internal", "env", "Library", "bin", "ffprobe.exe"),
        os.path.join(client_root, "packed", "_internal", "env", "Library", "bin", "ffprobe.exe"),
        "ffprobe",
    ]
    for cand in cands:
        try:
            if cand != "ffprobe" and not os.path.exists(cand):
                continue
            subprocess.run([cand, "-version"], capture_output=True, check=True)
            return cand
        except Exception:
            continue
    return None


def get_audio_duration(path: str) -> float:
    """Return media duration in seconds, matching the packaged ffprobe wrapper."""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"音频不存在: {path}")
    probe = _find_ffprobe()
    try:
        if probe:
            completed = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, check=True,
            )
            return float(completed.stdout.strip())
        import librosa
        return float(librosa.get_duration(path=path))
    except Exception as exc:
        raise RuntimeError(f"无法读取音频时长: {exc}") from exc
