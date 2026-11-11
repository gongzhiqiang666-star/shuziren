"""Threaded video decoder and batch face reader for origin-frame mode."""

from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
import cv2

from .image_face_reader_runtime import RealtimeFacePipeline


class VideoFaceReader:
    def __init__(self, device="cuda:0", detect_max_faces=1, enable_occluder=False,
                 occluder_model_path="", face_model_dir=""):
        self.device = device; self.detect_max_faces = max(1, int(detect_max_faces))
        self.face_pipeline = RealtimeFacePipeline(device, self.detect_max_faces, enable_occluder,
                                                  occluder_model_path, face_model_dir)
        self.batch_size = 4; self.queue_buffer_size = 32
        self.raw_frames_queue = queue.Queue(self.queue_buffer_size); self.processed_frames_queue = queue.Queue(self.queue_buffer_size)
        self.capture = None; self.ffmpeg_process = None; self.stderr_thread = None
        self.capture_thread = self.preprocess_thread = None; self.stop_event = threading.Event()
        self.video_path = ""; self.start_ms = 0; self.width = self.height = 0; self.fps = 25.0
        self.frame_count = 0; self.internal_buffer = []

    def _get_video_properties(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): raise RuntimeError(f"无法打开视频: {video_path}")
        try: return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), float(cap.get(cv2.CAP_PROP_FPS) or 25)
        finally: cap.release()

    def start_capture(self, video_path, start_ms=0):
        path = str(Path(video_path).expanduser().resolve())
        if not Path(path).is_file(): raise FileNotFoundError(path)
        start_ms = max(0, int(start_ms))
        width, height, fps = self._get_video_properties(path)
        ffmpeg=shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if not ffmpeg:raise FileNotFoundError("找不到 ffmpeg 可执行文件")
        self.stop_capture()
        if any(thread is not None and thread.is_alive()
               for thread in (self.capture_thread, self.preprocess_thread)):
            raise RuntimeError("上一段视频仍在停止，请稍后重试")
        self.width, self.height, self.fps = width, height, fps
        self.video_path, self.start_ms = path, start_ms; self.stop_event.clear(); self.internal_buffer.clear()
        self.raw_frames_queue = queue.Queue(self.queue_buffer_size); self.processed_frames_queue = queue.Queue(self.queue_buffer_size)
        command=[ffmpeg,"-hide_banner","-loglevel","warning"]
        if self.start_ms:command.extend(("-ss",f"{self.start_ms/1000:.3f}"))
        command.extend(("-stream_loop","-1","-i",path,"-an","-vcodec","rawvideo","-pix_fmt","bgr24","-f","rawvideo","pipe:1"))
        flags=getattr(subprocess,"CREATE_NO_WINDOW",0) if sys.platform=="win32" else 0
        self.ffmpeg_process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,creationflags=flags)
        self.capture=self.ffmpeg_process.stdout
        self.stderr_thread=threading.Thread(target=self._drain_stderr,name="video-face-ffmpeg-stderr",daemon=True)
        self.stderr_thread.start()
        self.capture_thread = threading.Thread(target=self._capture_thread, name="video-face-capture", daemon=True)
        self.preprocess_thread = threading.Thread(target=self._preprocess_thread, name="video-face-preprocess", daemon=True)
        self.capture_thread.start(); self.preprocess_thread.start(); return self

    def stop_capture(self):
        self.stop_event.set()
        process,self.ffmpeg_process=self.ffmpeg_process,None
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
        for thread in (self.capture_thread, self.preprocess_thread):
            if thread and thread.is_alive() and thread is not threading.current_thread(): thread.join(timeout=2)
        for pipe in (getattr(process,"stdout",None),getattr(process,"stderr",None)):
            if pipe is not None:
                try:pipe.close()
                except OSError:pass
        stderr_thread,self.stderr_thread=self.stderr_thread,None
        if stderr_thread and stderr_thread.is_alive() and stderr_thread is not threading.current_thread():stderr_thread.join(timeout=1)
        self.capture = None
        if self.capture_thread is not None and not self.capture_thread.is_alive():
            self.capture_thread = None
        if self.preprocess_thread is not None and not self.preprocess_thread.is_alive():
            self.preprocess_thread = None

    def _drain_stderr(self):
        process=self.ffmpeg_process
        pipe=getattr(process,"stderr",None) if process is not None else None
        if pipe is None:return
        try:
            for line in iter(pipe.readline,b""):
                if not line or self.stop_event.is_set():break
                text=line.decode("utf-8",errors="replace").strip() if isinstance(line,bytes) else str(line).strip()
                if text:print(f"ffmpeg-warn: {text}")
        except (OSError,ValueError):pass

    def _capture_thread(self):
        try:
            frame_size=self.width*self.height*3
            while not self.stop_event.is_set():
                raw=bytearray()
                while len(raw)<frame_size and not self.stop_event.is_set():
                    chunk=self.capture.read(frame_size-len(raw))
                    if not chunk:break
                    raw.extend(chunk)
                if len(raw)!=frame_size:break
                import numpy as np
                frame=np.frombuffer(raw,dtype=np.uint8).reshape(self.height,self.width,3).copy()
                while not self.stop_event.is_set():
                    try: self.raw_frames_queue.put(frame, timeout=.1); break
                    except queue.Full: continue
        finally:
            try: self.raw_frames_queue.put(None, timeout=.2)
            except queue.Full: pass

    def _detect_faces_batch(self, frames_batch): return self.face_pipeline.detect_batch(frames_batch)

    def _preprocess_thread(self):
        batch = []
        while not self.stop_event.is_set():
            try: frame = self.raw_frames_queue.get(timeout=.2)
            except queue.Empty:
                if self.capture_thread and not self.capture_thread.is_alive(): frame = None
                else: continue
            if frame is not None: batch.append(frame)
            if len(batch) >= self.batch_size or (frame is None and batch):
                detections = self._detect_faces_batch(batch)
                while not self.stop_event.is_set():
                    try: self.processed_frames_queue.put((batch, detections), timeout=.1); break
                    except queue.Full: continue
                batch = []
            if frame is None: break
        try: self.processed_frames_queue.put(None, timeout=.2)
        except queue.Full: pass

    def __iter__(self): return self
    def __next__(self):
        if self.internal_buffer:
            frames, detections = zip(*self.internal_buffer); self.internal_buffer.clear(); return list(frames), list(detections)
        while True:
            try: item = self.processed_frames_queue.get(timeout=1)
            except queue.Empty:
                if self.preprocess_thread and self.preprocess_thread.is_alive(): continue
                raise StopIteration
            if item is None: raise StopIteration
            return item

    def read_ahead(self, count):
        frames, detections = [], []
        while len(frames) < count:
            try: batch_frames, batch_detections = next(self)
            except StopIteration: break
            needed = count - len(frames); frames.extend(batch_frames[:needed]); detections.extend(batch_detections[:needed])
            self.internal_buffer.extend(zip(batch_frames[needed:], batch_detections[needed:]))
        return frames, detections

    def rewind(self):
        if not self.video_path: return False
        self.start_capture(self.video_path, 0); return True

    def seek(self, start_ms):
        if not self.video_path: return False
        self.start_capture(self.video_path, start_ms); return True

    def __del__(self):
        try: self.stop_capture()
        except Exception: pass
