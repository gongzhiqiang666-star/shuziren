"""Recovered ZipVoice-Distill voice synthesis entry point."""

from __future__ import annotations

import json
import gc
import logging
from pathlib import Path
from threading import Lock
from typing import Optional

from .voice_infer_common import CacheMixin, output_path, resolve_reference, temp_dir


class VoiceSynthesizer(CacheMixin):
    def __init__(self, models_base_path, reference_audio, reference_text, device="cuda",
                 voice_id=None, voice_infer_version=None):
        self._lock = Lock()
        import torch
        requested_device = str(device or "cpu")
        self.device = (requested_device if not requested_device.startswith("cuda")
                       or torch.cuda.is_available() else "cpu")
        self.models_base_path = Path(models_base_path)
        self.model_dir = self._model_dir()
        self.reference_audio = str(reference_audio)
        self.reference_text = (reference_text or "").strip()
        self.voice_id = voice_id
        self.voice_infer_version = voice_infer_version
        self.model = None
        self.vocoder = self.tokenizer = self.feature_extractor = None
        self.sampling_rate = 24000
        self._check_and_download_model()
        self._load_model()

    @classmethod
    def from_voice_dir(cls, models_base_path, voice_base_dir, voice_id, device="cuda", voice_infer_version=None):
        audio, text = resolve_reference(voice_base_dir)
        return cls(models_base_path, audio, text, device, voice_id, voice_infer_version)

    def _get_temp_path(self): return temp_dir(self.models_base_path, "zipvoice")

    def _model_dir(self):
        base = Path(self.models_base_path)
        for item in (base / "zipvoice_distill" / "zipvoice_distill", base / "zipvoice_distill", base):
            if (item / "model.json").is_file() and (item / "model.pt").is_file(): return item
        raise FileNotFoundError("ZipVoice-Distill model files were not found")

    def _check_and_download_model(self): return str(self._model_dir())

    def _get_or_download_vocoder(self) -> Path:
        base = Path(self.models_base_path)
        for item in (base / "vocos-mel-24khz", base / "vocoder"):
            if (item / "pytorch_model.bin").is_file(): return item
        try:
            from modelscope import snapshot_download
            return Path(snapshot_download("AI-ModelScope/vocos-mel-24khz", local_dir=str(base / "vocos-mel-24khz")))
        except Exception as exc:
            raise FileNotFoundError("Vocos 24kHz model is missing") from exc

    def _load_model(self):
        if self.model is not None: return self.model
        import torch
        from bin.voice_infer.zipvoice.models.zipvoice_distill import ZipVoiceDistill
        from bin.voice_infer.zipvoice.tokenizer.tokenizer import EmiliaTokenizer
        from bin.voice_infer.zipvoice.utils.checkpoint import load_checkpoint
        from bin.voice_infer.zipvoice.utils.feature import VocosFbank
        from bin.voice_infer.zipvoice.bin.infer_zipvoice import get_vocoder
        root = self.model_dir
        self.tokenizer = EmiliaTokenizer(token_file=str(root / "tokens.txt"))
        config = json.loads((root / "model.json").read_text(encoding="utf-8"))
        self.model = ZipVoiceDistill(**config["model"], vocab_size=self.tokenizer.vocab_size,
                                    pad_id=self.tokenizer.pad_id)
        load_checkpoint(filename=str(root / "model.pt"), model=self.model, strict=True)
        self.model.to(self.device).eval()
        self.vocoder = get_vocoder(str(self._get_or_download_vocoder())).to(self.device).eval()
        self.feature_extractor = VocosFbank()
        self.sampling_rate = config["feature"]["sampling_rate"]
        return self.model

    def synthesize(self, text, speed=1.0, reference_audio=None, reference_text=None,
                   language=None, use_cache=False) -> Optional[str]:
        with self._lock:
            try:
                call_reference_audio = str(reference_audio or self.reference_audio)
                call_reference_text = (reference_text or self.reference_text).strip()
                if not Path(call_reference_audio).is_file():
                    raise FileNotFoundError(call_reference_audio)
                if not call_reference_text:
                    raise ValueError("reference_text is required by ZipVoice")
                cached = self._cached(
                    text, speed, language, use_cache,
                    call_reference_audio, call_reference_text)
                if cached:
                    logging.info("音频缓存命中，直接复用: %s", cached)
                    return cached
                from bin.voice_infer.zipvoice.bin.infer_zipvoice import generate_sentence
                result = output_path(self._get_temp_path())
                generate_sentence(
                    result, call_reference_text, call_reference_audio, text,
                    self.model, self.vocoder, self.tokenizer, self.feature_extractor,
                    self.device, speed=float(speed), sampling_rate=self.sampling_rate)
                self._record(
                    result, text, speed, language,
                    call_reference_audio, call_reference_text)
                print(f"语音合成完成，输出文件: {result}")
                return result
            except Exception as error:
                logging.error("ZipVoice 合成失败: %s", error)
                return None

    def clear(self):
        for name in ("model", "vocoder", "tokenizer", "feature_extractor"):
            if hasattr(self, name):
                delattr(self, name)
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, AttributeError):
            pass
        return None
