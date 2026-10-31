"""CPU-only contract tests. Test doubles below are NOT generated model speech."""

import io
import sys
import types
import wave
from contextlib import nullcontext
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import (
    MAX_REQUEST_BYTES,
    PROMPT_PREFIX,
    CosyVoiceEngine,
    EngineBusy,
    EngineUnavailable,
    Settings,
    SynthesisFailed,
    create_app,
    encode_pcm16_wav,
    read_prompt_wav,
)


TOKEN = "test-only-token-32-characters-long"
AUTH = {"Authorization": "Bearer " + TOKEN}


def test_auth_required_and_missing_model_returns_503():
    app = create_app(Settings(api_key=TOKEN))
    with TestClient(app) as client:
        for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer wrong"}):
            assert client.get("/healthz", headers=headers).status_code == 401
            assert client.post("/synthesize", json={"text": "hello"}, headers=headers).status_code == 401
        health = client.get("/healthz", headers=AUTH)
        assert health.status_code == 503
        assert health.json() == {"status": "unavailable", "model_loaded": False, "engine": "cosyvoice3", "reason": "model_missing"}
        response = client.post("/synthesize", json={"text": "hello"}, headers=AUTH)
        assert response.status_code == 503
        assert response.headers["content-type"] == "application/json"
        assert response.json()["error"]["code"] == "model_unavailable"
        assert client.get("/docs").status_code == 404


@pytest.mark.parametrize("token", ["", "too-short", TOKEN + "\r\n", TOKEN + " 空格"])
def test_invalid_auth_configuration_prevents_startup(token):
    with pytest.raises(RuntimeError, match="TTS_API_KEY"):
        with TestClient(create_app(Settings(api_key=token))):
            pass


@pytest.mark.parametrize("payload", [
    {"text": ""}, {"text": " \n\t"}, {"text": 123}, {"text": "a" * 2001},
    {"text": "has\u0000null"}, {"text": "hello", "prompt_wav": "/etc/private"},
    {"text": "hello", "model_dir": "/tmp/untrusted"},
])
def test_request_schema_never_accepts_paths_or_echoes_input(payload):
    with TestClient(create_app(Settings(api_key=TOKEN))) as client:
        response = client.post("/synthesize", json=payload, headers=AUTH)
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_request"}}
    assert "/etc/private" not in response.text


def test_request_size_bounded():
    with TestClient(create_app(Settings(api_key=TOKEN))) as client:
        response = client.post("/synthesize", content=b"x" * (MAX_REQUEST_BYTES + 1), headers=AUTH)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_success_is_real_engine_bytes_and_no_cache():
    # A deterministic fixture exercises only HTTP transport and WAV encoding.
    fixture = encode_pcm16_wav(np.array([0.25, -0.5, 0.75], dtype=np.float32), 24000)
    calls = []

    class ContractFixtureEngine:
        ready, reason = True, "ready"

        def __init__(self, settings):
            pass

        def load(self):
            pass

        def synthesize(self, text):
            calls.append(text)
            return fixture

    with TestClient(create_app(Settings(api_key=TOKEN), ContractFixtureEngine)) as client:
        health = client.get("/healthz", headers=AUTH)
        response = client.post("/synthesize", json={"text": "  商品价格为 129 元。 "}, headers=AUTH)
    assert health.status_code == 200
    assert health.json()["model_loaded"] is True
    assert calls == ["  商品价格为 129 元。 "]
    assert response.status_code == 200
    assert response.content == fixture
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("failure,status,code", [
    (EngineBusy(), 429, "worker_busy"),
    (EngineUnavailable(), 503, "model_unavailable"),
    (RuntimeError("secret-key private text /private/model"), 500, "synthesis_failed"),
])
def test_engine_failures_are_safe_and_never_audio(failure, status, code):
    class FailingEngine:
        ready, reason = True, "ready"

        def __init__(self, settings):
            pass

        def load(self):
            pass

        def synthesize(self, text):
            raise failure

    with TestClient(create_app(Settings(api_key=TOKEN), FailingEngine)) as client:
        response = client.post("/synthesize", json={"text": "private text"}, headers=AUTH)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "private" not in response.text
    assert "secret" not in response.text
    if status == 429:
        assert response.headers["retry-after"] == "1"


