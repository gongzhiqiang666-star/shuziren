"""Looping 25-fps video/audio tape used by origin-frame live playback."""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ORIGIN_FPS = 25.0


@dataclass
class TapeFrame:
    image: np.ndarray
    audio: np.ndarray
    index: int
    frame_index: int
    epoch: int = 0
    generation: int = 0


class OriginTape:
    def __init__(self, video_path: str, output_sample_rate: int = 24000, prefetch: int = 24):
        self.video_path = str(Path(video_path).expanduser().resolve())
        self.output_sample_rate = int(output_sample_rate); self.prefetch = max(1, int(prefetch))
        self.capture = None; self.source_fps = ORIGIN_FPS; self.source_frame_count = 0
        self.width = self.height = self.total_frames = 0; self.samples_per_frame = self.output_sample_rate / ORIGIN_FPS
        self.audio = np.zeros(0, np.float32); self._queue = queue.Queue(maxsize=self.prefetch)
        self._stop = threading.Event(); self._thread = None; self._seek_lock = threading.Lock()
        self._pending_seek = None; self._play_index = 0; self._epoch = 0; self._generation = 0
        self._sample_pointer = 0; self._opened = False

    def open(self):
        if self._opened: return
        if not Path(self.video_path).is_file(): raise FileNotFoundError(self.video_path)
        capture = cv2.VideoCapture(self.video_path)
        if not capture.isOpened(): raise RuntimeError(f"无法打开视频: {self.video_path}")
        self.capture = capture; self.source_fps = float(capture.get(cv2.CAP_PROP_FPS) or ORIGIN_FPS)
        self.source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0); self.height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = self.source_frame_count / self.source_fps if self.source_fps else 0
        self.total_frames = max(1, round(duration * ORIGIN_FPS)); self._load_origin_audio(duration); self._opened = True

    def _load_origin_audio(self, duration: float):
        command = [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", self.video_path, "-vn", "-ac", "1",
                   "-ar", str(self.output_sample_rate), "-f", "f32le", "-"]
        result = subprocess.run(command, capture_output=True)
        expected = max(0, round(duration * self.output_sample_rate))
        if result.returncode == 0 and result.stdout:
            audio = np.frombuffer(result.stdout, np.float32).copy()
            if expected: audio = audio[:expected] if len(audio) >= expected else np.pad(audio, (0, expected - len(audio)))
            self.audio = audio
        else: self.audio = np.zeros(expected, np.float32)

    def start(self, start_index: int = 0):
        self.open(); self.stop(); self._stop.clear(); self.seek_index(start_index)
        self._thread = threading.Thread(target=self._prefetch_loop, name="origin-tape-prefetch", daemon=True); self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread(): self._thread.join(timeout=2)
        self._thread = None; self._clear_queue()

    def close(self):
        self.stop()
        if self.capture is not None: self.capture.release()
        self.capture = None; self._opened = False

    def _clear_queue(self):
        while True:
            try: self._queue.get_nowait()
            except queue.Empty: break

    def _wrap_index(self, index: int): return int(index) % max(self.total_frames, 1)
    def index_to_sample(self, index: int): return round(int(index) * self.output_sample_rate / ORIGIN_FPS)
    def sample_to_index(self, sample: int): return round(int(sample) * ORIGIN_FPS / self.output_sample_rate)
    def ms_to_index(self, start_ms: int): return round(max(0, int(start_ms)) * ORIGIN_FPS / 1000)

    @property
    def sample_pointer(self): return int(self._sample_pointer)
    @sample_pointer.setter
    def sample_pointer(self, sample): self._sample_pointer = max(0, int(sample))

    def get_audio(self, index: int):
        start, end = self.index_to_sample(index), self.index_to_sample(index + 1); needed = end - start
        if not len(self.audio): return np.zeros(needed, np.float32)
        positions = np.arange(start, end, dtype=np.int64) % len(self.audio)
        return self.audio[positions].copy()

    def get_audio_clip(self, end_sample: int, seconds: float):
        needed = max(0, round(seconds * self.output_sample_rate)); end = max(0, int(end_sample)); start = max(0, end - needed)
        if not len(self.audio): return np.zeros(end - start, np.float32), start, end
        positions = np.arange(start, end, dtype=np.int64) % len(self.audio)
        return self.audio[positions].copy(), start, end

    def seek_index(self, index: int):
        self.open(); target = self._wrap_index(index)
        with self._seek_lock:
            self._generation += 1; self._pending_seek = target; self._play_index = target
            self._sample_pointer = self.index_to_sample(target)
            self._clear_queue()
        return target

    def seek_ms(self, start_ms: int): return self.seek_index(self.ms_to_index(start_ms))

    def _source_frame_for_output(self, out_index: int):
        return min(max(0, self.source_frame_count - 1), int(round(self._wrap_index(out_index) * self.source_fps / ORIGIN_FPS)))

    def _prefetch_loop(self):
        current_source = -1
        while not self._stop.is_set():
            try:
                with self._seek_lock:
                    if self._pending_seek is not None:
                        self._play_index = self._pending_seek; self._pending_seek = None; current_source = -1
                    index, epoch, generation = self._play_index, self._epoch, self._generation
                source = self._source_frame_for_output(index)
                if source != current_source + 1: self.capture.set(cv2.CAP_PROP_POS_FRAMES, source)
                ok, image = self.capture.read(); current_source = source
                if not ok:
                    self.capture.set(cv2.CAP_PROP_POS_FRAMES, source); ok, image = self.capture.read()
                if not ok: raise RuntimeError(f"读取视频帧失败: {source}")
                packet = TapeFrame(image=image, audio=self.get_audio(index), index=index,
                                   frame_index=source, epoch=epoch, generation=generation)
                self._queue.put(packet, timeout=.1)
                with self._seek_lock:
                    if generation == self._generation:
                        next_index = index + 1
                        if next_index >= self.total_frames: self._epoch += 1
                        self._play_index = self._wrap_index(next_index)
            except queue.Full: continue
            except Exception:
                if not self._stop.is_set(): time.sleep(.02)

    def _take_one(self, timeout: float):
        try: return self._queue.get(timeout=max(0, timeout))
        except queue.Empty: return None

    def take_frames(self, count: int, timeout: float = 2.0):
        deadline = time.monotonic() + timeout; frames = []
        while len(frames) < count:
            packet = self._take_one(deadline - time.monotonic())
            if packet is None: break
            if packet.generation != self._generation:
                continue
            frames.append(packet); self._sample_pointer = self.index_to_sample(packet.index + 1)
        return frames

    def __del__(self):
        try: self.close()
        except Exception: pass
