"""MiniMax reference upload and voice cloning."""

from hashlib import sha256
from hmac import digest
import json
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir
from urllib.parse import urlsplit
from uuid import uuid4


def _response_payload(response):
    response.raise_for_status()
    payload = response.json()
    status = payload.get("base_resp") or {}
    if status.get("status_code") != 0:
        raise RuntimeError(status.get("status_msg") or "MiniMax 请求失败")
    return payload


def _runtime(config):
    host = str(config.get("api_host") or "").strip().rstrip("/") or "api.minimax.io"
    endpoint = host if "://" in host else f"https://{host}"
    parsed = urlsplit(endpoint)
    if (parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("MiniMax API 地址必须是无凭据、无查询参数的 HTTPS 地址")
    overseas = parsed.hostname.lower() in {"api.minimax.io", "api-uw.minimax.io"}
    group_id = str(config.get("group_id") or "").strip()
    if not overseas and not group_id:
        raise ValueError("Minimax Group ID 和 API Key 不能为空")
    return endpoint, overseas, group_id


def clone_voice_minimax(
    *, audio_path, duration, api_config, preview_text="你好，欢迎使用 Minimax 在线声音克隆。",
):
    import requests

    api_key = str(api_config.get("api_key") or "").strip()
    if not api_key or duration <= 0:
        raise ValueError("MiniMax 需要 API Key 和有效的参考音频")
    headers = {"Authorization": f"Bearer {api_key}"}
    endpoint, overseas, _ = _runtime(api_config)
    path = Path(audio_path)
    with path.open("rb") as source:
        uploaded = _response_payload(requests.post(
            endpoint + "/v1/files/upload", headers=headers,
            data={"purpose": "voice_clone"}, files={"file": (path.name, source)}, timeout=60,
        ))
    file_id = (uploaded.get("file") or {}).get("file_id")
    if not file_id:
        raise RuntimeError("MiniMax 未返回参考音频文件 ID")
    voice_id = "minimax_" + uuid4().hex[:20]
    payload = {"file_id": file_id, "voice_id": voice_id, "need_noise_reduction": True}
    default_model = "speech-2.8-turbo" if overseas else "speech-2.6-hd"
    model = api_config.get("model") or default_model
    if preview_text:
        payload.update(text=preview_text, model=model)
    result = _response_payload(requests.post(
        endpoint + "/v1/voice_clone", headers=headers, json=payload, timeout=60,
    ))
    return {
        "provider": "minimax", "minimax_voice_id": voice_id, "file_id": file_id,
        "duration": duration, "model": model, "demo_audio": result.get("demo_audio"),
    }


def synthesize_speech_minimax(
    *, text, voice_id, minimax_config, speed=1.0, language="zh-CN", use_cache=True,
):
    import requests

    api_key = str(minimax_config.get("api_key") or "").strip()
    if not api_key or not voice_id or not text.strip():
        raise ValueError("MiniMax 需要 API Key、声音 ID 和文本")
    endpoint, overseas, group_id = _runtime(minimax_config)
    default_model = "speech-2.8-turbo" if overseas else "speech-2.6-hd"
    payload = {
        "model": minimax_config.get("model") or default_model,
        "text": text, "stream": False, "output_format": "hex",
        "voice_setting": {"voice_id": voice_id, "speed": speed},
        "audio_setting": {"format": "mp3", "channel": 1},
        "language_boost": {"zh": "Chinese", "en": "English"}.get(language.split("-")[0], "auto"),
    }
    params = {} if overseas else {"GroupId": group_id}
    folder = Path(minimax_config.get("cache_dir") or Path(gettempdir()) / "yunchuang-minimax")
    folder.mkdir(parents=True, exist_ok=True)
    key = digest(api_key.encode(), json.dumps([endpoint, params, payload]).encode(), sha256).hex()
    target = folder / (key + ".mp3")
    if use_cache and target.is_file() and target.stat().st_size:
        return str(target)
    result = _response_payload(requests.post(
        endpoint + "/v1/t2a_v2", params=params,
        headers={"Authorization": f"Bearer {api_key}"}, json=payload, timeout=60,
    ))
    audio = bytes.fromhex((result.get("data") or {}).get("audio") or "")
    if not audio:
        raise RuntimeError("MiniMax 返回空音频")
    with NamedTemporaryFile(dir=folder, suffix=".mp3", delete=False) as output:
        path = Path(output.name)
        try:
            output.write(audio)
            output.close()
            if use_cache:
                path.replace(target)
                return str(target)
            return str(path)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