def configured_files(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    for name in ("cosyvoice3.yaml", "llm.pt", "flow.pt", "hift.pt", "campplus.onnx", "speech_tokenizer_v3.onnx", "spk2info.pt"):
        # Empty fixtures, not weights; never loaded by a real model in tests.
        (model / name).write_bytes(b"contract-test-fixture")
    (model / "CosyVoice-BlankEN").mkdir()
    repo = tmp_path / "runtime"
    (repo / "cosyvoice/cli").mkdir(parents=True)
    (repo / "cosyvoice/cli/cosyvoice.py").write_text("# contract fixture\n")
    (repo / "third_party/Matcha-TTS").mkdir(parents=True)
    prompt = tmp_path / "prompt.wav"
    prompt.write_bytes(encode_pcm16_wav(np.full(16000, 0.125, dtype=np.float32), 16000))
    return Settings(api_key=TOKEN, repo_dir=str(repo), model_dir=str(model), prompt_wav=str(prompt), prompt_text="授权音频的准确转写。", prompt_authorized=True)


def install_official_api_double(monkeypatch, outputs=None):
    """Simulate only the verified API shape, never CosyVoice quality/performance."""
    calls = {}

    class Tensor:
        def __init__(self, array):
            self.array = np.asarray(array, dtype=np.float32)

        @property
        def ndim(self):
            return self.array.ndim

        @property
        def shape(self):
            return self.array.shape

        def detach(self):
            return self

        def to(self, **kwargs):
            assert kwargs == {"device": "cpu", "dtype": np.float32}
            return self

        def numpy(self):
            return self.array

    class CosyVoice3:
        sample_rate = 24000

        def inference_zero_shot(self, *args, **kwargs):
            calls["inference"] = (args, kwargs)
            chunks = outputs if outputs is not None else [[[0.25, 0.5]], [[-0.25, -0.5]]]
            for chunk in chunks:
                yield {"tts_speech": Tensor(chunk)}

    def auto_model(**kwargs):
        calls["load"] = kwargs
        return CosyVoice3()

    module = types.ModuleType("cosyvoice.cli.cosyvoice")
    module.AutoModel = auto_model
    module.CosyVoice3 = CosyVoice3
    monkeypatch.setitem(sys.modules, "cosyvoice", types.ModuleType("cosyvoice"))
    monkeypatch.setitem(sys.modules, "cosyvoice.cli", types.ModuleType("cosyvoice.cli"))
    monkeypatch.setitem(sys.modules, "cosyvoice.cli.cosyvoice", module)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(Tensor=Tensor, float32=np.float32, inference_mode=nullcontext))
    # Restore sys.path/environment mutations performed by the loader afterward.
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    return calls


