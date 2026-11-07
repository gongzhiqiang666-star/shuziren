"""Recovered OmniVoice voice synthesis entry point."""

from __future__ import annotations

import gc
import logging
import re
from threading import Lock
from pathlib import Path
from typing import Optional

from .voice_infer_common import CacheMixin, apply_speed, atempo_filters, output_path, resolve_reference, temp_dir


_LANGUAGES = {
    "zh": "Chinese", "cn": "Chinese", "chinese": "Chinese",
    "zh-cn": "Chinese", "zh-hans": "Chinese", "zh-sg": "Chinese",
    "zh-tw": "Chinese", "zh-hant": "Chinese",
    "en": "English", "english": "English", "en-us": "English",
    "en-gb": "English", "en-au": "English",
    "ja": "Japanese", "jp": "Japanese", "japanese": "Japanese", "ja-jp": "Japanese",
    "ko": "Korean", "korean": "Korean", "ko-kr": "Korean",
    "my-mm": "my-mm",
}


def detect_language(text) -> Optional[str]:
    if re.search(r"[\u4e00-\u9fff]", text or ""):
        return "Chinese"
    if re.search(r"[\u3040-\u30ff]", text or ""):
        return "Japanese"
    if re.search(r"[\uac00-\ud7af]", text or ""):
        return "Korean"
    if re.search(r"[A-Za-z]", text or ""):
        return "English"
    return None


def normalize_omnivoice_language(language) -> Optional[str]:
    if not language:
        return None
    return _LANGUAGES.get(str(language).strip().lower(), str(language).strip())


class VoiceSynthesizer(CacheMixin):
    def __init__(self, models_base_path, reference_audio, reference_text, device="cuda",
                 voice_id=None, voice_infer_version=None):
        self._lock = Lock()
        import torch
        requested_device = str(device or "cpu")
        self.device = (requested_device if not requested_device.startswith("cuda")
                       or torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if self.device.startswith("cuda") else torch.float32
        self.models_base_path = Path(models_base_path)
        self.model_dir = self._expected_model_dir()
        self.reference_audio = str(reference_audio)
        self.reference_text = (reference_text or "").strip()
        self.voice_id = voice_id
        self.voice_infer_version = voice_infer_version
        self._prompt_cache = {}
        self._check_and_download_model()
        print("开始加载 OmniVoice 模型...")
        print(f"OmniVoice 使用设备: {self.device}")
        from bin.voice_infer_v2.omnivoice.models.omnivoice import OmniVoice
        self.synthesizer = OmniVoice.from_pretrained(
            str(self.model_dir), device_map=self.device, dtype=self.dtype, load_asr=False)
        self.model = self.synthesizer
        self.sampling_rate = int(self.synthesizer.sampling_rate or 24000)
        print(f"OmniVoice 初始化完成，sampling_rate={self.sampling_rate}")

    @classmethod
    def from_voice_dir(cls, models_base_path, voice_base_dir, voice_id, device="cuda", voice_infer_version=None):
        audio, text = resolve_reference(voice_base_dir)
        return cls(models_base_path, audio, text, device, voice_id, voice_infer_version)

    def _get_temp_path(self): return temp_dir(self.models_base_path, "omnivoice")
    def _build_atempo_filters(self,speed): return atempo_filters(speed)
    def _apply_speed(self,input_path, output_path, speed): apply_speed(input_path, output_path, speed)

    def _model_dir(self):
        base = Path(self.models_base_path)
        for item in (
            base / "pretrained_models" / "OmniVoice",
            base / "pretrained_models" / "omnivoice",
            base / "OmniVoice",
            base / "omnivoice",
            base,
        ):
            if any((item / name).is_file() for name in ("model.safetensors", "pytorch_model.bin")):
                return item
        raise FileNotFoundError("OmniVoice model.safetensors was not found")

    def _expected_model_dir(self):
        base = Path(self.models_base_path)
        try:
            return self._model_dir()
        except FileNotFoundError:
            return base / "OmniVoice" if base.name.lower() == "pretrained_models" else base / "pretrained_models" / "OmniVoice"

    def _is_model_ready(self):
        try: self._model_dir(); return True
        except FileNotFoundError: return False

    def _check_and_download_model(self):
        try:
            return str(self._model_dir())
        except FileNotFoundError:
            try:
                return self._download_from_modelscope()
            except Exception:
                return self._download_from_huggingface()
    def _download_from_huggingface(self):
        from huggingface_hub import snapshot_download
        return snapshot_download("k2-fsa/OmniVoice", local_dir=str(self.model_dir))
    def _download_from_modelscope(self):
        from modelscope import snapshot_download
        return snapshot_download("k2-fsa/OmniVoice", local_dir=str(self.model_dir))

    def _validate_reference_inputs(self, reference_audio, reference_text):
        if not reference_audio or not Path(reference_audio).is_file(): raise FileNotFoundError(reference_audio)
        if not (reference_text or "").strip(): raise ValueError("reference_text is required by OmniVoice")

    def _build_prompt_cache_key(self,reference_audio, reference_text):
        resolved = Path(reference_audio).resolve()
        try:
            stat = resolved.stat()
            return (resolved, stat.st_mtime_ns, stat.st_size, reference_text)
        except FileNotFoundError:
            return (resolved, reference_text)

    def _load_model(self):
        return self.synthesizer

    def _get_voice_clone_prompt(self, reference_audio, reference_text):
        key = self._build_prompt_cache_key(reference_audio, reference_text)
        if key not in self._prompt_cache:
            self._prompt_cache[key] = self._load_model().create_voice_clone_prompt(reference_audio, reference_text)
        return self._prompt_cache[key]

    def synthesize(self, text, speed=1.0, reference_audio=None, reference_text=None,
                   language=None, use_cache=False) -> Optional[str]:
        with self._lock:
            try:
                call_reference_audio=reference_audio or self.reference_audio
                call_reference_text=(reference_text or self.reference_text).strip()
                self._validate_reference_inputs(call_reference_audio, call_reference_text)
                language = normalize_omnivoice_language(language) or detect_language(text)
                cached = self._cached(
                    text, speed, language, use_cache,
                    call_reference_audio, call_reference_text)
                if cached:
                    logging.info("音频缓存命中，直接复用: %s",cached)
                    return cached
                import torchaudio
                prompt = self._get_voice_clone_prompt(call_reference_audio, call_reference_text)
                audio_list = self._load_model().generate(
                    text=text, language=language, voice_clone_prompt=prompt)
                if not audio_list:
                    raise RuntimeError("OmniVoice 推理结果为空")
                audio=audio_list[0]
                raw = output_path(self._get_temp_path())
                result = output_path(self._get_temp_path()) if float(speed) != 1 else raw
                torchaudio.save(raw, audio.cpu(), self.synthesizer.sampling_rate)
                if result != raw:
                    self._apply_speed(raw, result, speed)
                    Path(raw).unlink(missing_ok=True)
                self._record(
                    result, text, speed, language,
                    call_reference_audio, call_reference_text)
                print(f"语音合成完成，输出文件: {result}")
                return result
            except Exception as error:
                logging.error("OmniVoice 合成失败: %s",error)
                return None

    def clear(self):
        """Release OmniVoice and its accelerator allocations.

        Ghidra shows the original deleting the synthesizer attribute (rather
        than merely assigning ``None``), running GC, and conditionally
        clearing the CUDA allocator before returning ``None``.
        """
        if hasattr(self, "synthesizer"):
            del self.synthesizer
        self.model = None
        self._prompt_cache.clear()
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, AttributeError):
            pass
        return None
