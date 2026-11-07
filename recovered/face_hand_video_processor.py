"""Prepare face/hand video groups using silence VAD and bounded hand clips."""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4


def _duration(path):
    result = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    if result.returncode: raise RuntimeError(result.stderr.strip())
    return float(result.stdout.strip())


def _render_clip(source, target, start, duration):
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [shutil.which("ffmpeg") or "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(source),
               "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(target)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode: raise RuntimeError(result.stderr[-1200:])
    return str(target)


def _speech_ranges(path, minimum=1.0):
    total = _duration(path)
    result = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-i", str(path), "-af",
                             "silencedetect=noise=-35dB:d=0.5", "-f", "null", "-"], capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", result.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", result.stderr)]
    silences = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else total
        silences.append((max(0, start), min(total, end)))
    ranges, cursor = [], 0.0
    for start, end in silences:
        if start - cursor >= minimum: ranges.append((cursor, start))
        cursor = max(cursor, end)
    if total - cursor >= minimum: ranges.append((cursor, total))
    return ranges or [(0.0, total)]


def process_face_hand_video_group(face_video_path, hand_video_path="", output_root=None):
    from .face_hand_vad_split import clip_face_hand_video_group

    face=Path(face_video_path).expanduser().resolve()
    hand=Path(hand_video_path).expanduser().resolve() if hand_video_path else face
    root=Path(output_root or face.parent/"face_hand_video_groups")/uuid4().hex
    result=clip_face_hand_video_group(str(face),str(hand),output_dir=str(root))
    return {"group_dir":result["output_dir"],"face":[str(root/item) for item in result["face"]],
            "hand":[str(root/item) for item in result["hand"]],
            "face_count":result["face_count"],"hand_count":result["hand_count"],
            "manifest":result["manifest"]}
