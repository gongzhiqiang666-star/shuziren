"""Own loopback console: python -m scripts.local_console --data-directory PATH."""
import argparse
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
from urllib.parse import urlsplit

from scripts.local_console_config import ConfigError, ConfigStore, preflight

WEB = Path(__file__).parent / "local-console"


def create_server(store, port=None):
    token = secrets.token_urlsafe(32)
    lock = threading.RLock()
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
                filename = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}.get(path)
                if filename:
                    mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[filename]
                    return self.respond(200, (WEB / filename).read_bytes(), mime + "; charset=utf-8")
                return self.respond(404, {"error": "页面不存在"})
            except (ConfigError, OSError) as error:
                self.respond(400, {"error": str(error)})

        def do_POST(self):
            origin = "http://127.0.0.1:%d" % self.server.server_port
            if (not self.trusted_host() or self.headers.get("Origin") != origin
                    or not secrets.compare_digest(self.headers.get("X-Console-Token", ""), token)):
                return self.respond(403, {"error": "请求来源或会话无效，请刷新页面"})
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ConfigError("需要JSON请求")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ConfigError("请求长度无效")
                value = json.loads(self.rfile.read(length).decode("utf-8"))
                path = urlsplit(self.path).path
                with lock:
                    if path == "/api/config":
                        return self.respond(200, {"config": store.save(value), "message": "已保存；端口修改在下次启动生效"})
                    if path == "/api/preflight":
                        return self.respond(200, preflight(value))
                return self.respond(404, {"error": "接口不存在"})
            except (ValueError, UnicodeError, OSError) as error:
                self.respond(400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", configured_port if port is None else port), Handler)
    server.daemon_threads = True
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
    try:
        server = create_server(store, args.port)
    except OSError as error:
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
        logging.info("控制台已关闭")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
