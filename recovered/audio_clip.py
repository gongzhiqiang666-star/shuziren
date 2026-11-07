"""Recovered FunASR-driven audio sentence splitter."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def _normalize_text(text):
    return re.sub(r"\s+", "", str(text or "")).strip()


def _funasr_result_to_sentence_info(result):
    sentences = []
    for item in result or []:
        for sentence in item.get("sentence_info") or []:
            start = sentence.get("start", sentence.get("start_time", 0))
            end = sentence.get("end", sentence.get("end_time", start))
            sentences.append({"text": _normalize_text(sentence.get("text", "")),
                              "start": int(start), "end": int(end)})
        if item.get("sentence_info"):
            continue
        timestamps = item.get("timestamp") or item.get("timestamps") or []
        text = _normalize_text(item.get("text", ""))
        if timestamps and text:
            sentences.append({"text": text, "start": int(timestamps[0][0]),
                              "end": int(timestamps[-1][1])})
    return [item for item in sentences if item["text"] and item["end"] > item["start"]]


def _runtime_functions():
    try:
        from tools.asr.funasr_runtime import (cleanup_funasr_model,
                                              load_funasr_model,
                                              transcribe_with_funasr)
    except ImportError:
        from .funasr_runtime import (cleanup_funasr_model, load_funasr_model,
                                     transcribe_with_funasr)
    return load_funasr_model, transcribe_with_funasr, cleanup_funasr_model


def process_and_split_audio(file_path, output_dir, asr_weight_path,
                            min_seconds=8, max_seconds=15):
    source, destination = Path(file_path), Path(output_dir)
    if not source.is_file():
        raise FileNotFoundError(source)
    if min_seconds <= 0 or max_seconds < min_seconds:
        raise ValueError("分段时长参数无效")
    destination.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg")
    audio_path = destination / "extracted_audio.wav"
    subprocess.run([ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
                    str(audio_path)], capture_output=True, check=True)
    load_model, transcribe, cleanup = _runtime_functions()
    model = None
    try:
        model = load_model(str(asr_weight_path))
        sentence_info = _funasr_result_to_sentence_info(transcribe(model, str(audio_path)))
    finally:
        cleanup(model)
    groups, current = [], []
    for sentence in sentence_info:
        prospective = sentence["end"] - (current[0]["start"] if current else sentence["start"])
        if current and prospective > max_seconds * 1000:
            groups.append(current)
            current = []
        current.append(sentence)
        if current[-1]["end"] - current[0]["start"] >= min_seconds * 1000:
            groups.append(current)
            current = []
    if current:
        if groups and current[-1]["end"] - groups[-1][0]["start"] <= max_seconds * 1000:
            groups[-1].extend(current)
        else:
            groups.append(current)
    outputs = []
    for index, group in enumerate(groups):
        start_ms, end_ms = group[0]["start"], group[-1]["end"]
        stem = f"segment_{index + 1:04d}"
        audio_output = destination / f"{stem}.wav"
        text_output = destination / f"{stem}.txt"
        subprocess.run([ffmpeg, "-y", "-i", str(audio_path), "-ss", f"{start_ms / 1000:.3f}",
                        "-t", f"{(end_ms - start_ms) / 1000:.3f}", str(audio_output)],
                       capture_output=True, check=True)
        text = "".join(item["text"] for item in group)
        text_output.write_text(text, encoding="utf-8")
        outputs.append({"audio_path": str(audio_output), "text_output_path": str(text_output),
                        "text": text, "start": start_ms, "end": end_ms,
                        "actual_duration": (end_ms - start_ms) / 1000})
    return outputs
