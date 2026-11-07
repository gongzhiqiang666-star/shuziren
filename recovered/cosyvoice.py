"""CosyVoice synthesis through the DashScope Python SDK."""

from hashlib import sha256
from hmac import digest
import json
import wave
from pathlib import Path
from tempfile import NamedTemporaryFile, gettempdir

from .cosyvoice_config import resolve_audio_format, resolve_dashscope_endpoints


def synthesize_speech_cosyvoice(
    *, text, voice_id, cosyvoice_config, speed=1.0, language="zh-CN",
    use_cache=True, audio_format=None, timeout_seconds=30.0,
):
    from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

    config = resolve_dashscope_endpoints(cosyvoice_config)
    api_key = str(config.get("api_key") or "").strip()
    if not api_key or not voice_id or not text.strip():
        raise ValueError("CosyVoice 需要 API Key、声音 ID 和文本")
    audio_format, suffix = resolve_audio_format(AudioFormat, audio_format or config.get("audio_format"))
    raw_pcm = suffix == ".pcm"
    if raw_pcm:
        suffix = ".wav"
    model = config.get("model") or "cosyvoice-v3.5-flash"
    url = config["base_websocket_api_url"]
    hint = language.split("-", 1)[0].lower()
    cache_dir = Path(config.get("cache_dir") or Path(gettempdir()) / "yunchuang-cosyvoice")
    cache_dir.mkdir(parents=True, exist_ok=True)
    request = json.dumps([url, model, voice_id, text, speed, hint, str(audio_format)]).encode()
    key = digest(api_key.encode(), request, sha256).hex()
    target = cache_dir / (key + suffix)
    if use_cache and target.is_file() and target.stat().st_size:
        return str(target)
    synthesizer = SpeechSynthesizer(
        model=model, voice=voice_id, format=audio_format, speech_rate=speed,
        language_hints=[hint], url=url, headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        audio = synthesizer.call(text, timeout_millis=int(timeout_seconds * 1000))
    finally:
        synthesizer.close()
    if not audio:
        raise RuntimeError("CosyVoice 返回空音频")
    output = NamedTemporaryFile(dir=cache_dir, suffix=suffix, delete=False)
    temporary_path = Path(output.name)
    try:
        with output:
            if raw_pcm:
                with wave.open(output, "wb") as wav:
                    wav.setparams((1, 2, audio_format.sample_rate, 0, "NONE", ""))
                    wav.writeframes(audio)
            else:
                output.write(audio)
        if use_cache:
            temporary_path.replace(target)
            return str(target)
        return str(temporary_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _wait_aliyun_voice_ready(service, voice_id, timeout_seconds=90.0):
    from time import monotonic, sleep

    deadline = monotonic() + timeout_seconds
    while True:
        result = service.query_voice(voice_id)
        status = str(result.get("status") or "").upper()
        if status == "OK":
            return
        if status in {"UNDEPLOYED", "FAILED"}:
            raise RuntimeError(f"CosyVoice 声音克隆失败：{status}")
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("等待 CosyVoice 声音就绪超时")
        sleep(min(1.0, remaining))


class _VoiceEnrollment:
    def __init__(self, config):
        self.url = config["base_http_api_url"].rstrip("/") + "/services/audio/tts/customization"
        self.api_key = str(config.get("api_key") or "").strip()
        if not self.api_key:
            raise ValueError("CosyVoice 需要 API Key")

    def request(self, action, **fields):
        from urllib.request import Request, urlopen

        body = json.dumps({"model": "voice-enrollment", "input": dict(fields, action=action)})
        request = Request(
            self.url, data=body.encode(), method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        if not isinstance(result.get("output"), dict):
            raise RuntimeError("CosyVoice 返回了无效的声音克隆响应")
        return result["output"]

    def query_voice(self, voice_id):
        return self.request("query_voice", voice_id=voice_id)


def clone_voice_cosyvoice(*, audio_url, duration, api_config):
    if not audio_url or duration <= 0:
        raise ValueError("CosyVoice 需要有效的参考音频和时长")
    config = resolve_dashscope_endpoints(api_config)
    service = _VoiceEnrollment(config)
    model = config.get("model") or "cosyvoice-v3.5-flash"
    result = service.request(
        "create_voice", target_model=model, prefix=config.get("prefix") or "yunchuang",
        url=audio_url,
    )
    voice_id = result.get("voice_id")
    if not voice_id:
        raise RuntimeError("CosyVoice 未返回声音 ID")
    _wait_aliyun_voice_ready(service, voice_id)
    return {
        "voice_id": voice_id,
        "cosyvoice_voice_id": voice_id,
        "provider": "cosyvoice",
        "model": model,
        "reference_audio_url": audio_url,
        "duration": duration,
    }
