"""Low-latency FFmpeg RTMP reader for the v2 inference pipeline."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
import numpy as np

from .origin_video_face_reader import VideoFaceReader


def _env_int(name, default):
    try: return int(os.environ.get(name, default))
    except (TypeError, ValueError): return int(default)


def _env_float(name, default):
    try: return float(os.environ.get(name, default))
    except (TypeError, ValueError): return float(default)


class RtmpFaceReader(VideoFaceReader):
    def __init__(self, device="cuda:0", enable_occluder=False, occluder_model_path="", face_model_dir=""):
        super().__init__(device, 1, enable_occluder, occluder_model_path, face_model_dir)
        self.ffmpeg_process = None; self.stderr_thread = None; self.rtmp_url = ""
        self.first_frame = threading.Event()
        self.capture_lock = threading.RLock()

    @staticmethod
    def _make_even(value, minimum=2): return max(minimum, int(value) // 2 * 2)

    def _get_video_properties(self, rtmp_url):
        return self._probe_video_properties(rtmp_url, None)

    def _probe_video_properties(self, rtmp_url, cancel):
        configured_ffmpeg = os.environ.get("FFMPEG_EXE")
        ffprobe = shutil.which("ffprobe") or "ffprobe"
        if configured_ffmpeg:
            ffmpeg = Path(configured_ffmpeg)
            companion = ffmpeg.with_name("ffprobe" + ffmpeg.suffix)
            if companion.is_file():
                ffprobe = str(companion)
        command = [ffprobe, "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height,avg_frame_rate", "-of", "json", rtmp_url]
        if cancel is None:
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            except subprocess.TimeoutExpired:
                raise TimeoutError("RTMP 视频探测超时") from None
        else:
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as probe:
                deadline = time.monotonic() + 15
                try:
                    while not cancel.is_set() and time.monotonic() < deadline:
                        try:
                            stdout, stderr = probe.communicate(timeout=.2)
                        except subprocess.TimeoutExpired:
                            continue
                        result = subprocess.CompletedProcess(command, probe.returncode, stdout, stderr)
                        break
                    else:
                        raise TimeoutError("RTMP 重连已取消或探测超时")
                finally:
                    if probe.poll() is None:
                        probe.kill()
                        probe.communicate()
        if result.returncode:
            diagnostic = result.stderr.strip().replace(rtmp_url, "[RTMP 地址]")
            raise RuntimeError(diagnostic or "RTMP 视频探测失败")
        streams = json.loads(result.stdout).get("streams")
        if not streams:
            raise RuntimeError("RTMP 输入没有视频轨")
        stream = streams[0]
        width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            raise RuntimeError("RTMP 视频分辨率无效")
        numerator, _, denominator = str(stream.get("avg_frame_rate") or "25/1").partition("/")
        fps = float(numerator) / max(float(denominator or 1), 1)
        return width, height, fps or 25.0

    def _build_ffmpeg_video_filter(self, fps): return "null"

    def _build_ffmpeg_command(self, rtmp_url, fps):
        analyzed = _env_int("DH_LIVE_RTMP_ANALYZEDURATION", 1000000); probe = _env_int("DH_LIVE_RTMP_PROBESIZE", 1000000)
        command = [os.environ.get("FFMPEG_EXE") or shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "warning"]
        if not Path(rtmp_url).is_file():
            timeout = _env_int("DH_LIVE_RTMP_RW_TIMEOUT_US", 5_000_000)
            command += ["-rw_timeout", str(timeout), "-fflags", "nobuffer", "-flags", "low_delay",
                        "-analyzeduration", str(analyzed), "-probesize", str(probe)]
        return command + ["-i", rtmp_url, "-map", "0:v:0", "-an", "-vf", self._build_ffmpeg_video_filter(fps),
                          "-pix_fmt", "bgr24", "-f", "rawvideo", "-fps_mode", "passthrough", "-"]

    def _reset_pipeline_state(self):
        self.internal_buffer.clear(); self.raw_frames_queue = queue.Queue(self.queue_buffer_size)
        self.processed_frames_queue = queue.Queue(self.queue_buffer_size)

    def start_capture(self, rtmp_url):
        return self._start_capture(rtmp_url)

    def reconnect(self, cancel):
        return self._start_capture(self.rtmp_url, cancel)

    def _start_capture(self, rtmp_url, cancel=None):
        self.stop_capture()
        url = str(rtmp_url)
        properties = self._probe_video_properties(url, cancel)
        with self.capture_lock:
            if cancel is not None and cancel.is_set():
                raise RuntimeError("RTMP 重连已取消")
            self.rtmp_url = url
            self.width, self.height, self.fps = properties
            self._start_decoder()
        timeout = _env_float("DH_LIVE_INITIAL_FRAME_WAIT_TIMEOUT", 10.0)
        if not self._wait_for_initial_frame(timeout, cancel):
            self.stop_capture()
            if cancel is not None and cancel.is_set():
                raise RuntimeError("RTMP 重连已取消")
            raise TimeoutError("等待 RTMP 首帧超时")
        return self

    def _start_decoder(self):
        self.stop_event.clear(); self._reset_pipeline_state()
        self.first_frame.clear()
        self.ffmpeg_process = subprocess.Popen(self._build_ffmpeg_command(self.rtmp_url, self.fps), stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, bufsize=self.width * self.height * 3 * 2)
        self.stderr_thread = threading.Thread(target=self._drain_stderr, name="rtmp-ffmpeg-stderr", daemon=True)
        self.capture_thread = threading.Thread(target=self._capture_thread, name="rtmp-face-capture", daemon=True)
        self.preprocess_thread = threading.Thread(target=self._preprocess_thread, name="rtmp-face-preprocess", daemon=True)
        self.stderr_thread.start(); self.capture_thread.start(); self.preprocess_thread.start()

    def _wait_for_initial_frame(self, timeout, cancel=None):
        deadline = time.monotonic() + timeout
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                return False
            if self.first_frame.is_set(): return True
            if self.capture_thread is not None and not self.capture_thread.is_alive():
                return self.first_frame.is_set()
            time.sleep(.02)
        return False

    def _capture_thread(self):
        size = self.width * self.height * 3
        process = self.ffmpeg_process
        try:
            while not self.stop_event.is_set():
                data = process.stdout.read(size)
                if len(data) != size: break
                frame = np.frombuffer(data, np.uint8).reshape(self.height, self.width, 3).copy()
                while not self.stop_event.is_set():
                    try:
                        self.raw_frames_queue.put(frame, timeout=.1)
                        self.first_frame.set()
                        break
                    except queue.Full: continue
        finally:
            try: self.raw_frames_queue.put(None, timeout=.2)
            except queue.Full: pass

    def _drain_stderr(self):
        if not self.ffmpeg_process or not self.ffmpeg_process.stderr: return
        for _ in iter(self.ffmpeg_process.stderr.readline, b""):
            if self.stop_event.is_set(): break

    def _get_live_frame_batch(self):
        frames = []
        timeout = _env_float("DH_LIVE_FRAME_WAIT_TIMEOUT", .2)
        while len(frames) < self.batch_size:
            try: frame = self.raw_frames_queue.get(timeout=timeout)
            except queue.Empty: break
            if frame is None: break
            frames.append(frame)
        return frames

    def _attach_full_mask(self, frame, detection):
        return self.face_pipeline._attach_full_mask(frame, detection) if detection else detection

    def stop_capture(self):
        with self.capture_lock:
            self._stop_decoder()

    def _stop_decoder(self):
        self.stop_event.set()
        process = self.ffmpeg_process
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=1)
        for thread in (self.capture_thread, self.preprocess_thread, self.stderr_thread):
            if thread and thread.is_alive() and thread is not threading.current_thread(): thread.join(timeout=2)
        if process:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
        self.ffmpeg_process = None
        self.capture_thread = self.preprocess_thread = self.stderr_thread = None

    def rewind(self): return False
