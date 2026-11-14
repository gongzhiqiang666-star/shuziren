"""Recovered IndexTTS voice synthesis entry point."""

from __future__ import annotations

import gc
import logging
import os
import re
import wave
from pathlib import Path
from threading import Lock
from typing import Optional

from .voice_infer_common import CacheMixin, apply_speed, atempo_filters, output_path, resolve_reference, temp_dir


LONG_TEXT_CHARS = 300


def split_synthesis_text(text, max_chars=LONG_TEXT_CHARS):
    value = str(text or "").strip()
    if not value:
        return []
    units = [item.strip() for item in re.findall(r".*?(?:[。！？!?；;\n]+|$)", value, re.S) if item.strip()]
    chunks = []
    for unit in units:
        while len(unit) > max_chars:
            boundary = max(unit.rfind(mark, 0, max_chars + 1) for mark in ("，", ",", "、", " "))
            boundary = boundary + 1 if boundary >= max_chars // 2 else max_chars
            chunks.append(unit[:boundary].strip())
            unit = unit[boundary:].strip()
        if not unit:
            continue
        if chunks and len(chunks[-1]) + len(unit) <= max_chars:
            chunks[-1] += unit
        else:
            chunks.append(unit)
    return chunks


def concatenate_pcm_wavs(inputs, output):
    if not inputs:
        raise ValueError("没有可合并的 IndexTTS 音频片段")
    parameters = None
    with wave.open(os.fspath(output), "wb") as destination:
        for path in inputs:
            with wave.open(os.fspath(path), "rb") as source:
                current = (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
                if parameters is None:
                    parameters = current
                    destination.setnchannels(current[0])
                    destination.setsampwidth(current[1])
                    destination.setframerate(current[2])
                    destination.setcomptype(current[3], source.getcompname())
                elif current != parameters:
                    raise ValueError("IndexTTS 分段音频参数不一致")
                destination.writeframes(source.readframes(source.getnframes()))
    return os.fspath(output)


class VoiceSynthesizer(CacheMixin):
    def __init__(self, models_base_path, reference_audio, reference_text, device="cuda",
                 voice_id=None, voice_infer_version=None):
        self._lock = Lock()
        import torch
        requested_device = str(device or "cpu")
        self.device = (requested_device if not requested_device.startswith("cuda")
                       or torch.cuda.is_available() else "cpu")
        self.is_fp16 = self.device.startswith("cuda")
        self.models_base_path = Path(models_base_path)
        self.model_dir = self._ensure_model_dir()
        self.reference_audio = str(reference_audio) if reference_audio else ""
        self.reference_text = (reference_text or "").strip()
        self.voice_id = voice_id
        self.voice_infer_version = voice_infer_version
        from bin.voice_infer_v3.indextts.infer import IndexTTS
        self.model = IndexTTS(
            cfg_path=str(self.model_dir / "config.yaml"),
            model_dir=str(self.model_dir),
            is_fp16=self.is_fp16,
            device=self.device,
        )
        self.sampling_rate = 24000

    @classmethod
    def from_voice_dir(cls, models_base_path, voice_base_dir, voice_id, device="cuda", voice_infer_version=None):
        audio, text = resolve_reference(Path(voice_base_dir) / voice_id)
        return cls(models_base_path, audio, text, device, voice_id, voice_infer_version)

    def _get_temp_path(self):
        return temp_dir(self.models_base_path, "indextts")

    def _ensure_model_dir(self):
        base = Path(self.models_base_path)
        candidates = [base / "indextts", base / "pretrained_models" / "indextts", base]
        for item in candidates:
            if (item / "config.yaml").is_file():
                return item
        raise FileNotFoundError("IndexTTS config.yaml was not found")

    def _validate_reference_inputs(self, reference_audio):
        if not reference_audio or not Path(reference_audio).is_file():
            raise FileNotFoundError(f"invalid reference audio: {reference_audio}")

    def _load_model(self):
        return self.model

    def _build_atempo_filters(self,speed):
        return atempo_filters(speed)

    def _apply_speed(self,input_path, output_path, speed):
        apply_speed(input_path, output_path, speed)

    def synthesize(self, text, speed=1.0, reference_audio=None, reference_text=None,
                   language=None, use_cache=False) -> Optional[str]:
        with self._lock:
            try:
                call_reference_audio = str(reference_audio or self.reference_audio)
                call_reference_text = (reference_text or self.reference_text).strip()
                self._validate_reference_inputs(call_reference_audio)
                cached = self._cached(
                    text, speed, language, use_cache,
                    call_reference_audio, call_reference_text)
                if cached:
                    logging.info("音频缓存命中，直接复用: %s", cached)
                    return cached
                raw = output_path(self._get_temp_path())
                result = output_path(self._get_temp_path()) if float(speed) != 1.0 else raw
                staged = str(Path(raw).with_suffix(Path(raw).suffix + ".partial.wav"))
                parts = []
                import torch
                try:
                    chunks = split_synthesis_text(text)
                    if not chunks:
                        raise ValueError("text cannot be empty")
                    with torch.inference_mode():
                        for index, chunk in enumerate(chunks):
                            part = str(Path(raw).with_suffix(f".part-{index:04d}.wav"))
                            parts.append(part)
                            self.model.infer_fast(call_reference_audio, chunk, part, verbose=False)
                            if not Path(part).is_file() or Path(part).stat().st_size <= 44:
                                raise RuntimeError(f"IndexTTS 第 {index + 1} 段没有生成有效 WAV")
                    concatenate_pcm_wavs(parts, staged)
                    os.replace(staged, raw)
                    if result != raw:
                        accelerated = str(Path(result).with_suffix(Path(result).suffix + ".partial.wav"))
                        try:
                            self._apply_speed(raw, accelerated, speed)
                            os.replace(accelerated, result)
                        finally:
                            Path(accelerated).unlink(missing_ok=True)
                            Path(raw).unlink(missing_ok=True)
                finally:
                    Path(staged).unlink(missing_ok=True)
                    for part in parts:
                        Path(part).unlink(missing_ok=True)
                self._record(
                    result, text, speed, language,
                    call_reference_audio, call_reference_text)
                print(f"语音合成完成，输出文件: {result}")
                return result
            except Exception as error:
                logging.error("IndexTTS 合成失败: %s", error)
                return None

    def clear(self):
        if hasattr(self, "model"):
            del self.model
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, AttributeError):
            pass
        return None
