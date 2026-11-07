#!/usr/bin/env python3
"""Validate the secret-free configuration for the minimum real live proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path, PureWindowsPath
import re
from typing import Any


class ReadinessError(ValueError):
    """Raised when a readiness manifest is unsafe or outside the fixed scope."""


SENSITIVE_KEY = re.compile(
    r"(^|_)(password|passwd|secret|cookie|session|token|api_key|app_key|app_secret)($|_)",
    re.IGNORECASE,
)

_EXAMPLE = {
    "schema": 1,
    "runtime": {
        "root": "C:/yunchuang_v122/_internal",
        "environment": "env",
        "python": "C:/yunchuang_v122/_internal/env/python.exe",
    },
    "tts": {
        "name": "one-local-engine",
        "model_dir": "C:/live-assets/tts-model",
        "reference_audio": "C:/live-assets/voice/reference.wav",
        "reference_text": "C:/live-assets/voice/reference.txt",
    },
    "avatar": {
        "runtime": "yunchuang-image-infer",
        "model_dir": "C:/live-assets/avatar-model",
        "character_dir": "C:/live-assets/character-one",
    },
    "output": {
        "mode": "virtual_camera",
        "width": 1280,
        "height": 720,
        "fps": 25,
        "obs_scene": "minimum-live-proof",
    },
    "platform": {"required_for_this_run": False, "approval_status": "blocked"},
}

_FIELDS = {
    "runtime": {"root", "environment", "python"},
    "tts": {"name", "model_dir", "reference_audio", "reference_text"},
    "avatar": {"runtime", "model_dir", "character_dir"},
    "output": {"mode", "width", "height", "fps", "obs_scene"},
    "platform": {"required_for_this_run", "approval_status"},
}
_PATH_FIELDS = {
    ("runtime", "root"),
    ("runtime", "python"),
    ("tts", "model_dir"),
    ("tts", "reference_audio"),
    ("tts", "reference_text"),
    ("avatar", "model_dir"),
    ("avatar", "character_dir"),
}


def example_manifest() -> dict[str, Any]:
    return copy.deepcopy(_EXAMPLE)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ReadinessError("manifest cannot be read as JSON") from error
    if not isinstance(data, dict):
        raise ReadinessError("manifest root must be an object")
    return data


def _reject_sensitive_keys(value: Any, location: str = "manifest") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ReadinessError(f"non-string key at {location}")
            if SENSITIVE_KEY.search(key):
                raise ReadinessError(f"sensitive key at {location}.{key}")
            _reject_sensitive_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, f"{location}[{index}]")


def _object(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if isinstance(value, list):
        raise ReadinessError(f"exactly one {name} configuration is required")
    if not isinstance(value, dict):
        raise ReadinessError(f"exactly one {name} configuration is required")
    unknown = set(value) - _FIELDS[name]
    if unknown:
        raise ReadinessError(f"unknown key at {name}.{sorted(unknown)[0]}")
    missing = _FIELDS[name] - set(value)
    if missing:
        raise ReadinessError(f"missing key at {name}.{sorted(missing)[0]}")
    return value


def validate_manifest(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ReadinessError("manifest root must be an object")
    allowed = {"schema", *_FIELDS}
    unknown = set(data) - allowed
    if unknown:
        raise ReadinessError(f"unknown key at manifest.{sorted(unknown)[0]}")
    _reject_sensitive_keys(data)
    if data.get("schema") != 1:
        raise ReadinessError("schema must be 1")
    sections = {name: _object(data, name) for name in _FIELDS}
    for section, field in _PATH_FIELDS:
        value = sections[section][field]
        if not isinstance(value, str) or not value.strip() or not PureWindowsPath(value).is_absolute():
            raise ReadinessError(f"{section}.{field} must be an absolute Windows path")
    for section, fields in _FIELDS.items():
        for field in fields:
            if (section, field) not in _PATH_FIELDS and isinstance(_EXAMPLE[section][field], str):
                value = sections[section][field]
                if not isinstance(value, str) or not value.strip():
                    raise ReadinessError(f"{section}.{field} must be non-empty text")
    output = sections["output"]
    if output["mode"] not in {"virtual_camera", "srs"}:
        raise ReadinessError("output.mode must be virtual_camera or srs")
    if not isinstance(output["width"], int) or not 320 <= output["width"] <= 3840:
        raise ReadinessError("output.width is outside the first-proof range")
    if not isinstance(output["height"], int) or not 240 <= output["height"] <= 2160:
        raise ReadinessError("output.height is outside the first-proof range")
    if output["fps"] != 25:
        raise ReadinessError("output.fps must be 25 for the first proof")
    platform = sections["platform"]
    if not isinstance(platform["required_for_this_run"], bool):
        raise ReadinessError("platform.required_for_this_run must be boolean")
    if platform["approval_status"] not in {"approved", "blocked"}:
        raise ReadinessError("platform.approval_status must be approved or blocked")
    if platform["required_for_this_run"] and platform["approval_status"] != "approved":
        raise ReadinessError("a required platform gate must be approved")


if __name__ == "__main__":
    raise SystemExit("CLI is added in the next implementation task")
