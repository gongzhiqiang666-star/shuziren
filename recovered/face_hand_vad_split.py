"""Recovered energy-VAD cutter used by ``tools.face_hand_video``."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

FRAME_MS = 20
TARGET_SAMPLE_RATE = 16000
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 25
DEFAULT_MIN_CLIP_MS = 3000
DEFAULT_MAX_CLIP_MS = 30000
DEFAULT_FACE_KEEP_MIN_MS = 1000
DEFAULT_RMS_SILENCE_THRES = 0.015
DEFAULT_MIN_SPEECH_RUN_MS = 200
DEFAULT_SPEECH_MERGE_GAP_MS = 500
FACE_HAND_MANIFEST_NAME = "manifest.json"
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
_CUT_WORKERS = max(1, min(4, os.cpu_count() or 1))


def _resolve_ffmpeg():
    return os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg") or "ffmpeg"


def _resolve_ffprobe():
    configured = os.environ.get("FFMPEG_PATH")
    if configured:
        sibling = Path(configured).with_name("ffprobe.exe" if Path(configured).suffix.lower() == ".exe" else "ffprobe")
        if sibling.is_file():
            return str(sibling)
    return shutil.which("ffprobe") or "ffprobe"


def _extract_wav_16k(media_path: str, wav_path: str) -> None:
    result = subprocess.run([_resolve_ffmpeg(), "-y", "-i", media_path, "-vn", "-ac", "1", "-ar",
                             str(TARGET_SAMPLE_RATE), "-acodec", "pcm_s16le", wav_path], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-2000:])


def _probe_duration_ms(media_path: str) -> int:
    result = subprocess.run([_resolve_ffprobe(), "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=nw=1:nk=1", media_path], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return max(0, round(float(result.stdout.strip()) * 1000))


def _frame_rms_series(wav_path: str, *, frame_ms: int = FRAME_MS):
    with wave.open(wav_path, "rb") as source:
        rate, channels, width = source.getframerate(), source.getnchannels(), source.getsampwidth()
        if width != 2:
            raise ValueError(f"只支持 16-bit PCM，实际 sampwidth={width}")
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    frame_samples = max(1, round(rate * frame_ms / 1000))
    count = (len(samples) + frame_samples - 1) // frame_samples
    padded = np.zeros(count * frame_samples, dtype=np.float32)
    padded[:len(samples)] = samples.astype(np.float32) / 32768.0
    rms = np.sqrt(np.mean(padded.reshape(count, frame_samples) ** 2, axis=1)) if count else np.zeros(0)
    return rms, rate


def _runs_from_mask(mask: np.ndarray, *, frame_ms: int):
    runs, start = [], None
    for index, enabled in enumerate(np.asarray(mask, dtype=bool)):
        if enabled and start is None:
            start = index
        elif not enabled and start is not None:
            runs.append((start * frame_ms, index * frame_ms)); start = None
    if start is not None:
        runs.append((start * frame_ms, len(mask) * frame_ms))
    return runs


def _merge_close_segments(segments, *, max_gap_ms: int):
    merged = []
    for start, end in sorted(segments):
        if merged and start - merged[-1][1] <= max_gap_ms:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        elif end > start:
            merged.append((int(start), int(end)))
    return merged


def detect_speech_by_energy(wav_path: str, *, rms_silence_thres: float = DEFAULT_RMS_SILENCE_THRES,
                            frame_ms: int = FRAME_MS, min_speech_run_ms: int = DEFAULT_MIN_SPEECH_RUN_MS,
                            merge_gap_ms: int = DEFAULT_SPEECH_MERGE_GAP_MS):
    rms, _ = _frame_rms_series(wav_path, frame_ms=frame_ms)
    segments = _runs_from_mask(rms >= rms_silence_thres, frame_ms=frame_ms)
    segments = [(a, b) for a, b in segments if b - a >= min_speech_run_ms]
    return _merge_close_segments(segments, max_gap_ms=merge_gap_ms)


def _snap_ms(value_ms: int, *, duration_ms=None):
    value = max(0, round(value_ms / FRAME_MS) * FRAME_MS)
    return min(value, duration_ms) if duration_ms is not None else value


def _snap_segments(segments, *, duration_ms: int):
    return [(a, b) for a, b in ((_snap_ms(a, duration_ms=duration_ms),
                                 _snap_ms(b, duration_ms=duration_ms)) for a, b in segments) if b > a]


def _split_long_segment(start_ms: int, end_ms: int, *, min_ms: int, max_ms: int):
    pieces = []
    cursor = start_ms
    while end_ms - cursor > max_ms:
        pieces.append((cursor, cursor + max_ms)); cursor += max_ms
    remain = end_ms - cursor
    if remain >= min_ms:
        pieces.append((cursor, end_ms))
    elif pieces and remain > 0:
        pieces[-1] = (pieces[-1][0], end_ms)
    return pieces


def _fit_face_segments(segments, *, min_ms: int, max_ms: int, keep_min_ms: int):
    usable = [(a, b) for a, b in segments if b - a >= keep_min_ms]
    fitted = []
    pending = None
    for start, end in usable:
        if end - start >= min_ms:
            if pending:
                start = pending[0]; pending = None
            fitted.extend(_split_long_segment(start, end, min_ms=min_ms, max_ms=max_ms))
        elif pending and end - pending[0] <= max_ms:
            pending = (pending[0], end)
        else:
            if pending and pending[1] - pending[0] >= min_ms:
                fitted.append(pending)
            pending = (start, end)
    if pending and pending[1] - pending[0] >= min_ms:
        fitted.append(pending)
    return fitted


def plan_hand_random_segments(duration_ms: int, *, min_ms: int = DEFAULT_MIN_CLIP_MS,
                              max_ms: int = DEFAULT_MAX_CLIP_MS):
    if duration_ms <= 0 or min_ms <= 0 or max_ms < min_ms:
        return []
    rng = random.Random(duration_ms)
    output, cursor = [], 0
    while duration_ms - cursor >= min_ms:
        length = min(duration_ms - cursor, rng.randint(min_ms, max_ms))
        output.append((cursor, cursor + length)); cursor += length
    if output and cursor < duration_ms:
        output[-1] = (output[-1][0], duration_ms)
    return output


def plan_face_vad_segments(wav_path: str, duration_ms: int, *, min_ms: int = DEFAULT_MIN_CLIP_MS,
                           max_ms: int = DEFAULT_MAX_CLIP_MS, keep_min_ms: int = DEFAULT_FACE_KEEP_MIN_MS,
                           rms_silence_thres: float = DEFAULT_RMS_SILENCE_THRES,
                           merge_gap_ms: int = DEFAULT_SPEECH_MERGE_GAP_MS):
    speech = detect_speech_by_energy(wav_path, rms_silence_thres=rms_silence_thres,
                                     merge_gap_ms=merge_gap_ms)
    return _snap_segments(_fit_face_segments(speech, min_ms=min_ms, max_ms=max_ms,
                                             keep_min_ms=keep_min_ms), duration_ms=duration_ms)


def _cut_clip(source: str, start_ms: int, end_ms: int, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    vf = (f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
          f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={TARGET_FPS}")
    command = [_resolve_ffmpeg(), "-y", "-ss", f"{start_ms / 1000:.3f}", "-i", source,
               "-t", f"{(end_ms - start_ms) / 1000:.3f}", "-vf", vf, "-c:v", "libx264",
               "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
               "-ar", "48000", "-ac", "1", "-b:a", "128k", "-movflags", "+faststart", output_path]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-2000:])


def _validate_video_file(path: str, *, label: str):
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label}视频不存在: {resolved}")
    if resolved.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"{label}视频格式不支持: {resolved.suffix}")
    return str(resolved)


def clip_face_hand_video_group(face_video_path: str, hand_video_path: str, *, output_dir=None,
                               min_clip_ms: int = DEFAULT_MIN_CLIP_MS,
                               max_clip_ms: int = DEFAULT_MAX_CLIP_MS,
                               face_keep_min_ms: int = DEFAULT_FACE_KEEP_MIN_MS,
                               rms_silence_thres: float = DEFAULT_RMS_SILENCE_THRES,
                               merge_gap_ms: int = DEFAULT_SPEECH_MERGE_GAP_MS):
    face = _validate_video_file(face_video_path, label="人脸")
    hand = _validate_video_file(hand_video_path, label="人手")
    root = Path(output_dir or Path(face).parent / ("face_hand_vad_" + datetime.now().strftime("%Y%m%d_%H%M%S")))
    root.mkdir(parents=True, exist_ok=True)
    face_duration, hand_duration = _probe_duration_ms(face), _probe_duration_ms(hand)
    with TemporaryDirectory() as temporary:
        wav = str(Path(temporary) / "face_16k.wav")
        _extract_wav_16k(face, wav)
        face_segments = plan_face_vad_segments(wav, face_duration, min_ms=min_clip_ms, max_ms=max_clip_ms,
                                               keep_min_ms=face_keep_min_ms,
                                               rms_silence_thres=rms_silence_thres, merge_gap_ms=merge_gap_ms)
    hand_segments = plan_hand_random_segments(hand_duration, min_ms=min_clip_ms, max_ms=max_clip_ms)
    jobs = []
    for kind, source, segments in (("face", face, face_segments), ("hand", hand, hand_segments)):
        for index, (start, end) in enumerate(segments, 1):
            jobs.append((source, start, end, str(root / kind / f"{kind}_{index:03d}.mp4")))
    with ThreadPoolExecutor(max_workers=_CUT_WORKERS) as pool:
        futures = [pool.submit(_cut_clip, *job) for job in jobs]
        for future in as_completed(futures):
            future.result()
    face_rel = [str(Path(job[3]).relative_to(root)) for job in jobs if "/face/" in job[3]]
    hand_rel = [str(Path(job[3]).relative_to(root)) for job in jobs if "/hand/" in job[3]]
    manifest = {"created_at": datetime.now().isoformat(), "face_source": face, "hand_source": hand,
                "face": face_rel, "hand": hand_rel, "face_count": len(face_rel), "hand_count": len(hand_rel),
                "face_method": "energy_vad", "hand_method": "random_duration"}
    (root / FACE_HAND_MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"output_dir": str(root), "manifest": str(root / FACE_HAND_MANIFEST_NAME), **manifest}
