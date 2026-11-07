"""Read JSON messages from the local barrage bridge."""

import json
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from time import monotonic, sleep


class DanmuBridge:
    def __init__(self, url="ws://127.0.0.1:8888", *, heartbeat_interval=15):
        self.url = url
        self._socket = None
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_stop = None

    def start(self):
        from websocket import create_connection

        self._socket = create_connection(self.url, timeout=5)
        self._socket.settimeout(None)
        self._heartbeat_stop = Event()
        Thread(
            target=self._keep_alive, args=(self._socket, self._heartbeat_stop), daemon=True,
        ).start()

    def _keep_alive(self, socket, stop):
        while not stop.is_set():
            try:
                socket.send('{"type":"heartbeat"}')
            except Exception:
                socket.shutdown()
                return
            if stop.wait(self._heartbeat_interval):
                return

    def __iter__(self):
        socket = self._socket
        while socket is not None and self._socket is socket:
            try:
                raw = socket.recv()
            except Exception:
                if self._socket is not socket:
                    return
                raise
            if not raw:
                return
            try:
                message = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(message, dict):
                continue
            kind = message.get("type")
            if kind == "heartbeat":
                socket.send('{"type":"heartbeat_ack"}')
            elif kind != "heartbeat_ack":
                yield message

    def stop(self):
        socket, self._socket = self._socket, None
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if socket is not None:
            try:
                if socket.connected:
                    socket.send_close()
            except OSError:
                pass
            finally:
                socket.shutdown()


class _SubprocessDanmuBridge(DanmuBridge):
    def __init__(self, module, *arguments):
        super().__init__()
        self.module = module
        self.arguments = arguments
        self._process = None

    def start(self):
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            [sys.executable, "-m", self.module, *self.arguments],
            cwd=Path(__file__).resolve().parent,
        )
        deadline = monotonic() + 10
        try:
            while True:
                exit_code = self._process.poll()
                if exit_code is not None:
                    raise RuntimeError(f"{self.module} exited with code {exit_code}")
                try:
                    super().start()
                    return
                except ConnectionRefusedError:
                    if monotonic() >= deadline:
                        raise
                    sleep(0.1)
        except BaseException:
            self.stop()
            raise

    def __iter__(self):
        process = self._process
        receive_error = None
        try:
            yield from super().__iter__()
        except Exception as error:
            receive_error = error
        if process is not None and self._process is process:
            try:
                exit_code = process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                exit_code = None
            if exit_code and self._process is process:
                raise RuntimeError(f"{self.module} exited with code {exit_code}") from receive_error
        if receive_error is not None:
            raise receive_error

    def stop(self):
        try:
            super().stop()
        finally:
            process, self._process = self._process, None
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


class OCRDanmuBridge(_SubprocessDanmuBridge):
    def __init__(self, platform):
        super().__init__("danmu_ocr.run", "--platform", platform)


class KuaishouDanmuBridge(_SubprocessDanmuBridge):
    def __init__(self, live_url):
        super().__init__("kuaishou_v2.ws_server_kuaishou", live_url)
