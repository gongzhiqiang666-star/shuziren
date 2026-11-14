"""Video decoding and audio alignment for the recovered face/hand player."""

import random
from collections import deque
from contextlib import ExitStack, closing
from threading import Event, Lock, Thread, current_thread
from time import monotonic

import numpy as np

from .video_player import _AudioOutput, _VirtualCamOutput, _WindowOutput, _pick_sample_rate
from .output_mode import normalize_output_mode


def _align_audio_to_frames(audio, frame_count, spf):
    """Fit mono samples to the number of samples consumed by the video."""
    sample_count = frame_count * spf
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size >= sample_count:
        return audio[:sample_count]
    aligned = np.zeros(sample_count, dtype=np.float32)
    aligned[:audio.size] = audio
    return aligned


def _silence_bytes(frame_count):
    return bytes(frame_count * np.dtype(np.float32).itemsize)


def _audio_bytes(chunk, frame_count):
    if chunk is None:
        return _silence_bytes(frame_count)
    return _align_audio_to_frames(chunk, frame_count, 1).tobytes()


def _release_capture(cap):
    if cap is not None:
        cap.release()


def _open_capture(path):
    import cv2

    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        return cap
    _release_capture(cap)
    raise OSError(f"无法打开视频：{path}")


def _iter_clip_frames(path):
    """Yield OpenCV BGR frames and release the capture when iteration ends."""
    cap = _open_capture(path)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                return
            yield frame
    finally:
        _release_capture(cap)


