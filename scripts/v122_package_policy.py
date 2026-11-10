"""Explicit derived-data policy; archive verification never applies exclusions.

Runtime health verifies immutable inputs, not executable cache trust or inference.
"""
from pathlib import PurePosixPath

POLICY = "v122-derived-data-v1"
RUNTIME_PREFIX = "runtime/yunchuang_v122/"
REQUIRED_RUNTIME_FILES = (
    "数字人直播.exe", "_internal/start.py", "_internal/main.cp310-win_amd64.pyd",
    "_internal/live/clone_manager.cp310-win_amd64.pyd", "_internal/config/config.yaml",
    "_internal/env/python.exe", "_internal/env/ffmpeg/bin/ffmpeg.exe",
    "_internal/env/ffmpeg/bin/ffprobe.exe",
)


def derived_reason(relative):
    """Known paths/types only: code, weights and arbitrary temp files stay immutable."""
    if not relative.startswith(RUNTIME_PREFIX):
        return None
    path = PurePosixPath(relative[len(RUNTIME_PREFIX):])
    if "__pycache__" in path.parts and path.suffix.lower() in {".pyc", ".pyo", ".nbc", ".nbi"}:
        return "python-numba-cache"
    if path.as_posix() == "_internal/temp/audio_cache_index.txt":
        return "audio-cache-index"
    trt = PurePosixPath("_internal/assets/pretrained_models/image_infer_v2/trt_cache_full")
    if path.parent == trt and (path.suffix in {".engine", ".profile"} or path.name == "gpu_info.txt"):
        return "hardware-specific-tensorrt-cache"
    return None


def transport_metadata(relative):
    """Omit macOS transport metadata only when creating a new package."""
    return any(part == ".DS_Store" or part.startswith("._") for part in PurePosixPath(relative).parts)
