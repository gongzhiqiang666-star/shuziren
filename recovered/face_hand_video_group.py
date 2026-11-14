"""Load face and hand clips from the original video group layout."""

import json
from pathlib import Path

FACE_HAND_MANIFEST_NAME = "manifest.json"
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".m4v", ".mkv", ".webm"}


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
    return True, "", counts
