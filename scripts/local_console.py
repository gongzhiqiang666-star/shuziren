"""Own loopback console: python -m scripts.local_console --data-directory PATH."""
import argparse
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import socket
import sqlite3
import threading
from urllib.parse import urlsplit, parse_qs

from scripts.local_console_config import ConfigError, ConfigStore, preflight
from scripts.product_store import ProductStore, Conflict, ProductError
from scripts.voice_store import VoiceStore, VoiceError

WEB = Path(__file__).parent / "local-console"


class ConsoleServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def server_close(self):
        cleanup = getattr(self, 'cleanup_tasks', None)
        if cleanup: cleanup()
        super().server_close()


class InstanceLock:
    """OS-held lock; a crashed process releases it without trusting a stale PID."""
    def __init__(self, directory):
        self.path = Path(directory) / "console.lock"
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise OSError("同一配置目录的控制台已运行") from None
        return self

    def __exit__(self, *args):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def create_server(store, port=None):
    token = secrets.token_urlsafe(32)
    lock = threading.RLock()
    def products():
        return ProductStore(store.directory)
    task_manager = None
    tasks_closed = False
    def tasks():
        nonlocal task_manager
        with lock:
            if tasks_closed: raise ProductError('控制台正在退出')
            if task_manager is None:
                from scripts.llm_tasks import LLMTasks
                task_manager = LLMTasks(products())
            return task_manager
    def cleanup():
        nonlocal tasks_closed
        with lock:
            tasks_closed = True
            if task_manager is not None: task_manager.close()
    try:
        settings = store.load()
        configured_port = settings["port"]
    except ConfigError:
        configured_port = 5158  # Serve the visible error; never overwrite corrupt settings.

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.info("HTTP %s", fmt % args)

        def respond(self, status, body, content_type="application/json; charset=utf-8"):
            content = json.dumps(body, ensure_ascii=False).encode("utf-8") if isinstance(body, dict) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)

        def trusted_host(self):
            return self.headers.get("Host") == "127.0.0.1:%d" % self.server.server_port

        def do_GET(self):
            if not self.trusted_host():
                return self.respond(403, {"error": "请求地址不允许"})
            path = urlsplit(self.path).path
            try:
                if path == "/api/state":
                    with lock:
                        config = store.load()
                    return self.respond(200, {"config": config, "token": token,
                                              "listening_port": self.server.server_port,
                                              "live_status": "未启动", "data_directory": str(store.directory.resolve())})
                if path == "/api/session":
                    return self.respond(200, {"token": token})
                if path == '/api/voices':
                    voices=VoiceStore(store.directory)
                    return self.respond(200,{'voices':voices.list(),'selected':voices.selected()})
                if path == '/api/voices/audio':
                    ids=parse_qs(urlsplit(self.path).query).get('id',[])
                    if len(ids)!=1: raise VoiceError('请选择音色')
                    return self.respond(200,VoiceStore(store.directory).audio_path(ids[0]).read_bytes(),'audio/wav')
                if path == "/api/products":
                    data = products()
                    return self.respond(200, {"products": data.list(), "selected": data.selected()})
                if path == "/api/llm/state":
                    from scripts.console_llm import status
                    return self.respond(200, {**status(), "task":tasks().state()})
                if path == "/api/scripts":
                    query = parse_qs(urlsplit(self.path).query)
                    ids = query.get("product_id", [])
                    if len(ids) != 1:
                        raise ProductError("请选择商品")
                    data=products()
                    return self.respond(200, {"scripts": data.scripts(ids[0]),'selected':data.selected_script(ids[0])})
                filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}.get(path)
                if filename:
                    mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[filename]
                    return self.respond(200, (WEB / filename).read_bytes(), mime + "; charset=utf-8")
                return self.respond(404, {"error": "页面不存在"})
            except sqlite3.Error:
                self.respond(503, {"error": "商品数据库无法读取，请检查文件与权限；原数据未重置"})
            except (ValueError, OSError) as error:
                self.respond(400, {"error": str(error)})

        def do_POST(self):
            origin = "http://127.0.0.1:%d" % self.server.server_port
            if (not self.trusted_host() or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-Console-Token", ""), token)):
                # Drain small rejected requests so Windows does not reset the socket
                # before the client can receive the explicit 403 response.
                length=self.headers.get('Content-Length','0')
                if length.isdecimal() and 0<int(length)<=1048576:
                    self.connection.settimeout(2)
                    try: self.rfile.read(int(length))
                    except OSError: pass
                return self.respond(403, {"error": "请求来源或会话无效，请刷新页面"})
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ConfigError("需要JSON请求")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1048576:
                    raise ConfigError("请求长度无效")
                value = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(value, dict):
                    raise ConfigError("请求必须为对象")
                path = urlsplit(self.path).path
                with lock:
                    if path == "/api/shutdown":
                        if value != {"confirm": True}:
                            raise ConfigError("退出请求无效")
                        self.respond(200, {"message": "控制台正在退出"})
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
                        return
                    if path == "/api/config":
                        return self.respond(200, {"config": store.save(value), "message": "已保存；端口修改在下次启动生效"})
                    if path == "/api/preflight":
                        return self.respond(200, preflight(value))
                    if path == '/api/voices/import':
                        if set(value)!={'source','transcript','name'} or not isinstance(value['source'],str):
                            raise VoiceError('音色导入字段无效')
                        report=preflight(store.load())
                        if not report['runtime_root']: raise VoiceError('请先配置本机运行资源目录')
                        ffmpeg=Path(report['runtime_root'])/'_internal/env/ffmpeg/bin/ffmpeg.exe'
                        voice=VoiceStore(store.directory).import_audio(value['source'],value['transcript'],value['name'],ffmpeg)
                        return self.respond(201,{'voice':voice})
                    if path == '/api/voices/select':
                        if set(value)!={'voice_id'} or not isinstance(value['voice_id'],str):
                            raise VoiceError('音色选择字段无效')
                        VoiceStore(store.directory).select(value['voice_id'])
                        return self.respond(200,{'selected':value['voice_id']})
                    if path == "/api/products":
                        allowed = {"title", "content", "product_index", "product_id", "version"}
                        if not {"title", "content", "product_index"} <= value.keys() or value.keys() - allowed:
                            raise ProductError("商品字段不完整或包含未知字段")
                        return self.respond(200, {"product": products().save(**value)})
                    if path == "/api/llm/generate":
                        if set(value) != {"product_id", "version", "instructions"} or not isinstance(value['product_id'], str):
                            raise ProductError("生成字段无效")
                        return self.respond(202, {"task":tasks().start(value['product_id'],value['version'],value['instructions'])})
                    if path == "/api/llm/cancel":
                        if set(value) != {"task_id"}: raise ProductError("取消字段无效")
                        return self.respond(200, {"task":tasks().cancel(value['task_id'])})
                    if path == "/api/products/select":
                        if set(value) != {"product_id"} or not isinstance(value["product_id"], str):
                            raise ProductError("请选择有效商品")
                        products().select(value["product_id"])
                        return self.respond(200, {"selected": value["product_id"]})
                    if path == "/api/scripts":
                        if not {'snapshot','text'} <= value.keys() or value.keys()-{'snapshot','text','parent_script_id'}:
                            raise ProductError("话术字段不完整")
                        script_id = products().add_script(value["snapshot"], value["text"],parent_script_id=value.get('parent_script_id'))
                        return self.respond(201, {"id": script_id})
                    if path == '/api/scripts/select':
                        if set(value)!={'product_id','script_id'} or not all(isinstance(v,str) for v in value.values()):
                            raise ProductError('话术选择字段无效')
                        products().select_script(value['product_id'],value['script_id'])
                        return self.respond(200,{'selected':value['script_id']})
                return self.respond(404, {"error": "接口不存在"})
            except Conflict as error:
                self.respond(409, {"error": str(error)})
            except sqlite3.Error:
                self.respond(503, {"error": "商品数据库操作失败，请检查文件与权限；原数据未重置"})
            except (ValueError, UnicodeError, OSError) as error:
                self.respond(400, {"error": str(error)})

    server = ConsoleServer(("127.0.0.1", configured_port if port is None else port), Handler)
    server.daemon_threads = True
    server.cleanup_tasks = cleanup
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="数字人本地控制台")
    parser.add_argument("--data-directory", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    store = ConfigStore(args.data_directory)
    store.directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=store.directory / "console.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    instance = InstanceLock(store.directory)
    try:
        instance.__enter__()
        server = create_server(store, args.port)
    except OSError as error:
        instance.__exit__()
        logging.error("启动失败：%s", error)
        print("控制台启动失败，请检查端口是否占用：%s" % error, flush=True)
        return 1
    print("http://127.0.0.1:%d/" % server.server_port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        instance.__exit__()
        logging.info("控制台已关闭")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
