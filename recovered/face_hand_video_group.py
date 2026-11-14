"""Load face and hand clips from the original video group layout."""

import json
import os
from pathlib import Path
import shutil
import subprocess

FACE_HAND_MANIFEST_NAME = "manifest.json"
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".m4v", ".mkv", ".webm"}


def _resolve_ffprobe():
    configured = os.environ.get("FFPROBE_PATH")
    if configured and Path(configured).is_file():
        return configured
    ffmpeg = os.environ.get("FFMPEG_PATH")
    if ffmpeg:
        sibling = Path(ffmpeg).with_name(
            "ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe"
        )
        if sibling.is_file():
            return str(sibling)
    return shutil.which("ffprobe")


def _probe_video_file(path):
    ffprobe = _resolve_ffprobe()
    if not ffprobe:
        return False, "未找到 FFprobe，无法验证视频素材"
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_type,width,height",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        payload = json.loads(result.stdout or "{}") if result.returncode == 0 else {}
        streams = payload.get("streams") if isinstance(payload, dict) else None
        stream = streams[0] if isinstance(streams, list) and streams else None
        if (not isinstance(stream, dict) or stream.get("codec_type") != "video"
                or int(stream.get("width") or 0) <= 0
                or int(stream.get("height") or 0) <= 0):
            return False, f"视频素材无法解码：{Path(path).name}"
        return True, ""
    except (OSError, ValueError, subprocess.SubprocessError):
        return False, f"视频素材探测失败：{Path(path).name}"


def _list_videos(directory):
    if not directory.is_dir():
        return []
    return sorted(
        str(path.resolve()) for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def _resolve_listed(group_dir, entries):
    resolved = []
    for item in entries:
        path = Path(str(item).strip())
        if not path.is_absolute():
            path = group_dir / path
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            resolved.append(str(path.resolve()))
    return resolved


def load_face_hand_video_group(group_dir):
    root = Path(group_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"视频组目录不存在：{root}")
    manifest_path = root / FACE_HAND_MANIFEST_NAME
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("视频组 manifest 格式错误")

    clips = {}
    for name in ("face", "hand"):
        entries = manifest.get(name)
        if isinstance(entries, dict):
            entries = entries.get("files")
        clips[name] = (
            _resolve_listed(root, entries) if isinstance(entries, list)
            else _list_videos(root / name)
        )
    return {"group_dir": str(root), **clips, "manifest": manifest}


def validate_face_hand_video_group(group_dir):
    try:
        group = load_face_hand_video_group(group_dir)
    except (OSError, ValueError) as error:
        return False, str(error), {}
    counts = {f"{name}_count": len(group[name]) for name in ("face", "hand")}
    for name in ("face", "hand"):
        if not counts[f"{name}_count"]:
            return False, f"视频组缺少 {name}/ 视频", counts
        for item in group[name]:
            try:
                if Path(item).stat().st_size <= 0:
                    return False, f"视频组包含空的 {name} 素材：{Path(item).name}", counts
            except OSError:
                return False, f"视频组无法读取 {name} 素材：{Path(item).name}", counts
            decodable, probe_error = _probe_video_file(item)
            if not decodable:
                return False, f"{name} {probe_error}", counts
    return True, "", counts
