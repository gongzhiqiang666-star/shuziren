"""Source-controlled held-product drive-video normalization."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from fractions import Fraction
from pathlib import Path


DRIVE_FPS = 25
DRIVE_WIDTH = 1080
DRIVE_HEIGHT = 1920
DRIVE_SPEC = "1080x1920@25fps/h264"


def portrait_filter():
    return ("scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,"
            "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")


def _file(value, label):
    supplied = Path(str(value or ""))
    if supplied.is_symlink():
        raise ValueError(f"{label}不是普通文件")
    path = supplied.expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"{label}不存在或为空")
    return path


def _tool(value, label):
    path = Path(str(value or "")).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"缺少{label}")
    return path


def _run(command, timeout=600):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, creationflags=flags)
    if completed.returncode:
        detail = completed.stderr.strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "媒体处理失败")
    return completed


def probe_video(path, *, ffprobe):
    source = _file(path, "源视频")
    executable = _tool(ffprobe, "FFprobe")
    completed = _run([
        str(executable), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)])
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("FFprobe 返回无效 JSON") from error
    streams = value.get("streams") if isinstance(value, dict) else None
    video = next((item for item in streams or [] if item.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("源文件没有视频轨")
    rate = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1")
    try:
        fps = float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    duration = video.get("duration") or (value.get("format") or {}).get("duration")
    return {
        "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
        "fps": fps, "codec": str(video.get("codec_name") or "").lower(),
        "duration": float(duration or 0),
        "has_audio": any(item.get("codec_type") == "audio" for item in streams or []),
    }


def is_drive_spec(info):
    return (isinstance(info, dict) and info.get("width") == DRIVE_WIDTH
            and info.get("height") == DRIVE_HEIGHT and info.get("codec") == "h264"
            and abs(float(info.get("fps") or 0) - DRIVE_FPS) < 0.01)


def _publish(command, destination):
    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise ValueError("驱动视频输出必须是 MP4")
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.pending.mp4")
    try:
        _run([*command, str(pending)])
        if not pending.is_file() or pending.stat().st_size <= 0:
            raise RuntimeError("媒体处理未生成输出")
        os.replace(pending, destination)
        return destination
    finally:
        pending.unlink(missing_ok=True)


def write_drive_video(src, dest, *, ffmpeg, ffprobe, keep_audio=False):
    source = _file(src, "源视频")
    executable = _tool(ffmpeg, "FFmpeg")
    info = probe_video(source, ffprobe=ffprobe)
    destination = Path(dest).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise ValueError("驱动视频输出必须是 MP4")
    if source == destination:
        raise ValueError("输入和输出视频不能相同")
    if is_drive_spec(info) and (keep_audio or not info["has_audio"]):
        destination.parent.mkdir(parents=True, exist_ok=True)
        pending = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.pending")
        try:
            shutil.copyfile(source, pending)
            os.replace(pending, destination)
            return destination
        finally:
            pending.unlink(missing_ok=True)
    command = [str(executable), "-y", "-i", str(source), "-vf", portrait_filter(),
               "-r", str(DRIVE_FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    command += ["-c:a", "aac", "-b:a", "192k"] if keep_audio and info["has_audio"] else ["-an"]
    command += ["-movflags", "+faststart"]
    return _publish(command, destination)


def make_pingpong_video(src, dest, *, ffmpeg):
    source = _file(src, "源视频")
    executable = _tool(ffmpeg, "FFmpeg")
    destination = Path(dest).expanduser().resolve()
    if source == destination:
        raise ValueError("输入和输出视频不能相同")
    filters = (f"[0:v]{portrait_filter()},fps={DRIVE_FPS},split=2[forward][copy];"
               "[copy]reverse[backward];[forward][backward]concat=n=2:v=1:a=0[out]")
    return _publish([str(executable), "-y", "-i", str(source), "-filter_complex", filters,
                     "-map", "[out]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                     "-movflags", "+faststart"], destination)
