"""Recovered Vietnamese F5-TTS service client specialization."""

import os

try:
    from .voice_infer_malai_local import VoiceSynthesizer as BaseVoiceSynthesizer
except ImportError:
    from voice_infer_malai_local import VoiceSynthesizer as BaseVoiceSynthesizer


class VoiceSynthesizer(BaseVoiceSynthesizer):
    def __init__(self, reference_audio, reference_text="", voice_id=None, voice_infer_version=None, api_config=None):
        config = dict(api_config or {})
        config.setdefault("api_url", os.getenv("DH_VIETNAM_TTS_API_URL", "http://127.0.0.1:8112/tts"))
        config.setdefault("timeout", float(os.getenv("DH_VIETNAM_TTS_TIMEOUT", "300")))
        super().__init__(reference_audio, reference_text, voice_id,
                         voice_infer_version or "vietnam_local", config)

    def synthesize(self, text, speed=1.0, reference_audio=None, reference_text=None,
                   language=None, use_cache=False):
        return super().synthesize(text, speed, reference_audio, reference_text,
                                  language or "vi-VN", use_cache)
