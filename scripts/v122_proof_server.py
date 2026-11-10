#!/usr/bin/env python3
"""Loopback-only enrollment server for the v122 first proof."""

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from scripts.v122_adapter import V122Adapter
    from scripts.v122_orchestrator import run_pipeline
except ImportError:
    from v122_adapter import V122Adapter
    from v122_orchestrator import run_pipeline


STAGES = ("materials", "avatar", "voice", "tts", "drive", "mp4")
MIME_EXTENSIONS = {
    "person": {"video/webm": ".webm", "video/mp4": ".mp4", "video/quicktime": ".mov"},
    "voice": {"audio/webm": ".webm", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3"},
}
LIMITS = {"person": 750_000_000, "voice": 100_000_000}


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temporary), str(path))


class ProofStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.runs = self.root / "runs"
        self.current_path = self.root / "current-run.json"
        self.lock = threading.RLock()
        self.runs.mkdir(parents=True, exist_ok=True)

    def _new_state(self):
        run_id = time.strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8]
        state = {"run_id": run_id, "bind": "127.0.0.1", "materials": {},
                 "text": {"reference_transcript": "", "new_script": ""},
                 "stages": {name: {"status": "pending", "error": ""} for name in STAGES},
                 "outputs": {}}
        (self.runs / run_id / "materials").mkdir(parents=True)
        _atomic_json(self.runs / run_id / "state.json", state)
        _atomic_json(self.current_path, {"run_id": run_id})
        return state

    def state(self):
        with self.lock:
            try:
                run_id = json.loads(self.current_path.read_text(encoding="utf-8"))["run_id"]
                path = self.runs / Path(run_id).name / "state.json"
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, KeyError):
                return self._new_state()

    def save(self, state):
        with self.lock:
            run_id = Path(str(state["run_id"])).name
            _atomic_json(self.runs / run_id / "state.json", state)

    def claim_generation(self):
        with self.lock:
            state = self.state()
            ready = all(state["materials"].get(k, {}).get("confirmed") for k in ("person", "voice")) and all(state["text"].values())
            if not ready:
                raise ValueError("人物、声音和文字尚未全部确认")
            if any(item["status"] == "running" for item in state["stages"].values()):
                raise RuntimeError("生成任务正在运行")
            state["stages"]["materials"] = {"status": "running", "error": ""}
            self.save(state)
            return state

    def upload(self, kind, mime, stream, length):
        extension = MIME_EXTENSIONS.get(kind, {}).get(mime.split(";", 1)[0].lower())
        if extension is None:
            raise ValueError("不支持的媒体格式")
        if length <= 0 or length > LIMITS[kind]:
            raise ValueError("媒体文件大小不符合要求")
        state = self.state(); run_dir = self.runs / state["run_id"] / "materials"
        temporary = run_dir / (kind + ".upload")
        digest = hashlib.sha256(); remaining = length
        with temporary.open("wb") as target:
            while remaining:
                chunk = stream.read(min(1024 * 1024, remaining))
                if not chunk: raise ValueError("媒体上传不完整")
                target.write(chunk); digest.update(chunk); remaining -= len(chunk)
        final = run_dir / (kind + extension); os.replace(str(temporary), str(final))
        state["materials"][kind] = {"path": "materials/" + final.name, "sha256": digest.hexdigest(),
                                     "bytes": length, "mime": mime, "confirmed": False}
        self.save(state); return state["materials"][kind]

    def delete_current(self):
        with self.lock:
            state = self.state(); target = self.runs / Path(state["run_id"]).name
            if any(item["status"] == "running" for item in state["stages"].values()):
                raise RuntimeError("生成任务运行中，不能删除")
            target.relative_to(self.runs); shutil.rmtree(target)
            self.current_path.unlink(missing_ok=True)


