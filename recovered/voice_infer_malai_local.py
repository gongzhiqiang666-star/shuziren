"""Recovered request-only client for the independently started Malaysian F5-TTS service."""

from __future__ import annotations

import base64
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import requests

try:
    from .audio_cache import AudioCacheStore
except ImportError:
    from audio_cache import AudioCacheStore


DEFAULT_API_URL = "http://127.0.0.1:8111/tts"
DEFAULT_LANGUAGE = "ms-MY"
DEFAULT_VERSION = "malai_local"
SERVICE_LABEL = "Malaysian local TTS"
ENV_API_URL = "DH_MALAI_TTS_API_URL"
ENV_TIMEOUT = "DH_MALAI_TTS_TIMEOUT"


class VoiceSynthesizer:
    def __init__(self, reference_audio: str, reference_text: str = "", voice_id=None,
                 voice_infer_version=None, api_config=None):
        self.reference_audio = str(Path(reference_audio).expanduser().resolve())
        self.reference_text = str(reference_text or "")
        self.voice_id = voice_id
        self.voice_infer_version = voice_infer_version or DEFAULT_VERSION
        self.api_config = dict(api_config or {})
        self.temp_dir = Path(self.api_config.get("temp_dir") or tempfile.gettempdir()) / self.voice_infer_version
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._validate_reference_inputs(self.reference_audio)

    @classmethod
    def from_voice_dir(cls, models_base_path: str, voice_base_dir: str, voice_id: str,
                       device="cuda", voice_infer_version=None, api_config=None):
        base = Path(voice_base_dir) / str(voice_id)
        audio = base / "ref_audio.wav"; text = base / "ref_text.txt"
        return cls(str(audio), text.read_text(encoding="utf-8").strip() if text.is_file() else "",
                   voice_id=voice_id, voice_infer_version=voice_infer_version, api_config=api_config)

    def _get_temp_path(self):
        return str(self.temp_dir / f"{uuid4().hex}.wav")

    def _validate_reference_inputs(self, reference_audio):
        if not Path(reference_audio).is_file(): raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

    def _request_candidates(self):
        configured = self.api_config.get("api_url") or os.getenv(ENV_API_URL) or DEFAULT_API_URL
        base = configured.rstrip("/")
        values = [base]
        if not base.endswith(("/tts", "/infer", "/api/infer")):
            values.extend((base + "/tts", base + "/infer", base + "/api/infer"))
        return list(dict.fromkeys(values))

    def _write_response_bytes(self, data, content_type):
        suffix = ".mp3" if "mpeg" in content_type else ".flac" if "flac" in content_type else ".ogg" if "ogg" in content_type else ".wav"
        path = self.temp_dir / f"{uuid4().hex}{suffix}"; path.write_bytes(data); return str(path)

    def _copy_local_audio(self, path_value):
        source = Path(path_value).expanduser()
        if not source.is_file(): return None
        target = self.temp_dir / f"{uuid4().hex}{source.suffix or '.wav'}"; shutil.copyfile(source, target); return str(target)

    def _download_audio(self, url):
        response = requests.get(url, timeout=float(os.getenv(ENV_TIMEOUT, "300"))); response.raise_for_status()
        return self._write_response_bytes(response.content, response.headers.get("Content-Type", ""))

    def _decode_base64_audio(self, value):
        try:
            encoded = str(value).partition(",")[2] if str(value).startswith("data:") else str(value)
            return self._write_response_bytes(base64.b64decode(encoded), "audio/wav")
        except Exception: return None

    def _extract_audio_from_json(self, payload):
        if not isinstance(payload, dict): return None
        for key in ("audio_file", "audio_path", "path", "filename"):
            if payload.get(key):
                result = self._copy_local_audio(payload[key])
                if result: return result
        for key in ("audio_url", "download_url", "url"):
            if payload.get(key): return self._download_audio(payload[key])
        for key in ("audio_base64", "audio", "data"):
            value = payload.get(key)
            if isinstance(value, dict):
                result = self._extract_audio_from_json(value)
            elif isinstance(value, str): result = self._decode_base64_audio(value)
            else: result = None
            if result: return result
        return None

    def _response_to_audio_path(self, response):
        response.raise_for_status(); content_type = response.headers.get("Content-Type", "").lower()
        if content_type.startswith("audio/"): return self._write_response_bytes(response.content, content_type)
        try: result = self._extract_audio_from_json(response.json())
        except ValueError: result = None
        if not result: raise RuntimeError(f"{SERVICE_LABEL} response has no audio path/url/base64: {response.text[:300]}")
        return result

    def _post_once(self, url, text, speed, language, reference_audio, reference_text):
        form = {"text": text, "gen_text": text, "speed": speed,
                "language": language or DEFAULT_LANGUAGE, "synthesis_language": language or DEFAULT_LANGUAGE,
                "reference_text": reference_text, "ref_text": reference_text}
        form.update(self.api_config.get("extra_form") or {})
        with open(reference_audio, "rb") as audio:
            response = requests.post(url, data=form,
                                     files={self.api_config.get("reference_audio_field", "ref_audio"): (Path(reference_audio).name, audio)},
                                     headers=self.api_config.get("headers"), timeout=float(self.api_config.get("timeout") or os.getenv(ENV_TIMEOUT, "300")))
        return self._response_to_audio_path(response)

    def synthesize(self, text: str, speed: float = 1.0, reference_audio=None,
                   reference_text=None, language=None, use_cache=False):
        if not str(text).strip(): raise ValueError("text cannot be empty")
        audio = str(reference_audio or self.reference_audio); ref_text = self.reference_text if reference_text is None else reference_text
        self._validate_reference_inputs(audio)
        if use_cache:
            cached = AudioCacheStore.find_cached_audio(str(self.temp_dir), self.voice_id, text, speed,
                                                       self.voice_infer_version, language, audio, ref_text)
            if cached: return cached
        errors = []
        for candidate in self._request_candidates():
            try:
                output = self._post_once(candidate, text, speed, language, audio, ref_text)
                if use_cache: AudioCacheStore.append_record(str(self.temp_dir), output, self.voice_id, text, speed,
                                                             self.voice_infer_version, language, audio, ref_text)
                return output
            except Exception as error: errors.append(f"{candidate}: {error}")
        raise RuntimeError(f"{SERVICE_LABEL} request failed: {'; '.join(errors)}")

    def clear(self):
        return None
