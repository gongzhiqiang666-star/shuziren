"""Portrait output presets recovered from tools.output_resolution."""

import subprocess

DEFAULT_RESOLUTION = "720p"
PORTRAIT_RESOLUTION_MAP = {
    "480p": (480, 854),
    "720p": (720, 1280),
    "1080p": (1080, 1920),
    "2k": (1440, 2560),
    "4k": (2160, 3840),
}
RESOLUTION_RANK = {"480p": 0, "720p": 1, "1080p": 2, "2k": 3, "4k": 4}


def normalize_resolution_key(value, default=DEFAULT_RESOLUTION):
    key = str(value or "").strip().lower()
    return key if key in PORTRAIT_RESOLUTION_MAP else default


def resolve_portrait_size(resolution, default=DEFAULT_RESOLUTION):
    return PORTRAIT_RESOLUTION_MAP[normalize_resolution_key(resolution, default)]


def resolution_rank(resolution, default=DEFAULT_RESOLUTION):
    key = normalize_resolution_key(resolution, default)
    return int(RESOLUTION_RANK.get(key, RESOLUTION_RANK[default]))


def normalize_target_height(resolution, is_landscape):
    width, height = resolve_portrait_size(resolution)
    return width if is_landscape else height


def clamp_output_to_source(output_resolution, source_resolution, *, default=DEFAULT_RESOLUTION):
    output = normalize_resolution_key(output_resolution, default)
    source = normalize_resolution_key(source_resolution, None)
    if source is None or resolution_rank(output) <= resolution_rank(source):
        return output, None
    message = (
        f"输出清晰度 {output} 高于形象素材 {source}，已按素材清晰度输出，避免放大发糊；"
        f"若要 {output} 请重新按该清晰度克隆形象"
    )
    return source, message


def detect_primary_gpu_name():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=gpu_name", "--format=csv,noheader"],
            capture_output=True, text=True, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return ""
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