def make_handler(store, web_root):
    web_root = Path(web_root).resolve()
    class Handler(BaseHTTPRequestHandler):
        server_version = "V122Proof/1"
        def log_message(self, format, *args):
            return
        def _json(self, status, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(body)
        def _error(self, status, message): self._json(status, {"error": message})
        def _origin_ok(self):
            origin = self.headers.get("Origin")
            expected = "http://127.0.0.1:%d" % self.server.server_address[1]
            return origin in (None, expected)
        def _body_json(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 1_000_000: raise ValueError("请求过大")
            if not length: return {}
            value = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(value, dict): raise ValueError("请求必须是对象")
            return value
        def _route(self):
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or ".." in unquote(parsed.path).split("/"):
                raise ValueError("非法路径")
            return parsed.path
        def do_GET(self):
            try:
                path = self._route()
                if path == "/api/state": return self._json(200, store.state())
                if path in ("/api/media/generated.wav", "/api/media/final.mp4"):
                    state = store.state(); name = "generated.wav" if path.endswith(".wav") else "final.mp4"
                    candidate = store.runs / state["run_id"] / "outputs" / name
                    if not candidate.is_file(): return self._error(404, "media not ready")
                    body = candidate.read_bytes(); self.send_response(200)
                    self.send_header("Content-Type", "audio/wav" if name.endswith(".wav") else "video/mp4")
                    self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
                    self.end_headers(); self.wfile.write(body); return
                name = "index.html" if path == "/" else path.lstrip("/")
                candidate = (web_root / name).resolve(); candidate.relative_to(web_root)
                if not candidate.is_file(): return self._error(404, "not found")
                body = candidate.read_bytes(); self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self' blob:; script-src 'self'; style-src 'self'")
                self.end_headers(); self.wfile.write(body)
            except (ValueError, OSError) as error: self._error(400, str(error))
        def do_POST(self): self._mutate("POST")
        def do_PUT(self): self._mutate("PUT")
        def do_DELETE(self): self._mutate("DELETE")
        def _mutate(self, method):
            try:
                if not self._origin_ok() or self.headers.get("X-V122-Proof") != "1":
                    return self._error(403, "请求来源不允许")
                path = self._route()
                if method == "POST" and path in ("/api/materials/person", "/api/materials/voice"):
                    kind = path.rsplit("/", 1)[1]; length = int(self.headers.get("Content-Length", "0") or 0)
                    item = store.upload(kind, self.headers.get("Content-Type", ""), self.rfile, length)
                    return self._json(201, item)
                if method == "POST" and path.endswith("/confirm"):
                    kind = path.split("/")[-2]
                    if kind not in ("person", "voice"): return self._error(404, "not found")
                    state = store.state()
                    if kind not in state["materials"]: return self._error(409, "请先录入素材")
                    state["materials"][kind]["confirmed"] = True; store.save(state); return self._json(200, state)
                if method == "PUT" and path == "/api/text":
                    data = self._body_json()
                    if set(data) != {"reference_transcript", "new_script"}: raise ValueError("文字字段不完整")
                    if not all(isinstance(v, str) and v.strip() for v in data.values()): raise ValueError("文字不能为空")
                    state = store.state(); state["text"] = {k: v.strip() for k, v in data.items()}; store.save(state)
                    return self._json(200, state)
                if method == "POST" and path == "/api/generate":
                    try: state = store.claim_generation()
                    except (ValueError, RuntimeError) as error: return self._error(409, str(error))
                    runtime = store.root / "runtime/yunchuang_v122"
                    bridge = store.root / "proof/scripts/v122_runtime_bridge.py"
                    ffmpeg = runtime / "_internal/env/ffmpeg/bin/ffmpeg.exe"
                    if not runtime.is_dir() or not bridge.is_file() or not ffmpeg.is_file():
                        state["stages"]["materials"] = {"status": "blocked", "error": "V122_RUNTIME_INCOMPLETE"}
                        store.save(state); return self._json(409, state)
                    adapter = V122Adapter(runtime, bridge)
                    def work(): run_pipeline(store.root, state, adapter, ffmpeg, on_update=store.save)
                    threading.Thread(target=work, name="v122-proof-" + state["run_id"], daemon=True).start()
                    return self._json(202, state)
                if method == "DELETE" and path == "/api/current-run":
                    if self._body_json() != {"confirm": True}: raise ValueError("删除需要明确确认")
                    try: store.delete_current()
                    except RuntimeError as error: return self._error(409, str(error))
                    return self._json(200, {"deleted": True})
                return self._error(404, "not found")
            except (ValueError, OSError, json.JSONDecodeError) as error: self._error(400, str(error))
    return Handler


def create_server(root, web_root, port=5157):
    store = ProofStore(root)
    return ThreadingHTTPServer(("127.0.0.1", int(port)), make_handler(store, web_root))


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--web", required=True, type=Path); parser.add_argument("--port", type=int, default=5157)
    args = parser.parse_args(argv); server = create_server(args.root, args.web, args.port)
    print("http://127.0.0.1:%d/" % server.server_address[1], flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