class FaceHandVideoStreamManager:
    """Select face and hand clips from separate rotation pools."""

    def __init__(
        self, *, face_videos, hand_videos, window_width=720, window_height=1280,
        image_output_mode="window", fps=25,
    ):
        self.face_videos = list(face_videos)
        self.hand_videos = list(hand_videos)
        self.window_width = window_width
        self.window_height = window_height
        self.image_output_mode = normalize_output_mode(image_output_mode)
        self.fps = fps
        self._face_history = []
        self._hand_history = []
        self._clip_lock = Lock()
        self._clip = None
        self._face_done = False
        self._on_face_done = None
        self._audio_queues = {"danmu": deque(), "normal": deque()}
        self._av_queue = deque()
        self._latest_frame = None
        self._video_output = None
        self._tts_samples = np.empty(0, dtype=np.float32)
        self._tts_path = None
        self._tts_queue_name = None
        self.sample_rate = 44100
        self._stop = Event()
        self._worker = None
        self._ready = Event()
        self.last_error = None

    def _choose(self, pool, history):
        if not pool:
            return ""
        candidates = [path for path in pool if path not in history]
        if not candidates:
            history.clear()
            candidates = pool
        selected = random.choice(candidates)
        history.append(selected)
        return selected

    def play_face_clip(self, video_path=None):
        with self._clip_lock:
            path = video_path or self._choose(self.face_videos, self._face_history)
            if path:
                self._clip = ("face", path)
                self._face_done = False
            return path

    def play_hand_clip(self, video_path=None):
        with self._clip_lock:
            path = video_path or self._choose(self.hand_videos, self._hand_history)
            if path:
                self._clip = ("hand", path)
            return path

    def is_face_phase(self):
        with self._clip_lock:
            return self._clip is not None and self._clip[0] == "face"

    def set_on_face_done(self, callback):
        with self._clip_lock:
            self._on_face_done = callback

    def consume_face_clip_done(self):
        with self._clip_lock:
            done = self._face_done
            self._face_done = False
            return done

    def _finish_clip(self, clip):
        with self._clip_lock:
            if clip is not self._clip:
                return
            self._clip = None
            if clip[0] == "hand":
                if self._worker is current_thread() and not self._stop.is_set() and self.hand_videos:
                    path = self._choose(self.hand_videos, self._hand_history)
                    self._clip = ("hand", path)
                return
            self._face_done = True
            callback = self._on_face_done
        if callback is not None:
            callback()

    def _iter_current_clip(self, clip=None):
        """Decode the selected clip until EOF or until another clip replaces it."""
        if clip is None:
            with self._clip_lock:
                clip = self._clip
        if clip is None:
            return
        with closing(_iter_clip_frames(clip[1])) as frames:
            for frame in frames:
                resized = self._resize(frame)
                with self._clip_lock:
                    if clip is not self._clip:
                        return
                yield resized
        self._finish_clip(clip)

    def _resize(self, frame):
        if frame.shape[:2] == (self.window_height, self.window_width):
            return frame
        import cv2

        return cv2.resize(
            frame, (self.window_width, self.window_height),
            interpolation=cv2.INTER_LINEAR,
        )

    def _put_av(self, frame, chunk, audio_path, *, meta="frame"):
        with self._clip_lock:
            if self._stop.is_set():
                return False
            self._av_queue.append({
                "frame": frame,
                "audio": np.asarray(chunk, dtype=np.float32).reshape(-1),
                "audio_path": audio_path,
                "meta": meta,
            })
        return True

    def _drain_av_queue(self):
        with self._clip_lock:
            self._av_queue.clear()

    def _show(self, frame):
        self._latest_frame = frame
        output = self._video_output
        if output is not None and frame is not None:
            return output.render(frame)
        return frame is not None

    def _audio_callback(self, in_data, frame_count, time_info, status):
        with self._clip_lock:
            packet = self._av_queue.popleft() if self._av_queue else None
        if packet is None:
            chunk, path = self._take_tts(frame_count)
        else:
            self._show(packet["frame"])
            chunk, path = packet["audio"], packet["audio_path"]
        with self._clip_lock:
            self._tts_path = path
        try:
            import pyaudio
            continuation = pyaudio.paContinue
        except ImportError:
            continuation = 0
        return _audio_bytes(chunk, frame_count), continuation

    def _play_face(self, path):
        audio = self._decode_audio(path)
        samples_per_frame = self.sample_rate / self.fps
        remainder = 0.0
        emitted = False
        for frame in _iter_clip_frames(path):
            if self._stop.is_set():
                break
            remainder += samples_per_frame
            count = int(remainder); remainder -= count
            chunk = _align_audio_to_frames(audio, 1, count); audio = audio[count:]
            if not self._put_av(self._resize(frame), chunk, path, meta="face"):
                break
            emitted = True
        return emitted

    def _play_hand(self, path):
        samples_per_frame = self.sample_rate / self.fps
        remainder = 0.0
        for frame in _iter_clip_frames(path):
            if self._stop.is_set():
                return
            remainder += samples_per_frame
            count = int(remainder); remainder -= count
            chunk, audio_path = self._take_tts(count)
            if not self._put_av(self._resize(frame), chunk, audio_path, meta="hand"):
                return

    def _display_loop(self):
        while not self._stop.is_set():
            with self._clip_lock:
                frame = self._latest_frame
            if frame is not None and not self._show(frame):
                return
            self._stop.wait(max(0.001, 1 / self.fps))

    @property
    def is_playing(self):
        with self._clip_lock:
            return self._worker is not None and self._worker.is_alive() and not self._stop.is_set()

    def start_playing(self):
        with self._clip_lock:
            if self._worker is not None and self._worker.is_alive():
                return self._ready.is_set() and not self._stop.is_set()
            if self.fps <= 0:
                self.last_error = "视频输出配置无效"
                return False
            self.last_error = None
            self._stop.clear()
            self._ready.clear()
            self._worker = Thread(target=self._run, daemon=True)
            self._worker.start()
        self._ready.wait()
        return self.last_error is None and not self._stop.is_set()

    def stop_playing(self):
        with self._clip_lock:
            self._stop.set()
            worker = self._worker
        if worker is not None and worker is not current_thread():
            worker.join()

    def _run(self):
        try:
            with ExitStack() as cleanup:
                if self.image_output_mode == "window":
                    output = _WindowOutput(self.window_width, self.window_height)
                else:
                    output = _VirtualCamOutput(self.window_width, self.window_height, self.fps)
                cleanup.callback(output.close)
                self._video_output = output
                audio = _AudioOutput()
                cleanup.callback(audio.close)
                self.sample_rate = audio.sample_rate
                samples_per_frame = self.sample_rate / self.fps
                sample_remainder = 0.0
                self._ready.set()
                while not self._stop.is_set():
                    with self._clip_lock:
                        clip = self._clip
                    if clip is None:
                        self._stop.wait(0.01)
                        continue
                    original = self._decode_audio(clip[1]) if clip[0] == "face" else None
                    deadline = monotonic()
                    with closing(self._iter_current_clip(clip)) as frames:
                        for frame in frames:
                            if self._stop.is_set() or not output.render(frame):
                                return
                            sample_remainder += samples_per_frame
                            sample_count = int(sample_remainder)
                            sample_remainder -= sample_count
                            if original is None:
                                samples, _ = self._take_tts(sample_count)
                            else:
                                samples = _align_audio_to_frames(original, 1, sample_count)
                                original = original[sample_count:]
                            audio.play(samples.tobytes())
                            deadline += 1 / self.fps
                            if self._stop.wait(max(0, deadline - monotonic())):
                                return
                    self._stop.wait(0.01)
        except Exception as error:
            self.last_error = str(error)
        finally:
            self._video_output = None
            self._stop.set()
            self._ready.set()

    def add_audio_to_queue(
        self, audio_path, queue_name="normal", use_silent_features=False, target_face_index=0,
    ):
        with self._clip_lock:
            queue = self._audio_queues.setdefault(queue_name, deque())
            queue.append((audio_path, use_silent_features, target_face_index))
            if queue_name == "danmu" and self._tts_queue_name == "normal":
                self._tts_samples = np.empty(0, dtype=np.float32)
                self._tts_path = None
                self._tts_queue_name = None

    def get_queue_lengths(self):
        with self._clip_lock:
            return {name: len(queue) for name, queue in self._audio_queues.items()}

    def clear_audio_queues(self):
        with self._clip_lock:
            for queue in self._audio_queues.values():
                queue.clear()
            self._tts_samples = np.empty(0, dtype=np.float32)
            self._tts_path = None
            self._tts_queue_name = None

    def _load_tts(self, path):
        return self._decode_audio(path)

    def _decode_audio(self, path):
        import av

        resampler = av.AudioResampler(format="flt", layout="mono", rate=self.sample_rate)
        chunks = []
        with av.open(path) as container:
            if not container.streams.audio:
                return np.empty(0, dtype=np.float32)
            for frame in container.decode(audio=0):
                chunks.extend(part.to_ndarray().reshape(-1) for part in resampler.resample(frame))
            chunks.extend(part.to_ndarray().reshape(-1) for part in resampler.resample(None))
        return np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)

    def _take_tts(self, spf):
        with self._clip_lock:
            if not self._tts_samples.size:
                self._tts_path = None
                self._tts_queue_name = None
                for queue_name, queue in self._audio_queues.items():
                    if queue:
                        path, _, _ = queue.popleft()
                        self._tts_samples = self._load_tts(path)
                        self._tts_path = path
                        self._tts_queue_name = queue_name
                        break
            chunk = _align_audio_to_frames(self._tts_samples, 1, spf)
            self._tts_samples = self._tts_samples[spf:]
            return chunk, self._tts_path

    def get_current_playing_audio_path(self):
        with self._clip_lock:
            return self._tts_path
