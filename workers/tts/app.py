"""Authenticated, local-only HTTP wrapper around genuine CosyVoice3 inference.

Heavy model dependencies are imported only after local configuration and model
files have been checked. Missing models never produce placeholder audio.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.metadata
import io
import json
import logging
import os
import re
import sys
import threading
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator


LOGGER = logging.getLogger("shuziren.tts")
MAX_TEXT_CHARS = 2000
MAX_REQUEST_BYTES = 16 * 1024
MAX_AUDIO_BYTES = 32 * 1024 * 1024
MAX_AUDIO_SECONDS = 300
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._~+/=-]{24,512}\Z", re.ASCII)
PROMPT_PREFIX = "You are a helpful assistant.<|endofprompt|>"


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    repo_dir: str = ""
    model_dir: str = ""
    prompt_wav: str = ""
    prompt_text: str = field(default="", repr=False)
    prompt_authorized: bool = False
    fp16: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_key=os.getenv("TTS_API_KEY", ""),
            repo_dir=os.getenv("COSYVOICE_REPO_DIR", ""),
            model_dir=os.getenv("COSYVOICE_MODEL_DIR", ""),
            prompt_wav=os.getenv("COSYVOICE_PROMPT_WAV", ""),
            prompt_text=os.getenv("COSYVOICE_PROMPT_TEXT", ""),
            prompt_authorized=os.getenv("COSYVOICE_PROMPT_AUTHORIZED", "") == "1",
            fp16=os.getenv("COSYVOICE_FP16", "0") == "1",
        )

    def validate_auth(self) -> None:
        if not TOKEN_PATTERN.fullmatch(self.api_key):
            raise RuntimeError("TTS_API_KEY must be a 24-512 character ASCII bearer token")


class EngineUnavailable(Exception):
    pass


class EngineBusy(Exception):
    pass


class SynthesisFailed(Exception):
    pass


class Engine(Protocol):
    ready: bool
    reason: str

    def load(self) -> None: ...

    def synthesize(self, text: str) -> bytes: ...


class CosyVoiceEngine:
    """One configured voice and one inference at a time; no remote fallbacks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ready = False
        self.reason = "not_loaded"
        self._model: Any = None
        self._prompt_path: Path | None = None
        self._prompt_hash = ""
        self.engine_id = ""
        self._artifact_stats: list[tuple[Path, tuple[int, int, int]]] = []
        self._lock = threading.Lock()

    def load(self) -> None:
        self.ready = False
        self._model = None
        self.engine_id = ""
        self._artifact_stats = []
        config = self.settings
        if not config.model_dir or not Path(config.model_dir).is_dir():
            self.reason = "model_missing"
            return
        model_dir = Path(config.model_dir).resolve()
        # AutoModel otherwise falls back to snapshot_download. Check all local
        # CosyVoice3 entry files first, and reject mixed version directories.
        required = (
            "cosyvoice3.yaml", "llm.pt", "flow.pt", "hift.pt", "campplus.onnx",
            "speech_tokenizer_v3.onnx", "spk2info.pt",
        )
        if any(not (model_dir / name).is_file() for name in required) or not (model_dir / "CosyVoice-BlankEN").is_dir():
            self.reason = "model_incomplete"
            return
        if (model_dir / "cosyvoice.yaml").exists() or (model_dir / "cosyvoice2.yaml").exists():
            self.reason = "model_version_mismatch"
            return
        if not config.prompt_authorized:
            self.reason = "prompt_authorization_missing"
            return
        if not config.prompt_text.strip() or len(config.prompt_text) > MAX_TEXT_CHARS or "<|" in config.prompt_text:
            self.reason = "prompt_text_invalid"
            return
        try:
            prompt_path = Path(config.prompt_wav).resolve(strict=True)
            prompt_bytes = read_prompt_wav(prompt_path)
        except (OSError, ValueError, EOFError, wave.Error):
            self.reason = "prompt_audio_invalid"
            return
        if not config.repo_dir:
            self.reason = "runtime_missing"
            return
        repo_dir = Path(config.repo_dir).resolve()
        if not (repo_dir / "cosyvoice/cli/cosyvoice.py").is_file() or not (repo_dir / "third_party/Matcha-TTS").is_dir():
            self.reason = "runtime_missing"
            return
        artifact_roots = (
            ("model", model_dir, None),
            ("runtime", repo_dir / "cosyvoice", {".py", ".yaml", ".json"}),
            ("matcha", repo_dir / "third_party/Matcha-TTS", {".py", ".yaml", ".json"}),
        )
        try:
            before_load = {path: file_signature(path) for _, path in identity_files(artifact_roots)}
        except (OSError, ValueError):
            self.reason = "artifact_identity_failed"
            return
        # Both repository paths are fixed administrator configuration, never
        # taken from an HTTP request. Pin the source revision in deployment.
        sys.path.insert(0, str(repo_dir / "third_party/Matcha-TTS"))
        sys.path.insert(0, str(repo_dir))
        # The wrapper never downloads weights at startup/inference. These flags
        # additionally disable Hugging Face/Transformers network fallbacks.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            from cosyvoice.cli.cosyvoice import AutoModel, CosyVoice3

            model = AutoModel(model_dir=str(model_dir), load_trt=False, load_vllm=False, fp16=config.fp16)
            if not isinstance(model, CosyVoice3):
                self.reason = "model_version_mismatch"
                return
            sample_rate = int(model.sample_rate)
            if not 8000 <= sample_rate <= 48000:
                self.reason = "sample_rate_unsupported"
                return
        except Exception as exc:
            # Upstream exception messages may contain local paths or text. Only
            # log the class; return a stable status without those values.
            LOGGER.error("CosyVoice3 loading failed (%s)", type(exc).__name__)
            self.reason = "model_load_failed"
            return
        self._model = model
        self._prompt_path = prompt_path
        self._prompt_hash = hashlib.sha256(prompt_bytes).hexdigest()
        try:
            # Hash actual local model/runtime contents once. A tag or directory
            # name cannot identify a replaced model. Only the digest is exposed.
            digest = hashlib.sha256()
            files = identity_files(artifact_roots)
            if set(before_load) != {path for _, path in files}:
                raise ValueError("artifact set changed while loading")
            for label, path in files:
                before = file_signature(path)
                if before_load.get(path) != before:
                    raise ValueError("artifact changed while loading")
                digest.update(label.encode("utf-8"))
                digest.update(b"\x00")
                digest.update(before[0].to_bytes(8, "big"))
                with path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                if file_signature(path) != before:
                    raise ValueError("artifact changed while hashing")
                self._artifact_stats.append((path, before))
            packages = {}
            for name in ("torch", "torchaudio", "transformers", "numpy", "onnxruntime"):
                try:
                    packages[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    packages[name] = "not_installed"
            configuration = {
                "protocol": "cosyvoice3-identity-v1", "reference_sha256": self._prompt_hash,
                "prompt_text_sha256": hashlib.sha256(config.prompt_text.encode("utf-8")).hexdigest(),
                "fp16": config.fp16, "sample_rate": sample_rate,
                "stream": False, "speed": 1.0, "text_frontend": True, "prompt_prefix": PROMPT_PREFIX,
                "packages": packages,
            }
            digest.update(json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            self.engine_id = digest.hexdigest()
        except (OSError, ValueError):
            self.reason = "artifact_identity_failed"
            self._model = None
            self.engine_id = ""
            return
        self.reason = "ready"
        self.ready = True

    def identity(self) -> str:
        if not self.ready or not self.engine_id or self._prompt_path is None:
            raise EngineUnavailable()
        try:
            unchanged = hashlib.sha256(read_prompt_wav(self._prompt_path)).hexdigest() == self._prompt_hash
            unchanged = unchanged and all(file_signature(path) == signature for path, signature in self._artifact_stats)
        except (OSError, ValueError, EOFError, wave.Error):
            unchanged = False
        if not unchanged:
            self.ready = False
            self.reason = "artifacts_changed"
            self.engine_id = ""
            raise EngineUnavailable()
        return self.engine_id

    def synthesize(self, text: str) -> bytes:
        if not self.ready or self._model is None or self._prompt_path is None:
            raise EngineUnavailable()
        if not self._lock.acquire(blocking=False):
            raise EngineBusy()
        try:
            # Reject replacement of a configured voice file until an operator
            # explicitly restarts/reloads this worker with its new voice setup.
            try:
                unchanged = hashlib.sha256(read_prompt_wav(self._prompt_path)).hexdigest() == self._prompt_hash
            except (OSError, ValueError, EOFError, wave.Error):
                unchanged = False
            if not unchanged:
                self.ready = False
                self.reason = "prompt_audio_changed"
                raise EngineUnavailable()
            self.identity()
            import numpy as np
            import torch

            chunks: list[Any] = []
            total_frames = 0
            sample_rate = int(self._model.sample_rate)
            with torch.inference_mode():
                outputs = self._model.inference_zero_shot(
                    text,
                    PROMPT_PREFIX + self.settings.prompt_text,
                    str(self._prompt_path),
                    stream=False,
                    speed=1.0,
                    text_frontend=True,
                )
                for output in outputs:
                    speech = output.get("tts_speech") if isinstance(output, dict) else None
                    if speech is None or not isinstance(speech, torch.Tensor) or speech.ndim != 2 or speech.shape[0] != 1:
                        raise SynthesisFailed()
                    chunk = speech.detach().to(device="cpu", dtype=torch.float32).numpy()[0]
                    if chunk.size == 0 or not np.isfinite(chunk).all():
                        raise SynthesisFailed()
                    total_frames += int(chunk.size)
                    if total_frames > sample_rate * MAX_AUDIO_SECONDS or total_frames * 2 + 44 > MAX_AUDIO_BYTES:
                        raise SynthesisFailed()
                    chunks.append(chunk.copy())
            if not chunks:
                raise SynthesisFailed()
            waveform = np.concatenate(chunks)
            if not np.any(waveform):
                # A silent placeholder cannot be treated as successful speech.
                raise SynthesisFailed()
            return encode_pcm16_wav(waveform, sample_rate)
        except EngineUnavailable:
            raise
        except Exception as exc:
            LOGGER.error("CosyVoice3 synthesis failed (%s)", type(exc).__name__)
            raise SynthesisFailed() from None
        finally:
            self._lock.release()


def file_signature(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def identity_files(roots: Any) -> list[tuple[str, Path]]:
    files = []
    for label, root, suffixes in roots:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if any(part in {".git", "__pycache__", ".cache"} for part in relative.parts):
                continue
            # Individual checkpoint symlinks are hashed through their target.
            # A symlink directory could hide unhashed files from rglob.
            if path.is_symlink() and path.is_dir():
                raise ValueError("symlink model directories are unsupported")
            if path.is_file() and (suffixes is None or path.suffix in suffixes):
                files.append((label + "/" + relative.as_posix(), path))
    return files


def read_prompt_wav(path: Path) -> bytes:
    """Small mono PCM16 prompt only; no URLs or arbitrary request-time paths."""
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("invalid prompt")
    raw = path.read_bytes()
    with wave.open(io.BytesIO(raw), "rb") as audio:
        rate, frames = audio.getframerate(), audio.getnframes()
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getcomptype() != "NONE" or not 8000 <= rate <= 48000:
            raise ValueError("invalid prompt")
        if frames < rate // 2 or frames > rate * 30:
            raise ValueError("invalid prompt duration")
        pcm = audio.readframes(frames + 1)
        if len(pcm) != frames * 2 or not any(pcm):
            raise ValueError("invalid prompt samples")
    return raw


def encode_pcm16_wav(waveform: Any, sample_rate: int) -> bytes:
    import numpy as np

    samples = np.asarray(waveform, dtype=np.float32)
    if samples.ndim != 1 or samples.size == 0 or not np.isfinite(samples).all() or not 8000 <= sample_rate <= 48000:
        raise SynthesisFailed()
    if samples.size > sample_rate * MAX_AUDIO_SECONDS or samples.size * 2 + 44 > MAX_AUDIO_BYTES:
        raise SynthesisFailed()
    pcm = np.rint(np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    if not any(pcm):
        raise SynthesisFailed()
    result = io.BytesIO()
    with wave.open(result, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return result.getvalue()


class SynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(strict=True, min_length=1, max_length=MAX_TEXT_CHARS)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("invalid text")
        return value


class BodyLimitMiddleware:
    """Bound request memory including chunked bodies before JSON parsing."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        data = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            data.extend(message.get("body", b""))
            if len(data) > MAX_REQUEST_BYTES:
                await JSONResponse({"error": {"code": "request_too_large"}}, status_code=413)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        replayed = False

        async def bounded_receive() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(settings: Settings | None = None, engine_factory: Callable[[Settings], Engine] = CosyVoiceEngine) -> FastAPI:
    configured = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configured.validate_auth()
        engine = engine_factory(configured)
        app.state.engine = engine
        # Initialization happens once before serving requests. A missing local
        # model remains an authenticated, inspectable 503 state.
        engine.load()
        yield

    app = FastAPI(title="Local CosyVoice3 worker", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware)
    bearer = HTTPBearer(auto_error=False)

    def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        received = credentials.credentials.encode("utf-8") if credentials and credentials.scheme.lower() == "bearer" else b""
        if not hmac.compare_digest(received, configured.api_key.encode("utf-8")):
            raise HTTPException(status_code=401, detail={"code": "unauthorized"}, headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError) -> JSONResponse:
        # Pydantic's default detail echoes invalid input, including supplied text.
        return JSONResponse({"error": {"code": "invalid_request"}}, status_code=422)

    @app.get("/healthz", dependencies=[Depends(authorize)])
    def health(request: Request) -> JSONResponse:
        engine: Engine = request.app.state.engine
        engine_id = None
        identity = getattr(engine, "identity", None)
        if engine.ready and identity is not None:
            try:
                engine_id = identity()
            except EngineUnavailable:
                pass
        payload = {"status": "ready" if engine.ready else "unavailable", "model_loaded": engine.ready, "engine": "cosyvoice3", "reason": engine.reason}
        if engine_id:
            payload["engine_id"] = engine_id
        return JSONResponse(
            payload,
            status_code=200 if engine.ready else 503,
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/synthesize", dependencies=[Depends(authorize)])
    def synthesize(payload: SynthesisRequest, request: Request) -> Response:
        engine: Engine = request.app.state.engine
        try:
            wav = engine.synthesize(payload.text)
        except EngineUnavailable:
            return JSONResponse({"error": {"code": "model_unavailable"}}, status_code=503)
        except EngineBusy:
            return JSONResponse({"error": {"code": "worker_busy"}}, status_code=429, headers={"Retry-After": "1"})
        except Exception:
            return JSONResponse({"error": {"code": "synthesis_failed"}}, status_code=500)
        return Response(wav, media_type="audio/wav", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return app


app = create_app()
