"""Canonical video output names shared by live playback modes."""

_OUTPUT_MODE_ALIASES = {
    "window": "window",
    "cam": "virtual_cam",
    "camera": "virtual_cam",
    "vcam": "virtual_cam",
    "virtual_cam": "virtual_cam",
}


def normalize_output_mode(value, default="window"):
    key = str(value or default).strip().lower()
    normalized = _OUTPUT_MODE_ALIASES.get(key)
    if normalized is None:
        raise ValueError(f"不支持的视频输出模式: {value}")
    return normalized
