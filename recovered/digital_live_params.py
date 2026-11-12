"""Build the keyword arguments used by the digital-human runtime."""

from pathlib import Path

from .output_resolution import normalize_resolution_key, resolve_portrait_size


VIDEO_DRIVE_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".wmv"}


def iter_video_drive_files(path):
    source = Path(path)
    if not source.exists():
        raise ValueError("视频驱动素材不存在，请重新选择")
    if source.is_dir():
        files = sorted(
            str(file) for file in source.iterdir()
            if file.is_file() and file.suffix.lower() in VIDEO_DRIVE_EXTENSIONS
        )
        if not files:
            raise ValueError("视频驱动文件夹内未找到可用视频文件")
        return files
    if source.is_file() and source.suffix.lower() in VIDEO_DRIVE_EXTENSIONS:
        return [str(source)]
    raise ValueError("视频驱动素材必须是视频文件，或包含视频文件的文件夹")


def is_required_video_fps(fps):
    return round(float(fps)) == 25


def validate_video_drive_assets(path):
    from .video_player import _open_media_source

    for file in iter_video_drive_files(path):
        with _open_media_source(file) as container:
            if not container.streams.video:
                raise ValueError(f"视频驱动素材没有视频轨道：{file}")
            stream = container.streams.video[0]
            width, height = stream.width, stream.height
            if max(width, height) > 1920 or min(width, height) > 1080:
                raise ValueError(
                    f"视频驱动素材分辨率必须为 1080P 及以下，当前文件 {file} ({width}×{height})"
                    "。请先压缩到 1920x1080 或 1080x1920 以内。"
                )
            fps = stream.average_rate
            if fps is None:
                raise ValueError(f"无法识别视频帧率: {file}")
            if not is_required_video_fps(fps):
                raise ValueError(f"视频帧率必须为 25 FPS，当前文件 {file} ({float(fps):g} FPS)")


def build_local_params(live_data):
    input_mode = live_data.get("input_mode", "file")
    if input_mode not in ("file", "camera", "video", "rtmp", "dual"):
        raise ValueError(f"不支持的驱动模式: {input_mode}")
    video_path = (live_data.get("video_path_for_driving") or "").strip()
    rtmp_value = live_data.get("rtmp_url_for_driving")
    rtmp_url = rtmp_value.strip() if isinstance(rtmp_value, str) else ""
    if input_mode == "video":
        if not video_path:
            raise ValueError("使用视频驱动模式时，必须提供视频文件路径")
        validate_video_drive_assets(video_path)
    if input_mode == "rtmp" and not rtmp_url:
        raise ValueError("使用 RTMP 流驱动模式时，必须提供 RTMP 地址")
    try:
        camera_index = int(live_data.get("selected_camera_index"))
    except (TypeError, ValueError, OverflowError):
        camera_index = -1
    camera_resolution = (live_data.get("camera_resolution") or "").strip() or "1280x720"
    if input_mode == "camera" and camera_resolution not in {
        "1280x720", "720x1280", "1920x1080", "1080x1920",
    }:
        raise ValueError("使用摄像头输入模式时，必须选择正确的分辨率（横屏720/1080或竖屏720/1080）")
    language = live_data.get("language") or "zh-CN"
    language_key = language.strip().lower().replace("_", "-")
    near_clone = bool(live_data.get("use_near_audio_clone"))
    resolution = normalize_resolution_key(live_data.get("output_resolution"))
    width, height = resolve_portrait_size(resolution)
    return {
        "model_id": (live_data.get("model_id") or live_data.get("imageModelId") or "").strip(),
        "voice_id": (live_data.get("voice_id") or "").strip() or None,
        "voice_infer_version": live_data.get("voice_infer_version") or "v1",
        "language": language,
        "voice_speed": float(live_data.get("voice_speed") or 1.1),
        "image_output_mode": live_data.get("image_output_mode", "cam"),
        "is_interrupt": bool(live_data.get("is_interrupt")),
        "enable_action_generalization": bool(live_data.get("enable_action_generalization")),
        "input_mode": input_mode,
        "camera_index": camera_index,
        "camera_resolution": camera_resolution,
        "video_path_for_driving": video_path,
        "rtmp_url_for_driving": rtmp_url,
        "enable_occluder": bool(live_data.get("enable_occluder")),
        "occluder_model_path": live_data.get("occluder_model_path") or "",
        "live_streamer_name": live_data.get("live_streamer_name") or "",
        "use_audio_cache": bool(live_data.get("use_audio_cache", True)),
        "script_input_mode": live_data.get("script_input_mode") or "text",
        "script_audio_dir": live_data.get("script_audio_dir") or "",
        "origin_idle_video_mode": bool(live_data.get("origin_idle_video_mode")),
        "use_near_audio_clone": near_clone and (language_key == "zh" or language_key.startswith("zh-")),
        "output_resolution": resolution,
        "window_width": width,
        "window_height": height,
    }
