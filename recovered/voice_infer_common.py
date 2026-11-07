"""Shared runtime helpers for the recovered local voice inference adapters."""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from .audio_cache import AudioCacheStore


def resolve_reference(voice_base_dir: str) -> tuple[str, str]:
    base = Path(voice_base_dir)
    audio = base / "ref_audio.wav"
    if not audio.is_file():
        wavs = sorted(base.glob("*.wav"))
        if not wavs:
            raise FileNotFoundError(f"reference audio not found in {base}")
        audio = wavs[0]
    text = ""
    for name in ("ref_text.txt", "reference_text.txt", "text.txt"):
        candidate = base / name
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8").strip()
            break
    return str(audio), text


def temp_dir(models_base_path: str, backend: str) -> str:
    preferred = Path(models_base_path) / "temp" / backend
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        return str(preferred.resolve())
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "yunchuang_voice" / backend
        fallback.mkdir(parents=True, exist_ok=True)
        return str(fallback)


def output_path(directory: str, suffix: str = ".wav") -> str:
    return str(Path(directory) / f"{uuid.uuid4().hex}{suffix}")


def atempo_filters(speed: float) -> list[str]:
    speed = float(speed)
    if speed <= 0:
        raise ValueError("speed must be greater than zero")
    factors: list[float] = []
    while speed > 2.0:
        factors.append(2.0)
        speed /= 2.0
    while speed < 0.5:
        factors.append(0.5)
        speed /= 0.5
    factors.append(speed)
    return [f"atempo={value:.8g}" for value in factors]


def apply_speed(input_path: str, output_path_: str, speed: float) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", input_path,
         "-filter:a", ",".join(atempo_filters(speed)), output_path_],
        check=True,
    )


class CacheMixin:
    def _cached(self, text: str, speed: float, language: Optional[str], use_cache: bool,
                reference_audio: Optional[str] = None,
                reference_text: Optional[str] = None):
        if not use_cache:
            return None
        return AudioCacheStore.find_cached_audio(
            self._get_temp_path(), self.voice_id, text, speed,
            self.voice_infer_version, language,
            self.reference_audio if reference_audio is None else reference_audio,
            self.reference_text if reference_text is None else reference_text,
        )

    def _record(self, path: str, text: str, speed: float, language: Optional[str],
                reference_audio: Optional[str] = None,
                reference_text: Optional[str] = None):
        AudioCacheStore.append_record(
            self._get_temp_path(), path, self.voice_id, text, speed,
            self.voice_infer_version, language,
            self.reference_audio if reference_audio is None else reference_audio,
            self.reference_text if reference_text is None else reference_text,
        )

    def clear(self):
        # Release every backend object that may retain model weights or prompt
        # tensors.  The original entry points expose one common ``clear`` API.
        for name in ("model", "vocoder", "tokenizer", "feature_extractor"):
            if hasattr(self, name):
                setattr(self, name, None)
        prompt_cache = getattr(self, "_prompt_cache", None)
        if prompt_cache is not None:
            prompt_cache.clear()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if hasattr(torch, "mps"):
                torch.mps.empty_cache()
        except Exception:
            pass
