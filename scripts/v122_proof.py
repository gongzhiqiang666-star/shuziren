#!/usr/bin/env python3
"""Portable contracts and utilities for the local v122 first-proof toolkit."""

import json
import re
from pathlib import Path, PurePosixPath


class ProofError(ValueError):
    pass


_TOP_KEYS = {"version", "paths", "runtime", "capture", "output"}
_PATH_KEYS = {"runtime", "runs", "reports", "recordings", "web"}
_SENSITIVE = re.compile(r"(^|_)(api_?key|token|cookie|password|secret|credential)s?($|_)", re.I)


def example_config():
    return {
        "version": 1,
        "paths": {
            "runtime": "runtime/yunchuang_v122",
            "runs": "runs",
            "reports": "reports",
            "recordings": "recordings",
            "web": "proof/web",
        },
        "runtime": {"environment": "env", "python": "_internal/env/python.exe"},
        "capture": {"person_max_bytes": 750_000_000, "voice_max_bytes": 100_000_000},
        "output": {"width": 720, "height": 1280, "fps": 25},
    }


def load_config(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProofError("configuration is not readable JSON") from error
    validate_config(data)
    return data


def _reject_sensitive(value, location="config"):
    if isinstance(value, dict):
        for key, child in value.items():
            if _SENSITIVE.search(str(key)):
                raise ProofError("sensitive configuration key is forbidden at " + location)
            _reject_sensitive(child, location + "." + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive(child, "%s[%d]" % (location, index))


def _safe_relative(value):
    if not isinstance(value, str) or not value.strip():
        return False
    if re.match(r"^[A-Za-z]:", value) or value.startswith(("/", "\\")):
        return False
    path = PurePosixPath(value.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def validate_config(data):
    if not isinstance(data, dict):
        raise ProofError("configuration root must be an object")
    _reject_sensitive(data)
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise ProofError("unknown configuration key")
    if set(data) != _TOP_KEYS:
        raise ProofError("configuration is missing required sections")
    paths = data.get("paths")
    if not isinstance(paths, dict) or set(paths) != _PATH_KEYS:
        raise ProofError("paths must contain the fixed path set")
    for value in paths.values():
        if not _safe_relative(value):
            raise ProofError("paths must be relative and remain inside the package")
    runtime = data.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {"environment", "python"}:
        raise ProofError("runtime shape is invalid")
    if runtime["environment"] not in {"env", "env_50"} or not _safe_relative(runtime["python"]):
        raise ProofError("runtime environment is invalid")
    capture = data.get("capture")
    if not isinstance(capture, dict) or set(capture) != {"person_max_bytes", "voice_max_bytes"}:
        raise ProofError("capture shape is invalid")
    if any(not isinstance(v, int) or v <= 0 for v in capture.values()):
        raise ProofError("capture limits must be positive integers")
    output = data.get("output")
    if output != {"width": 720, "height": 1280, "fps": 25}:
        raise ProofError("first proof output must be 720x1280 at 25 fps")


def resolve_package_path(root, relative):
    if not _safe_relative(relative):
        raise ProofError("unsafe package-relative path")
    root = Path(root).resolve()
    candidate = (root / Path(relative.replace("/", str(Path("/"))))).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ProofError("path escapes package root") from error
    return candidate


def select_environment(gpu_name):
    value = str(gpu_name or "").lower()
    if re.search(r"rtx\s*50\d\d", value):
        return "env_50"
    return "env"


def normalization_command(ffmpeg, source, target, kind):
    base = [str(ffmpeg), "-nostdin", "-v", "error", "-y", "-i", str(source)]
    if kind == "person":
        return base + ["-map", "0:v:0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                       "-r", "25", "-movflags", "+faststart", str(target)]
    if kind == "voice":
        return base + ["-map", "0:a:0", "-vn", "-ac", "1", "-ar", "24000",
                       "-c:a", "pcm_s16le", "-f", "wav", str(target)]
    raise ProofError("unknown normalization kind")


def validate_video_probe(probe):
    duration = float(probe.get("duration") or 0)
    if duration < 20 or duration > 60:
        raise ProofError("MAT_VIDEO_DURATION")
    if int(probe.get("video_streams") or 0) != 1:
        raise ProofError("MAT_VIDEO_STREAMS")
    width, height = int(probe.get("width") or 0), int(probe.get("height") or 0)
    if min(width, height) < 720:
        raise ProofError("MAT_VIDEO_RESOLUTION")
    fps = float(probe.get("fps") or 0)
    if fps < 20 or fps > 60:
        raise ProofError("MAT_VIDEO_FPS")
    return True


def validate_audio_probe(probe):
    duration = float(probe.get("duration") or 0)
    if duration < 10 or duration > 30:
        raise ProofError("MAT_AUDIO_DURATION")
    if int(probe.get("channels") or 0) not in (1, 2):
        raise ProofError("MAT_AUDIO_CHANNELS")
    if not str(probe.get("codec") or "").startswith("pcm_"):
        raise ProofError("MAT_AUDIO_CODEC")
    return True
