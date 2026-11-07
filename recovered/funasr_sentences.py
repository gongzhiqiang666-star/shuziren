"""Recovered timestamp and sentence utilities layered on FunASR."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .funasr_runtime import cleanup_funasr_model, load_funasr_model, transcribe_with_funasr


TERMINAL_PUNCT = "。！？!?"
SOFT_PUNCT = "，,；;、"
TARGET_SENTENCE_CHARS = 50
HARD_MAX_SENTENCE_CHARS = 80
DIRECT_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}


def _normalize_text(text: Any) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    return re.sub(r"\s+([，,。.!?！？；;：:])", r"\1", value)


def _split_text_by_terminal(text: str) -> List[str]:
    return [part for part in re.findall(rf".*?[{re.escape(TERMINAL_PUNCT)}]|.+$", _normalize_text(text)) if part]


def _ends_with_punct(text: str, chars: str) -> bool:
    return bool(text) and text[-1] in chars


def _expand_sentences_by_punct(sentences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    expanded = []
    for sentence in sentences:
        parts = _split_text_by_terminal(sentence.get("text", ""))
        if len(parts) <= 1:
            expanded.append(sentence)
            continue
        start, end = int(sentence["start"]), int(sentence["end"])
        total = sum(len(part) for part in parts) or 1
        cursor = start
        used = 0
        for index, part in enumerate(parts):
            used += len(part)
            part_end = end if index == len(parts) - 1 else start + round((end - start) * used / total)
            expanded.append({"start": cursor, "end": part_end, "text": part})
            cursor = part_end
    return expanded


def merge_timed_sentences(sentences: List[Dict[str, Any]], *, target_len: int = TARGET_SENTENCE_CHARS,
                          hard_max: int = HARD_MAX_SENTENCE_CHARS) -> List[Dict[str, Any]]:
    merged, current = [], None
    for sentence in _expand_sentences_by_punct(sentences):
        text = _normalize_text(sentence.get("text"))
        if not text:
            continue
        if current and (len(current["text"] + text) > hard_max or
                        (len(current["text"]) >= target_len and
                         _ends_with_punct(current["text"], TERMINAL_PUNCT + SOFT_PUNCT))):
            merged.append(current)
            current = None
        if current is None:
            current = {"start": int(sentence["start"]), "end": int(sentence["end"]), "text": text}
        else:
            current["end"] = int(sentence["end"])
            current["text"] += text
    if current:
        merged.append(current)
    return merged


def funasr_result_to_sentence_info(result: Any) -> List[Dict[str, Any]]:
    sentences = []
    for item in result or []:
        raw_sentences = item.get("sentence_info") or []
        if raw_sentences:
            for sentence in raw_sentences:
                start = sentence.get("start", sentence.get("start_time", 0))
                end = sentence.get("end", sentence.get("end_time", start))
                sentences.append({"start": int(start), "end": int(end),
                                  "text": _normalize_text(sentence.get("text"))})
            continue
        timestamps = item.get("timestamp") or item.get("timestamps") or []
        text = _normalize_text(item.get("text"))
        if timestamps and text:
            sentences.append({"start": int(timestamps[0][0]), "end": int(timestamps[-1][1]), "text": text})
    return merge_timed_sentences([item for item in sentences if item["text"] and item["end"] > item["start"]])


def _extract_audio_wav(media_path: str, output_wav: str) -> str:
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg")
    subprocess.run([ffmpeg, "-y", "-i", str(media_path), "-vn", "-ac", "1", "-ar", "16000",
                    str(output_wav)], capture_output=True, check=True)
    return str(output_wav)


def recognize_media_sentences(media_path: str, asr_weight_path: str, *, model: Any = None,
                              keep_model: bool = False) -> List[Dict[str, Any]]:
    source = Path(media_path)
    if not source.is_file():
        raise FileNotFoundError(f"文件不存在: {source}")
    owns_model = model is None
    if owns_model:
        model = load_funasr_model(asr_weight_path)
    try:
        if source.suffix.lower() in DIRECT_AUDIO_SUFFIXES:
            return funasr_result_to_sentence_info(transcribe_with_funasr(model, str(source)))
        with tempfile.TemporaryDirectory(prefix="lip_sync_asr_") as directory:
            asr_input = _extract_audio_wav(str(source), str(Path(directory) / "audio.wav"))
            return funasr_result_to_sentence_info(transcribe_with_funasr(model, asr_input))
    finally:
        if owns_model and not keep_model:
            cleanup_funasr_model(model)
