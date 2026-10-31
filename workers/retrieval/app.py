"""Local CPU BGE embeddings. Model files are administrator supplied and offline.

The application never substitutes random vectors when loading or inference fails.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.metadata
import json
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

MODEL = "BAAI/bge-small-zh-v1.5"
INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
TOKEN = re.compile(r"[\x21-\x7e]{24,512}\Z")


def artifact_files(folder: Path):
    return sorted(file for file in folder.rglob("*") if file.is_file() and file.suffix in {".json", ".txt", ".safetensors"} and ".cache" not in file.relative_to(folder).parts)


def signatures(files):
    return {str(file): (file.stat().st_ino, file.stat().st_size, file.stat().st_mtime_ns, file.stat().st_ctime_ns) for file in files}


def fingerprint(folder: Path, files, runtime):
    digest = hashlib.sha256(json.dumps(runtime, sort_keys=True, ensure_ascii=False).encode())
    digest.update(Path(__file__).read_bytes())
    for file in files:
        digest.update(file.relative_to(folder).as_posix().encode() + b"\x00")
        content = hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                content.update(chunk)
        digest.update(content.digest())
    return digest.hexdigest()


class Engine:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.ready = False
        self.reason = "not_loaded"
        self.revision = ""
        self._lock = threading.Lock()

    def load(self):
        self.ready = False
        self.revision = ""
        folder = Path(self.model_dir).resolve()
        required = [folder / name for name in ("config.json", "tokenizer_config.json", "vocab.txt", "model.safetensors")]
        if not self.model_dir or not all(f.is_file() for f in required):
            self.reason = "model_missing"
            return
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            files = artifact_files(folder)
            before = signatures(files)
            # Fixed local directory, no remote code, no pickle weight fallback.
            self.tokenizer = AutoTokenizer.from_pretrained(str(folder), local_files_only=True, trust_remote_code=False)
            self.model = AutoModel.from_pretrained(str(folder), local_files_only=True, trust_remote_code=False, use_safetensors=True).to("cpu").eval()
            if self.model.config.hidden_size != 512 or self.model.config.model_type != "bert":
                self.reason = "model_mismatch"
                return
            torch.set_num_threads(max(1, min(8, int(os.getenv("BGE_CPU_THREADS", "2")))))
            runtime = {name: importlib.metadata.version(name) for name in ("torch", "transformers", "tokenizers", "safetensors")}
            runtime.update({"instruction": INSTRUCTION, "pooling": "CLS", "max_tokens": 512, "normalization": "l2", "device": "cpu", "threads": torch.get_num_threads()})
            revision = fingerprint(folder, files, runtime)
            if files != artifact_files(folder) or before != signatures(files):
                self.reason = "model_changed_during_load"
                return
            self.revision = revision
            self.ready = True
            self.reason = "ready"
        except Exception:
            self.ready = False
            self.reason = "model_load_failed"

    def embed(self, texts: list[str], query: bool):
        if not self.ready:
            raise HTTPException(503, "bge_not_ready")
        if not self._lock.acquire(blocking=False):
            raise HTTPException(429, "bge_busy")
        try:
            import torch
            data = [INSTRUCTION + text if query else text for text in texts]
            encoded = self.tokenizer(data, padding=True, truncation=True, max_length=512, return_tensors="pt")
            with torch.inference_mode():
                vectors = self.model(**encoded).last_hidden_state[:, 0]
                vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
            if vectors.shape != (len(texts), 512) or not torch.isfinite(vectors).all().item():
                raise ValueError("invalid embeddings")
            return vectors.tolist()
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "embedding_failed") from None
        finally:
            self._lock.release()


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    texts: list[str] = Field(min_length=1, max_length=32)
    query: bool = False

    @field_validator("texts")
    @classmethod
    def validate_text(cls, texts):
        if any(not text.strip() or len(text) > 4500 or "\x00" in text for text in texts):
            raise ValueError("invalid text")
        return texts


def create_app(key: str | None = None, engine=None):
    key = key if key is not None else os.getenv("BGE_API_KEY", "")
    worker = engine if engine is not None else Engine(os.getenv("BGE_MODEL_DIR", ""))

    @asynccontextmanager
    async def lifespan(app):
        if not TOKEN.fullmatch(key):
            raise RuntimeError("BGE_API_KEY must contain 24-512 printable non-space ASCII characters")
        worker.load()
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    auth = HTTPBearer(auto_error=False)

    def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(auth)):
        if not TOKEN.fullmatch(key) or credentials is None or not hmac.compare_digest(credentials.credentials.encode(), key.encode()):
            raise HTTPException(401, "unauthorized")

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        # Limit streamed bodies as well as Content-Length, before JSON validation.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 600_000:
                return JSONResponse({"detail": "request_too_large"}, status_code=413)
        request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _error):
        return JSONResponse({"detail": "invalid_request"}, status_code=422)

    @app.get("/health", dependencies=[Depends(authorize)])
    def health():
        return JSONResponse({"ready": worker.ready, "reason": worker.reason, "model": MODEL, "revision": worker.revision}, status_code=200 if worker.ready else 503)

    @app.post("/embed", dependencies=[Depends(authorize)])
    def embed(request: EmbeddingRequest):
        return {"model": MODEL, "revision": worker.revision, "vectors": worker.embed(request.texts, request.query)}

    return app


app = create_app()
