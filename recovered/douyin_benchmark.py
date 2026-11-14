"""Validation helpers for Douyin benchmark-video extraction."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


DOUYIN_HOSTS = ("douyin.com", "iesdouyin.com")
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".flv", ".m4v"}


def normalize_douyin_url(value):
    text = str(value or "").strip()
    match = re.search(r"https://[^\s<>\"']+", text)
    if not match:
        raise ValueError("请输入有效的抖音 HTTPS 视频链接")
    url = match.group(0).rstrip("，。！？；,!?;)]}")
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (parsed.scheme != "https" or parsed.username or parsed.password or
            not any(hostname == host or hostname.endswith("." + host) for host in DOUYIN_HOSTS)):
        raise ValueError("仅支持抖音官方 HTTPS 视频链接")
    return parsed.geturl()


def select_downloaded_video(stdout, working_directory):
    root = Path(working_directory).resolve()
    for line in reversed(str(stdout or "").splitlines()):
        value = line.strip().strip('"')
        if not value:
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            candidate = candidate.resolve(strict=True)
        except OSError:
            continue
        if (candidate.is_file() and candidate.is_relative_to(root) and
                candidate.suffix.lower() in VIDEO_SUFFIXES and candidate.stat().st_size > 0):
            return candidate
    raise RuntimeError("下载成功但未找到工具目录内的有效视频文件")


def resolve_ffprobe(runtime_dir):
    candidates = [
        Path(runtime_dir) / "env" / "ffmpeg" / "bin" / "ffprobe.exe",
        Path(runtime_dir) / "ffmpeg" / "bin" / "ffprobe.exe",
    ]
    discovered = shutil.which("ffprobe")
    if discovered:
        candidates.append(Path(discovered))
    result = next((path.resolve() for path in candidates if path.is_file()), None)
    if result is None:
        raise FileNotFoundError("未找到 FFprobe，无法验证下载视频")
    return result


def probe_video(video_path, ffprobe_path):
    result = subprocess.run([
        str(ffprobe_path), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(video_path),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        raise ValueError("下载结果不是可解码的视频")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list) or not any(stream.get("codec_type") == "video" for stream in streams):
        raise ValueError("下载结果不包含视频轨道")
    duration = (payload.get("format") or {}).get("duration")
    if duration not in (None, "") and float(duration) <= 0:
        raise ValueError("下载视频时长无效")
    return payload
