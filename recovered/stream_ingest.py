"""Recovered external Douyin stream to local SRS relay process."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

DEFAULT_SRS_HOST = "127.0.0.1"
DEFAULT_SRS_PORT = 1935
DEFAULT_SRS_APP = "live"


class DouyinStreamResolver:
    """Resolve a Douyin room page to concrete live media URLs."""

    def __init__(self):
        from tools.get_douyin_flv.get_douyin_live_url import get_live_url_sync, normalize_live_url

        self.get_live_url_sync = get_live_url_sync
        self.normalize_live_url = normalize_live_url

    def _normalize_room_url(self, room_url: str) -> str:
        value = str(room_url or "").strip()
        if not value:
            raise ValueError("抖音直播间地址不能为空")
        match = re.search(r"live\.douyin\.com/(\d+)", value)
        if match:
            return f"https://live.douyin.com/{match.group(1)}"
        if value.isdigit():
            return f"https://live.douyin.com/{value}"
        if "douyin.com" not in value:
            raise ValueError("无效的抖音直播间地址")
        if not value.startswith(("http://", "https://")):
            value = "https://" + value
        return self.normalize_live_url(value)

    def build_candidates(self, stream_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        seen = set()
        for key, mode in (("flv_url", "copy"), ("m3u8_url", "copy"), ("flv_url", "transcode"), ("m3u8_url", "transcode")):
            url = str(stream_data.get(key) or "").strip()
            pair = (url, mode)
            if url and pair not in seen:
                seen.add(pair); candidates.append(pair)
        return candidates

    def resolve(self, room_url: str) -> Dict[str, Any]:
        normalized_url = self._normalize_room_url(room_url)
        stream_data = self.get_live_url_sync(normalized_url)
        if not isinstance(stream_data, dict):
            raise RuntimeError("无法解析抖音直播流")
        if not stream_data.get("is_live", True):
            raise RuntimeError("抖音直播间当前未开播")
        candidates = self.build_candidates(stream_data)
        if not candidates:
            raise RuntimeError("抖音直播间未返回可用流地址")
        return {**stream_data, "room_url": normalized_url, "candidates": candidates}


class LiveStreamIngestProcess:
    """Convert an external live stream into one stable local RTMP stream."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = dict(config or {})
        self.process: Optional[subprocess.Popen] = None
        self.stderr_thread: Optional[threading.Thread] = None
        self.stderr_lines = deque(maxlen=80)
        self._stop_requested = False
        self.stream_name = f"douyin_relay_{uuid4().hex}"
        self.local_playback_url = self._build_local_playback_url()
        self.last_error = ""
        self.resolver = DouyinStreamResolver()

    def start(self, room_url: str) -> str:
        self.stop()
        self._stop_requested = False
        self.stderr_lines.clear()
        data = self.resolver.resolve(room_url)
        failed_error = ""
        candidates = data.get("candidates") or self.resolver.build_candidates(data)
        allow_transcode = self._as_bool(self.config.get("douyin_transcode_fallback", True))
        for upstream_url, mode in candidates:
            if mode == "transcode" and not allow_transcode:
                continue
            try:
                self._start_ffmpeg(upstream_url, mode)
                if self._wait_until_stable():
                    return self.local_playback_url
                code = self.process.poll() if self.process is not None else -1
                failed_error = self._format_ffmpeg_error(-1 if code is None else code)
            except Exception as error:
                failed_error = str(error)
            self._stop_process()
        self.last_error = failed_error or "无法启动抖音直播流转发"
        raise RuntimeError(self.last_error)

    def stop(self) -> None:
        self._stop_requested = True
        self._stop_process()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _start_ffmpeg(self, upstream_url: str, mode: str) -> None:
        command = self._build_ffmpeg_command(upstream_url, mode)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self.stderr_thread.start()

    def _build_ffmpeg_command(self, upstream_url: str, mode: str) -> List[str]:
        timeout_us = int(float(self.config.get("douyin_rw_timeout_seconds", 15)) * 1_000_000)
        delay_max = str(int(self.config.get("douyin_reconnect_delay_max", 10)))
        command = [
            self._resolve_ffmpeg_executable(), "-hide_banner", "-nostats", "-loglevel", "warning",
            "-nostdin", "-fflags", "+genpts", "-rw_timeout", str(timeout_us),
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", delay_max,
            "-i", upstream_url, "-map", "0:v:0?", "-map", "0:a:0?",
        ]
        if mode == "transcode":
            command += ["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-c:a", "aac", "-ar", "44100"]
        else:
            command += ["-c:v", "copy", "-c:a", "copy"]
        return command + ["-f", "flv", self.local_playback_url]

    def _wait_until_stable(self) -> bool:
        startup_wait = max(0.1, float(self.config.get("douyin_ingest_startup_wait", 3.0)))
        deadline = time.monotonic() + startup_wait
        while time.monotonic() < deadline:
            if self._stop_requested or self.process is None or self.process.poll() is not None:
                return False
            time.sleep(0.1)
        return self.is_running()

    def _drain_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            clean = self._sanitize_log_line(line)
            if clean:
                self.stderr_lines.append(clean)

    def _format_ffmpeg_error(self, return_code: int) -> str:
        detail = " | ".join(list(self.stderr_lines)[-8:])
        return f"FFmpeg 启动失败，返回码 {return_code}" + (f": {detail}" if detail else "")

    def _stop_process(self) -> None:
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=3)
        thread, self.stderr_thread = self.stderr_thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)

    def _build_local_playback_url(self) -> str:
        host = str(self.config.get("local_srs_host") or DEFAULT_SRS_HOST)
        port = int(self.config.get("local_srs_port") or DEFAULT_SRS_PORT)
        app = str(self.config.get("local_srs_app") or DEFAULT_SRS_APP).strip("/")
        return f"rtmp://{host}:{port}/{app}/{self.stream_name}"

    def _resolve_ffmpeg_executable(self) -> str:
        configured = str(self.config.get("ffmpeg_executable") or self.config.get("ffmpeg_path") or "").strip()
        if configured and Path(configured).is_file():
            return str(Path(configured).resolve())
        found = shutil.which("ffmpeg")
        if found:
            return found
        root = Path(__file__).resolve().parent.parent
        for candidate in (root / "env/ffmpeg/bin/ffmpeg.exe", root / "env_50/ffmpeg/bin/ffmpeg.exe"):
            if candidate.is_file():
                return str(candidate)
        raise FileNotFoundError("未找到 FFmpeg 可执行文件")

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}
        return bool(value)

    @staticmethod
    def _sanitize_log_line(line: str) -> str:
        text = str(line or "").rstrip()
        text = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?<redacted>", text)
        return text

