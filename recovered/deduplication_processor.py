"""Recovered frame transformations used to vary relayed/recorded video."""

from __future__ import annotations

import random
import threading
import time
from queue import Empty, Full, Queue
from typing import Any, Dict, Iterable, Optional, Tuple

import numpy as np


class CompositeFrameProcessor:
    def __init__(self, processors: Iterable[Any]):
        self.processors = list(processors)

    def process(self, frame_info: Dict[str, Any]) -> Dict[str, Any]:
        result = frame_info
        for processor in self.processors:
            result = processor.process(result)
        return result

    def stop(self) -> None:
        errors = []
        for processor in reversed(self.processors):
            stop = getattr(processor, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception as error:
                    errors.append(error)
        if errors:
            raise RuntimeError(f"画面去重资源停止失败: {errors[0]}") from errors[0]


class MirrorProcessor:
    def __init__(self, probability: float = 1.0):
        self.probability = max(0.0, min(1.0, float(probability)))

    def process(self, frame_info: Dict[str, Any]) -> Dict[str, Any]:
        import cv2

        if random.random() >= self.probability:
            return frame_info
        result = dict(frame_info)
        result["frame"] = cv2.flip(frame_info["frame"], 1)
        result["mirrored"] = True
        return result


class FrameDropProcessor:
    def __init__(self, drop_chance: float = 0.02):
        self.drop_chance = max(0.0, min(1.0, float(drop_chance)))
        self.last_frame: Optional[np.ndarray] = None

    def process(self, frame_info: Dict[str, Any]) -> Dict[str, Any]:
        frame = frame_info["frame"]
        result = dict(frame_info)
        if self.last_frame is not None and random.random() < self.drop_chance:
            result["frame"] = self.last_frame.copy()
            result["frame_drop"] = True
        else:
            self.last_frame = frame.copy()
        return result


class JitterProcessor:
    def __init__(self, jitter_range: Tuple[int, int] = (-2, 2), probability: float = 0.3):
        self.jitter_range = self._normalize_range(jitter_range, (-2, 2))
        self.probability = max(0.0, min(1.0, float(probability)))

    @staticmethod
    def _normalize_range(value: Any, default: Tuple[int, int]) -> Tuple[int, int]:
        try:
            left, right = map(int, value)
        except (TypeError, ValueError):
            return default
        return (left, right) if left <= right else (right, left)

    def process(self, frame_info: Dict[str, Any]) -> Dict[str, Any]:
        import cv2

        if random.random() >= self.probability:
            return frame_info
        frame = frame_info["frame"]
        height, width = frame.shape[:2]
        shift_x = random.randint(*self.jitter_range)
        shift_y = random.randint(*self.jitter_range)
        matrix = np.float32([[1, 0, shift_x], [0, 1, shift_y]])
        result = dict(frame_info)
        result["frame"] = cv2.warpAffine(
            frame, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE
        )
        result["jitter"] = (shift_x, shift_y)
        return result


class ChromaticAberrationProcessor:
    def __init__(self, shift_range: Tuple[int, int] = (-3, 3), probability: float = 0.3):
        self.shift_range = JitterProcessor._normalize_range(shift_range, (-3, 3))
        self.probability = max(0.0, min(1.0, float(probability)))

    def process(self, frame_info: Dict[str, Any]) -> Dict[str, Any]:
        import cv2

        if random.random() >= self.probability:
            return frame_info
        frame = frame_info["frame"]
        height, width = frame.shape[:2]
        left, right = self.shift_range
        red_shift, blue_shift = random.randint(left, right), random.randint(left, right)
        red_matrix = np.float32([[1, 0, red_shift], [0, 1, 0]])
        blue_matrix = np.float32([[1, 0, blue_shift], [0, 1, 0]])
        blue, green, red = cv2.split(frame)
        shifted_blue = cv2.warpAffine(blue, blue_matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
        shifted_red = cv2.warpAffine(red, red_matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
        result = dict(frame_info)
        result["frame"] = cv2.merge((shifted_blue, green, shifted_red))
        result["chromatic_aberration"] = (blue_shift, red_shift)
        return result


class RotationProcessor:
    def __init__(
        self,
        angle_range: Tuple[float, float] = (-1.0, 1.0),
        interval_range: Tuple[float, float] = (1.0, 3.0),
        duration: float = 0.5,
    ):
        self.angle_range = self._normalize_float_range(angle_range, (-1.0, 1.0))
        self.interval_range = self._normalize_float_range(interval_range, (1.0, 3.0))
        self.duration = max(0.001, float(duration))
        self.next_tilt_time = time.monotonic() + random.uniform(*self.interval_range)
        self.tilt_start_time = 0.0
        self.target_angle = 0.0
        self.is_tilting = False

    @staticmethod
    def _normalize_float_range(value: Any, default: Tuple[float, float]) -> Tuple[float, float]:
        try:
            left, right = map(float, value)
        except (TypeError, ValueError):
            return default
        return (left, right) if left <= right else (right, left)

    def process(self, frame_info: Dict[str, Any]) -> Dict[str, Any]:
        import cv2

        now = time.monotonic()
        if not self.is_tilting and now >= self.next_tilt_time:
            self.is_tilting = True
            self.tilt_start_time = now
            self.target_angle = random.uniform(*self.angle_range)
        if not self.is_tilting:
            return frame_info
        progress = min(1.0, (now - self.tilt_start_time) / self.duration)
        angle = self.target_angle * np.sin(np.pi * progress)
        frame = frame_info["frame"]
        height, width = frame.shape[:2]
        matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), float(angle), 1.0)
        result = dict(frame_info)
        result["frame"] = cv2.warpAffine(frame, matrix, (width, height), borderMode=cv2.BORDER_REPLICATE)
        result["rotation"] = float(angle)
        if progress >= 1.0:
            self.is_tilting = False
            self.next_tilt_time = now + random.uniform(*self.interval_range)
        return result


class OverlayProcessor:
    def __init__(self, video_path: str, alpha: float = 0.03):
        import cv2

        if not video_path:
            raise ValueError("overlay video_path is required")
        self.video_path = video_path
        self.alpha = max(0.0, min(1.0, float(alpha)))
        self.capture = cv2.VideoCapture(video_path)
        if not self.capture.isOpened():
            self.capture.release()
            raise ValueError(f"无法打开叠加视频: {video_path}")
        fps = float(self.capture.get(cv2.CAP_PROP_FPS) or 25.0)
        self.frame_interval = 1.0 / max(1.0, fps)
        self._frame_queue: Queue[np.ndarray] = Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._target_size_lock = threading.Lock()
        self._target_size: Optional[Tuple[int, int]] = None
        self._last_overlay_frame: Optional[np.ndarray] = None
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        import cv2

        while not self._stop_event.is_set():
            started = time.monotonic()
            ok, frame = self.capture.read()
            if not ok:
                self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._stop_event.wait(self.frame_interval)
                continue
            with self._target_size_lock:
                target = self._target_size
            if target and frame.shape[1::-1] != target:
                frame = cv2.resize(frame, target, interpolation=cv2.INTER_AREA)
            self._put_latest_frame(frame)
            self._stop_event.wait(max(0.0, self.frame_interval - (time.monotonic() - started)))

    def _put_latest_frame(self, frame: np.ndarray) -> None:
        try:
            self._frame_queue.put_nowait(frame)
        except Full:
            try:
                self._frame_queue.get_nowait()
            except Empty:
                pass
            self._frame_queue.put_nowait(frame)

    def process(self, frame_info: Dict[str, Any]) -> Dict[str, Any]:
        import cv2

        main_frame = frame_info["frame"]
        height, width = main_frame.shape[:2]
        with self._target_size_lock:
            self._target_size = (width, height)
        try:
            while True:
                self._last_overlay_frame = self._frame_queue.get_nowait()
        except Empty:
            pass
        overlay = self._last_overlay_frame
        if overlay is None:
            return frame_info
        if overlay.shape[:2] != main_frame.shape[:2]:
            overlay = cv2.resize(overlay, (width, height), interpolation=cv2.INTER_AREA)
        result = dict(frame_info)
        result["frame"] = cv2.addWeighted(main_frame, 1.0 - self.alpha, overlay, self.alpha, 0.0)
        result["overlay"] = True
        return result

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self.capture.release()


class DeduplicationFrameProcessor(CompositeFrameProcessor):
    def __init__(self, config: Optional[Dict[str, Any]]):
        config = dict(config or {})
        processors = []
        mirror_cfg = config.get("mirror") or {}
        if mirror_cfg.get("enabled"):
            processors.append(MirrorProcessor(mirror_cfg.get("probability", 1.0)))
        drop_cfg = config.get("frame_drop") or {}
        if drop_cfg.get("enabled"):
            processors.append(FrameDropProcessor(drop_cfg.get("drop_chance", 0.02)))
        jitter_cfg = config.get("jitter") or {}
        if jitter_cfg.get("enabled"):
            processors.append(JitterProcessor(jitter_cfg.get("jitter_range", (-2, 2)), jitter_cfg.get("probability", 0.3)))
        chromatic_cfg = config.get("chromatic_aberration") or {}
        if chromatic_cfg.get("enabled"):
            processors.append(ChromaticAberrationProcessor(chromatic_cfg.get("shift_range", (-3, 3)), chromatic_cfg.get("probability", 0.3)))
        rotation_cfg = config.get("rotation") or {}
        if rotation_cfg.get("enabled"):
            processors.append(RotationProcessor(rotation_cfg.get("angle_range", (-1.0, 1.0)), rotation_cfg.get("interval_range", (1.0, 3.0)), rotation_cfg.get("duration", 0.5)))
        overlay_cfg = config.get("overlay") or {}
        overlay_path = overlay_cfg.get("video_path") or overlay_cfg.get("path")
        if overlay_cfg.get("enabled") and not overlay_path:
            raise ValueError("启用叠加去重时必须配置 overlay video_path")
        if overlay_cfg.get("enabled") and overlay_path:
            processors.append(OverlayProcessor(str(overlay_path), overlay_cfg.get("alpha", 0.03)))
        super().__init__(processors)

