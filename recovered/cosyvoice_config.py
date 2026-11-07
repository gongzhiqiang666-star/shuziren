"""DashScope region settings recovered from generate_voice.pyd."""

_HTTP = "https://{host}/api/v1"
_WEBSOCKET = "wss://{host}/api-ws/v1/inference"
_INTERNATIONAL = {"international", "intl", "singapore", "ap-southeast-1"}


def resolve_dashscope_endpoints(api_config=None):
    config = dict(api_config or {})
    region = str(config.get("region") or "").strip().lower()
    host = "dashscope-intl.aliyuncs.com" if region in _INTERNATIONAL else "dashscope.aliyuncs.com"
    config["base_http_api_url"] = config.get("base_http_api_url") or _HTTP.format(host=host)
    config["base_websocket_api_url"] = config.get("base_websocket_api_url") or _WEBSOCKET.format(host=host)
    return config


def resolve_audio_format(formats, audio_format=None):
    """Resolve the SDK enum and the matching output file suffix."""
    name = str(audio_format or "").strip().upper() or "MP3_22050HZ_MONO_256KBPS"
    if name.startswith("WAV_"):
        suffix = ".wav"
    elif name.startswith("PCM_"):
        suffix = ".pcm"
    elif name.startswith("MP3_"):
        suffix = ".mp3"
    else:
        raise ValueError(f"不支持的 CosyVoice 音频格式：{name}")
    try:
        return getattr(formats, name), suffix
    except AttributeError as error:
        raise ValueError(f"不支持的 CosyVoice 音频格式：{name}") from error
