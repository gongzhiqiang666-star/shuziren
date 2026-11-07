"""Recovered high-level audio/video recognition entry point."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .whisper_runtime import (cleanup_whisper_model, load_whisper_model,
                              transcribe_with_whisper, whisper_result_to_text)


def recognize_audio(file_path, asr_weight_path):
    source = Path(file_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg")
    temp_audio_path = source.with_name(source.stem + "_temp.wav")
    text_output_path = source.with_suffix(".txt")
    subprocess.run([ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
                    str(temp_audio_path)], capture_output=True, check=True)
    model = None
    try:
        model = load_whisper_model(str(asr_weight_path))
        result = transcribe_with_whisper(model, str(temp_audio_path), word_timestamps=True)
        full_text = whisper_result_to_text(result)
        text_output_path.write_text(full_text, encoding="utf-8")
        return {"text": full_text, "output_path": str(text_output_path)}
    finally:
        try:
            cleanup_whisper_model(model)
        finally:
            temp_audio_path.unlink(missing_ok=True)