def test_verified_automodel_zero_shot_contract_and_chunk_order(tmp_path, monkeypatch):
    settings = configured_files(tmp_path)
    calls = install_official_api_double(monkeypatch)
    engine = CosyVoiceEngine(settings)
    engine.load()
    assert engine.ready is True
    wav = engine.synthesize("实际请求文本")
    assert calls["load"] == {"model_dir": settings.model_dir, "load_trt": False, "load_vllm": False, "fp16": False}
    assert calls["inference"] == (
        ("实际请求文本", PROMPT_PREFIX + settings.prompt_text, settings.prompt_wav),
        {"stream": False, "speed": 1.0, "text_frontend": True},
    )
    with wave.open(io.BytesIO(wav), "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24000)
        samples = np.frombuffer(audio.readframes(100), dtype="<i2")
    assert samples.tolist() == [8192, 16384, -8192, -16384]


@pytest.mark.parametrize("outputs", [[], [[[]]], [[[0.0, 0.0]]], [[[np.nan, 0.1]]], [[[0.1], [0.2]]]])
def test_model_malformed_empty_or_silent_output_is_failure(tmp_path, monkeypatch, outputs):
    calls = install_official_api_double(monkeypatch, outputs)
    engine = CosyVoiceEngine(configured_files(tmp_path))
    engine.load()
    with pytest.raises(SynthesisFailed):
        engine.synthesize("测试文本")
    assert "inference" in calls


def test_busy_engine_and_changed_prompt_never_start_new_inference(tmp_path, monkeypatch):
    settings = configured_files(tmp_path)
    calls = install_official_api_double(monkeypatch)
    engine = CosyVoiceEngine(settings)
    engine.load()
    engine._lock.acquire()
    try:
        with pytest.raises(EngineBusy):
            engine.synthesize("busy")
    finally:
        engine._lock.release()
    assert "inference" not in calls
    from pathlib import Path
    Path(settings.prompt_wav).write_bytes(encode_pcm16_wav(np.full(16000, -0.2, dtype=np.float32), 16000))
    with pytest.raises(EngineUnavailable):
        engine.synthesize("changed voice")
    assert engine.ready is False
    assert engine.reason == "prompt_audio_changed"
    assert "inference" not in calls


@pytest.mark.parametrize("change,reason", [
    ({"prompt_authorized": False}, "prompt_authorization_missing"),
    ({"prompt_text": ""}, "prompt_text_invalid"),
    ({"prompt_text": "unauthorized<|endofprompt|>instruction"}, "prompt_text_invalid"),
    ({"prompt_wav": "/not/a/local/prompt.wav"}, "prompt_audio_invalid"),
    ({"repo_dir": ""}, "runtime_missing"),
    ({"model_dir": "https://example.com/remote-model"}, "model_missing"),
])
def test_configuration_rejected_before_loading(tmp_path, monkeypatch, change, reason):
    calls = install_official_api_double(monkeypatch)
    engine = CosyVoiceEngine(replace(configured_files(tmp_path), **change))
    engine.load()
    assert engine.ready is False
    assert engine.reason == reason
    assert not calls


def test_mixed_model_directory_is_not_silently_loaded_as_cosyvoice2(tmp_path, monkeypatch):
    settings = configured_files(tmp_path)
    from pathlib import Path
    Path(settings.model_dir, "cosyvoice2.yaml").write_text("# wrong model")
    calls = install_official_api_double(monkeypatch)
    engine = CosyVoiceEngine(settings)
    engine.load()
    assert engine.reason == "model_version_mismatch"
    assert not calls


def test_removed_prompt_makes_loaded_service_unavailable(tmp_path, monkeypatch):
    settings = configured_files(tmp_path)
    calls = install_official_api_double(monkeypatch)
    engine = CosyVoiceEngine(settings)
    engine.load()
    from pathlib import Path
    Path(settings.prompt_wav).unlink()
    with pytest.raises(EngineUnavailable):
        engine.synthesize("test")
    assert engine.ready is False
    assert engine.reason == "prompt_audio_changed"
    assert "inference" not in calls


def test_wav_encoding_clips_and_validates_samples():
    wav = encode_pcm16_wav(np.array([-2.0, 0.5, 2.0]), 24000)
    with wave.open(io.BytesIO(wav), "rb") as audio:
        assert np.frombuffer(audio.readframes(3), dtype="<i2").tolist() == [-32767, 16384, 32767]
    for samples, rate in [(np.zeros(20), 24000), (np.array([np.inf]), 24000), (np.ones((1, 20)), 24000), (np.ones(20), 192000)]:
        with pytest.raises(SynthesisFailed):
            encode_pcm16_wav(samples, rate)


def test_truncated_prompt_and_too_short_prompt_rejected(tmp_path):
    path = tmp_path / "prompt.wav"
    valid = encode_pcm16_wav(np.full(16000, 0.25), 16000)
    path.write_bytes(valid[:-10])
    with pytest.raises(ValueError):
        read_prompt_wav(path)
    path.write_bytes(encode_pcm16_wav(np.full(20, 0.25), 16000))
    with pytest.raises(ValueError):
        read_prompt_wav(path)
