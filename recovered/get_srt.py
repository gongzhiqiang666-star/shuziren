"""Recovered video-to-SRT pipeline built on the shared Whisper runtime."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .audio_duration import get_audio_duration
from .whisper_runtime import (cleanup_whisper_model, load_whisper_model,
                              transcribe_with_whisper, whisper_result_to_text)


PUNCTUATION = "。！？!?；;，,、"
MAX_SUBTITLE_CHARS = 24
MIN_SUBTITLE_MS = 500
MAX_SUBTITLE_MS = 4500
MAX_OVERLAP_RATIO = 0.5


def format_srt_time(milliseconds: int) -> str:
    value = max(0, int(milliseconds))
    hours, value = divmod(value, 3_600_000)
    minutes, value = divmod(value, 60_000)
    seconds, millis = divmod(value, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def normalize_subtitle_text(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"(?<=[,.!?;:])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[,.!?;:])", "", value)
    return value


def load_model(asr_weight_path: str) -> Any:
    return load_whisper_model(asr_weight_path)


def transcribe_video(model: Any, video_path: str) -> Dict[str, Any]:
    return transcribe_with_whisper(model, video_path, word_timestamps=True)


def _extract_audio_for_asr(video_path: str) -> str:
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg")
    descriptor, output = tempfile.mkstemp(prefix="shuziren-subtitle-asr-", suffix=".wav")
    os.close(descriptor)
    try:
        subprocess.run([ffmpeg, "-y", "-i", video_path, "-map", "0:a:0", "-vn", "-ac", "1",
                        "-ar", "16000", "-acodec", "pcm_s16le", output], capture_output=True, check=True)
        return output
    except Exception:
        Path(output).unlink(missing_ok=True)
        raise


def get_media_duration_ms(video_path: str) -> int:
    return round(get_audio_duration(video_path) * 1000)


def _normalize_timestamp_pair(value: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        start, end = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if end < start:
        start, end = end, start
    return round(start), round(end)


def _clamp_subtitle(start_ms: int, end_ms: int, text: str,
                    max_duration_ms: int) -> Optional[Tuple[int, int, str]]:
    text = normalize_subtitle_text(text)
    start = max(0, min(int(start_ms), max_duration_ms))
    end = max(start, min(int(end_ms), max_duration_ms))
    if not text or end <= start:
        return None
    end = min(max_duration_ms, max(end, min(start + MIN_SUBTITLE_MS, max_duration_ms)))
    if end - start > MAX_SUBTITLE_MS:
        end = start + MAX_SUBTITLE_MS
    return start, end, text


def _normalize_subtitle_timeline(subtitles, max_duration_ms):
    output, last_end = [], 0
    for start, end, text in sorted(subtitles, key=lambda item: (item[0], item[1])):
        item = _clamp_subtitle(start, end, text, max_duration_ms)
        if item is None:
            continue
        start, end, text = item
        if start < last_end:
            overlap_ms = last_end - start
            duration_ms = end - start
            if duration_ms <= 0 or overlap_ms >= duration_ms * MAX_OVERLAP_RATIO:
                continue
            start = last_end
        if end <= start:
            continue
        output.append((start, end, text))
        last_end = end
    return output


def _build_subtitles_from_sentence_info(result, max_duration_ms):
    rows = []
    for item in result.get("sentence_info") or []:
        try:
            start = int(float(item.get("start", 0)))
            end = int(float(item.get("end", start)))
        except (AttributeError, TypeError, ValueError):
            continue
        subtitle = _clamp_subtitle(start, end, item.get("text", ""), max_duration_ms)
        if subtitle is not None:
            rows.append(subtitle)
    return _normalize_subtitle_timeline(rows, max_duration_ms)


def _build_subtitles_from_timestamps(result, max_duration_ms):
    text = normalize_subtitle_text(result.get("text", ""))
    raw_pairs = result.get("timestamp") or result.get("timestamps") or []
    pairs = [pair for pair in (_normalize_timestamp_pair(value) for value in raw_pairs)
             if pair is not None]
    if not text or not pairs:
        return []

    subtitles, chunks = [], []
    current_start = current_end = None
    current_chars = pair_index = 0

    def flush():
        nonlocal chunks, current_start, current_end, current_chars
        if chunks and current_start is not None and current_end is not None:
            item = _clamp_subtitle(current_start, current_end, "".join(chunks), max_duration_ms)
            if item is not None:
                subtitles.append(item)
        chunks = []
        current_start = current_end = None
        current_chars = 0

    for char in (char for char in text if not char.isspace()):
        if char in PUNCTUATION:
            chunks.append(char)
            if (current_start is not None and current_end is not None and
                    current_end - current_start >= MIN_SUBTITLE_MS):
                flush()
            continue
        if pair_index >= len(pairs):
            chunks.append(char)
            continue
        start, end = pairs[pair_index]
        pair_index += 1
        current_chars += 1
        if current_start is None:
            current_start = start
        chunks.append(char)
        current_end = end
        if (current_chars >= MAX_SUBTITLE_CHARS or
                current_end - current_start >= MAX_SUBTITLE_MS):
            flush()
    flush()
    return _normalize_subtitle_timeline(subtitles, max_duration_ms)


def _build_subtitles_from_plain_text(result, max_duration_ms):
    text = normalize_subtitle_text(whisper_result_to_text(result))
    chars = [char for char in text if not char.isspace()]
    if not chars or max_duration_ms <= 0:
        return []
    chunks, current = [], []
    for char in chars:
        current.append(char)
        if char in PUNCTUATION or len(current) >= MAX_SUBTITLE_CHARS:
            chunk = normalize_subtitle_text("".join(current))
            if chunk:
                chunks.append(chunk)
            current = []
    if current:
        chunk = normalize_subtitle_text("".join(current))
        if chunk:
            chunks.append(chunk)
    if not chunks:
        return []

    total_chars = max(1, sum(len(chunk) for chunk in chunks))
    cursor_ms, subtitles = 0, []
    for index, chunk in enumerate(chunks):
        end_ms = (max_duration_ms if index == len(chunks) - 1 else
                  cursor_ms + int(max_duration_ms * len(chunk) / total_chars))
        subtitle = _clamp_subtitle(cursor_ms, end_ms, chunk, max_duration_ms)
        if subtitle is not None:
            subtitles.append(subtitle)
            cursor_ms = subtitle[1]
    return subtitles


def build_subtitles(result: Dict[str, Any], max_duration_ms: int):
    subtitles = _build_subtitles_from_sentence_info(result, max_duration_ms)
    return subtitles or _build_subtitles_from_timestamps(result, max_duration_ms) or \
        _build_subtitles_from_plain_text(result, max_duration_ms)


def save_srt(video_path: str, subtitles, output_path: Optional[str] = None) -> str:
    output = Path(output_path) if output_path else Path(video_path).with_suffix(".srt")
    blocks = [f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}"
              for index, (start, end, text) in enumerate(subtitles, 1)]
    output.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    return str(output)


def save_debug_json(video_path: str, result: Dict[str, Any], output_path: Optional[str] = None) -> str:
    output = Path(output_path) if output_path else Path(video_path).with_suffix(".asr_result.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output)


def cleanup_model(model: Optional[Any]) -> None:
    cleanup_whisper_model(model)


def generate_srt_for_video(video_path: str, asr_weight_path: str,
                           output_path: Optional[str] = None,
                           debug_json_path: Optional[str] = None) -> Dict[str, str]:
    audio_path = None;model = None
    try:
        audio_path = _extract_audio_for_asr(video_path)
        model = load_model(asr_weight_path)
        result = transcribe_video(model, audio_path)
        duration_ms = get_media_duration_ms(video_path)
        subtitles = build_subtitles(result, duration_ms)
        srt_path = save_srt(video_path, subtitles, output_path)
        json_path = save_debug_json(video_path, result, debug_json_path)
        return {"srt_path": srt_path, "debug_json_path": json_path}
    finally:
        cleanup_model(model)
        if audio_path:
            try:Path(audio_path).unlink()
            except FileNotFoundError:pass
