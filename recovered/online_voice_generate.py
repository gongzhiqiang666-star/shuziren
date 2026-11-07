"""Compatibility facade for the original online voice-generation extension."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from .cosyvoice import (
    _wait_aliyun_voice_ready as _wait_aliyun_voice_ready_impl,
    clone_voice_cosyvoice,
    synthesize_speech_cosyvoice,
)
from .cosyvoice_config import resolve_dashscope_endpoints
from .minimax import clone_voice_minimax, synthesize_speech_minimax


_ALIYUN_INTERNATIONAL_LANGUAGES = {
    "ar-sa", "bahasa-malaysia", "bahasa-melayu", "de-de", "en-us", "es-es",
    "fil-ph", "fr-fr", "id-id", "it-it", "ja-jp", "ko-kr", "ms-my", "pt-br",
    "ru-ru", "th-th", "tl-ph", "vi-vn", "zh-cn",
}
_ALIYUN_CHINA_LANGUAGES = _ALIYUN_INTERNATIONAL_LANGUAGES - {
    "de-de", "fr-fr", "pt-br", "ru-ru",
}
_COSYVOICE_LANGUAGE_HINTS = {
    "ar": "ar-sa", "de": "de-de", "en": "en-us", "es": "es-es",
    "fil": "fil-ph", "fr": "fr-fr", "id": "id-id", "it": "it-it",
    "ja": "ja-jp", "ko": "ko-kr", "ms": "ms-my", "pt": "pt-br",
    "ru": "ru-ru", "th": "th-th", "tl": "tl-ph", "vi": "vi-vn",
    "zh": "zh-cn",
}


def _ensure_dir(path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _api_host(api_config):
    host = str((api_config or {}).get("api_host") or "api.minimax.io").strip().rstrip("/")
    return host if "://" in host else "https://" + host


def _is_overseas_minimax(api_host):
    host = str(api_host or "api.minimax.io").strip().rstrip("/")
    if "://" not in host:
        host = "https://" + host
    return (urlsplit(host).hostname or "").lower() in {"api.minimax.io", "api-uw.minimax.io"}


def _default_minimax_model(api_host):
    return "speech-2.8-turbo" if _is_overseas_minimax(api_host) else "speech-2.6-hd"


def _minimax_headers(api_key, content_type=None):
    headers = {"Authorization": f"Bearer {api_key}"}
    if content_type:
        headers["Content-Type"] = str(content_type)
    return headers


def _upload_clone_audio(audio_path, api_key, api_host):
    import requests
    from .minimax import _response_payload
    path = Path(audio_path)
    with path.open("rb") as source:
        host = str(api_host or "api.minimax.io").strip().rstrip("/")
        if "://" not in host:
            host = "https://" + host
        result = _response_payload(requests.post(host + "/v1/files/upload",
            headers=_minimax_headers(api_key), data={"purpose": "voice_clone"},
            files={"file": (path.name, source)}, timeout=60))
    file_id = (result.get("file") or {}).get("file_id")
    if file_id is None:
        raise RuntimeError("Minimax 未返回参考音频文件 ID")
    return int(file_id)


def _wait_aliyun_voice_ready(service, voice_id, timeout_seconds=90.0) -> None:
    return _wait_aliyun_voice_ready_impl(service, voice_id, timeout_seconds)


def is_overseas_aliyun_voice_config(config):
    endpoints = resolve_dashscope_endpoints(config or {})
    host = (urlsplit(endpoints["base_http_api_url"]).hostname or "").lower()
    return host not in {"dashscope.aliyuncs.com", "dashscope.cn-beijing.aliyuncs.com"}


def resolve_aliyun_voice_runtime(config):
    resolved = resolve_dashscope_endpoints(config or {})
    resolved["http_url"] = resolved["base_http_api_url"]
    resolved["websocket_url"] = resolved["base_websocket_api_url"]
    return resolved


def apply_dashscope_endpoint(api_config):
    resolved = resolve_aliyun_voice_runtime(api_config or {})
    try:
        import dashscope
        dashscope.base_http_api_url = resolved["http_url"]
        dashscope.base_websocket_api_url = resolved["websocket_url"]
    except ImportError:
        pass
    return resolved


def aliyun_voice_supports_language(language, config=None):
    hint = cosyvoice_language_hint(language)
    supported = (_ALIYUN_INTERNATIONAL_LANGUAGES if
                 is_overseas_aliyun_voice_config(config or {}) else
                 _ALIYUN_CHINA_LANGUAGES)
    return hint in supported


def cosyvoice_language_hint(language):
    normalized = str(language or "zh-CN").strip().lower().replace("_", "-")
    if normalized in _ALIYUN_INTERNATIONAL_LANGUAGES:
        return normalized
    return _COSYVOICE_LANGUAGE_HINTS.get(normalized.split("-", 1)[0], "zh-cn")
