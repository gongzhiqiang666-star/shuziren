"""OpenCV camera reader used by the realtime image inference pipeline."""

from __future__ import annotations

import os
import platform
import queue
import re
import subprocess
import threading
import time
import cv2

from .origin_video_face_reader import VideoFaceReader


def _env_int(name, default):
    try: return int(os.environ.get(name, default))
    except (TypeError, ValueError): return int(default)


def _env_float(name, default):
    try: return float(os.environ.get(name, default))
    except (TypeError, ValueError): return float(default)


class RealtimeFaceReader(VideoFaceReader):
    SUPPORTED_RESOLUTIONS = ((1920, 1080), (1280, 720), (720, 1280), (640, 480))

    def __init__(self, device="cuda:0", enable_occluder=False, occluder_model_path="", face_model_dir=""):
        super().__init__(device, 1, enable_occluder, occluder_model_path, face_model_dir)
        self.camera_index = -1; self.camera_name = ""; self.cam_resolution = None

    @staticmethod
    def _camera_backends():
        if platform.system() == "Windows":
            return [("DirectShow", getattr(cv2, "CAP_DSHOW", None)), ("MSMF", getattr(cv2, "CAP_MSMF", None)), ("default", None)]
        if platform.system() == "Darwin": return [("AVFoundation", getattr(cv2, "CAP_AVFOUNDATION", None)), ("default", None)]
        return [("V4L2", getattr(cv2, "CAP_V4L2", None)), ("default", None)]

    @staticmethod
    def _create_capture(camera_index, backend):
        return cv2.VideoCapture(int(camera_index)) if backend is None else cv2.VideoCapture(int(camera_index), backend)

    @staticmethod
    def _dims_match(frame_w, frame_h, want_w, want_h):
        return abs(int(frame_w) - int(want_w)) <= 16 and abs(int(frame_h) - int(want_h)) <= 16

    @staticmethod
    def _resolution_display_name(resolution):
        value = str(resolution or "").lower().replace("p", "")
        aliases = {"720": "1280x720", "1080": "1920x1080", "720x1280": "720x1280", "1080x1920": "1080x1920"}
        return aliases.get(value, value if "x" in value else "1280x720")

    @classmethod
    def _parse_resolution(cls, resolution):
        text = cls._resolution_display_name(resolution); width, height = text.split("x", 1); return int(width), int(height)

    @staticmethod
    def get_available_cameras():
        cameras = {}
        if platform.system() == "Windows":
            try:
                result = subprocess.run([os.environ.get("FFMPEG_EXE", "ffmpeg"), "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], capture_output=True, text=True, timeout=8)
                section = result.stderr.split("DirectShow audio devices", 1)[0]
                names = re.findall(r'"([^\"]+)"\s*\(video\)', section, re.I)
                cameras.update(enumerate(dict.fromkeys(names)))
            except Exception: pass
        if cameras: return dict(cameras)
        for index in range(10):
            capture = RealtimeFaceReader._create_capture(index, RealtimeFaceReader._camera_backends()[0][1])
            try:
                if capture.isOpened(): cameras[index] = f"Camera {index}"
            finally: capture.release()
        return cameras

    @staticmethod
    def _probe_camera_at_resolution(camera_index, want_w, want_h, fps):
        for _, backend in RealtimeFaceReader._camera_backends():
            capture = RealtimeFaceReader._create_capture(camera_index, backend)
            try:
                if not capture.isOpened(): continue
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, want_w); capture.set(cv2.CAP_PROP_FRAME_HEIGHT, want_h)
                capture.set(cv2.CAP_PROP_FPS, fps); ok, frame = capture.read()
                if ok and frame is not None and RealtimeFaceReader._dims_match(frame.shape[1], frame.shape[0], want_w, want_h): return True
            finally: capture.release()
        return False

    @staticmethod
    def probe_camera_availability(camera_index, resolution=None, fps=30):
        cameras = RealtimeFaceReader.get_available_cameras(); available = int(camera_index) in cameras
        result = {"available": available, "camera_index": int(camera_index), "camera_name": cameras.get(int(camera_index), ""),
                  "resolution": resolution or "", "fps": int(fps)}
        if available and resolution:
            width, height = RealtimeFaceReader._parse_resolution(resolution); result["available"] = RealtimeFaceReader._probe_camera_at_resolution(camera_index, width, height, fps)
        return result

    @staticmethod
    def detect_best_camera_resolution(camera_index, fps=30):
        tested = []
        for width, height in RealtimeFaceReader.SUPPORTED_RESOLUTIONS:
            supported = RealtimeFaceReader._probe_camera_at_resolution(camera_index, width, height, fps)
            tested.append({"width": width, "height": height, "resolution": f"{width}x{height}", "supported": supported})
            if supported: return {"available": True, "camera_index": int(camera_index), "resolution": f"{width}x{height}",
                                  "width": width, "height": height, "fps": fps, "tested_resolutions": tested}
        return {"available": False, "camera_index": int(camera_index), "resolution": "", "tested_resolutions": tested}

    @staticmethod
    def detect_best_camera_resolution_by_name(camera_name):
        cameras = RealtimeFaceReader.get_available_cameras(); index = next((i for i, name in cameras.items() if name == camera_name), -1)
        result = RealtimeFaceReader.detect_best_camera_resolution(index) if index >= 0 else {"available": False, "camera_index": -1, "resolution": ""}
        result["camera_name"] = camera_name; return result

    def _open_camera_with_opencv(self, camera_index, camera_name, cam_resolution=None):
        width, height = self._parse_resolution(cam_resolution or "1280x720")
        for backend_name, backend in self._camera_backends():
            capture = self._create_capture(camera_index, backend)
            if not capture.isOpened(): capture.release(); continue
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1); capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height); capture.set(cv2.CAP_PROP_FPS, 30)
            ok, frame = capture.read()
            if ok and frame is not None:
                self.capture = capture; self.width, self.height = frame.shape[1], frame.shape[0]; self.fps = float(capture.get(cv2.CAP_PROP_FPS) or 30)
                self.backend_name = backend_name; return frame
            capture.release()
        raise RuntimeError(f"无法打开摄像头 {camera_name or camera_index}")

    def _is_capture_running(self): return bool(self.capture_thread and self.capture_thread.is_alive() and not self.stop_event.is_set())

    def _capture_thread(self):
        try:
            while not self.stop_event.is_set():
                capture = self.capture
                if capture is None: break
                ok, frame = capture.read()
                if not ok or frame is None: break
                try:
                    self.raw_frames_queue.put_nowait(frame)
                except queue.Full:
                    # A live camera must stay near real time. Drop the oldest unprocessed
                    # frame instead of turning a brief slowdown into seconds of latency.
                    try: self.raw_frames_queue.get_nowait()
                    except queue.Empty: pass
                    try: self.raw_frames_queue.put_nowait(frame)
                    except queue.Full: pass
        finally:
            try: self.raw_frames_queue.put_nowait(None)
            except queue.Full:
                try: self.raw_frames_queue.get_nowait()
                except queue.Empty: pass
                try: self.raw_frames_queue.put_nowait(None)
                except queue.Full: pass

    def stop_capture(self):
        self.stop_event.set()
        capture = self.capture
        thread = self.capture_thread
        if thread and thread.is_alive() and thread is not threading.current_thread(): thread.join(timeout=.5)
        # Camera drivers can block indefinitely in read(). Release only as a fallback,
        # after giving the loop a chance to observe stop_event and exit normally.
        if capture is not None: capture.release()
        self.capture = None
        for thread in (self.capture_thread, self.preprocess_thread):
            if thread and thread.is_alive() and thread is not threading.current_thread(): thread.join(timeout=1.5)
        self.capture_thread = self.preprocess_thread = None

    def start_capture(self, camera_index, cam_resolution=None):
        self.stop_capture(); cameras = self.get_available_cameras(); self.camera_index = int(camera_index)
        self.camera_name = cameras.get(self.camera_index, f"Camera {self.camera_index}"); self.cam_resolution = cam_resolution
        first = self._open_camera_with_opencv(self.camera_index, self.camera_name, cam_resolution)
        self.stop_event.clear(); self.internal_buffer.clear(); self.raw_frames_queue = queue.Queue(self.queue_buffer_size)
        self.processed_frames_queue = queue.Queue(self.queue_buffer_size); self.raw_frames_queue.put(first)
        self.capture_thread = threading.Thread(target=self._capture_thread, name="camera-face-capture", daemon=True)
        self.preprocess_thread = threading.Thread(target=self._preprocess_thread, name="camera-face-preprocess", daemon=True)
        self.capture_thread.start(); self.preprocess_thread.start(); return first

    def _get_live_frame_batch(self):
        frames = []; timeout = _env_float("DH_LIVE_FRAME_WAIT_TIMEOUT", .2)
        while len(frames) < self.batch_size:
            try: frame = self.raw_frames_queue.get(timeout=timeout)
            except queue.Empty: break
            if frame is None: break
            frames.append(frame)
        return frames

    def _attach_full_mask(self, frame, detection):
        return self.face_pipeline._attach_full_mask(frame, detection) if detection else detection

    def rewind(self): return False
