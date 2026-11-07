"""KT overlay entry point shared by the recovered inference frame players."""

from collections import deque
import sys
from threading import Thread
from time import time

from .product_kt_overlay import apply_product_kt_overlay


SAMPLE_RATE = 16000
FPS = 25


def _apply_kt_overlay(frame, physical_index=None):
    return apply_product_kt_overlay(frame, physical_index=physical_index)


def _resolve_output_sample_rate(py_audio, preferred_rate, channels=1):
    from pyaudio import paFloat32

    try:
        device = py_audio.get_default_output_device_info()
        default_rate = int(device["defaultSampleRate"])
    except Exception:
        default_rate = 0

    candidates = [preferred_rate]
    if default_rate > 0:
        candidates.append(default_rate)
    candidates.extend((48000, 44100, 32000, 24000))
    for rate in dict.fromkeys(candidates):
        try:
            if py_audio.is_format_supported(
                rate, output_channels=channels, output_format=paFloat32,
            ):
                return rate
        except Exception:
            continue
    return default_rate or 48000


class CVPlayer:
    def __init__(self, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("Window dimensions must be positive")
        self.window_width = width
        self.window_height = height
        self._frame = None
        self._window_title = "数字人直播"
        self.is_fullscreen = False
        self._render_thread = None
        self._playing = False

    def calculate_new_size(self, width, height):
        if width <= 0 or height <= 0:
            raise ValueError("Frame dimensions must be positive")
        scale = min(self.window_width / width, self.window_height / height)
        return max(1, int(width * scale)), max(1, int(height * scale))

    def add_frame(self, frame):
        self._frame = frame

    def mouse_callback(self, event, x, y, flags, param):
        import cv2

        if event == cv2.EVENT_LBUTTONDBLCLK:
            fullscreen = not self.is_fullscreen
            mode = cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL
            cv2.setWindowProperty(self._window_title, cv2.WND_PROP_FULLSCREEN, mode)
            self.is_fullscreen = fullscreen

    def remove_window_buttons(self):
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, self._window_title)
            if not hwnd:
                return False
            style = user32.GetWindowLongW(hwnd, -16)
            user32.SetWindowLongW(hwnd, -16, style & ~0x00080000 & ~0x00040000)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x27)
            return True
        except (AttributeError, OSError):
            return False

    def render_loop(self):
        import cv2

        title = self._window_title
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        try:
            cv2.setMouseCallback(title, self.mouse_callback)
            while self._playing:
                frame = self._frame
                if frame is not None:
                    height, width = frame.shape[:2]
                    size = self.calculate_new_size(width, height)
                    cv2.imshow(title, cv2.resize(frame, size))
                if cv2.waitKey(15) & 0xFF == 27:
                    break
                if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            self._playing = False
            self.is_fullscreen = False
            try:
                cv2.destroyWindow(title)
            except cv2.error:
                pass

    def _run_render_loop(self):
        try:
            self.render_loop()
        finally:
            self._playing = False

    def start_playback(self):
        if self._playing or (self._render_thread is not None and self._render_thread.is_alive()):
            return
        self._playing = True
        if sys.platform == "win32":
            self._render_thread = Thread(target=self._run_render_loop, daemon=True)
            try:
                self._render_thread.start()
            except BaseException:
                self._playing = False
                raise
        else:
            self._run_render_loop()

    def stop_playback(self):
        self._playing = False


class StreamPlayer:
    def __init__(self, window_width, window_height):
        from threading import Event, Lock

        self.player = CVPlayer(window_width, window_height)
        self._queue = deque()
        self._stream = None
        self._audio_backend = None
        self.SAMPLE_RATE = SAMPLE_RATE
        self.samples_per_frame = self.SAMPLE_RATE // FPS
        self._queue_lock = Lock()
        self._playback_lock = Lock()
        self._output_frame_count = 0
        self._audio_frame_count = 0
        self._reused_frame_count = 0
        self._last_frame_info = None
        self._stop_event = Event()
        self.running = False

    def upload_frame(self, frame_info):
        with self._queue_lock:
            self._queue.append(frame_info)

    def clear_queues(self):
        with self._queue_lock:
            self._queue.clear()
            self._last_frame_info = None

    def get_queue_length(self):
        with self._queue_lock:
            return len(self._queue)

    def get_queue_item_at_index(self, index):
        with self._queue_lock:
            try:
                return self._queue[index]
            except IndexError:
                return None

    def get_last_queue_item(self):
        return self.get_queue_item_at_index(-1)

    def get_playback_stats_snapshot(self):
        with self._queue_lock:
            return {
                "time": time(),
                "output_frames": self._output_frame_count,
                "reused_frames": self._reused_frame_count,
                "unique_frames": self._audio_frame_count,
                "queue_length": len(self._queue),
                "output_frame_count": self._output_frame_count,
                "audio_frame_count": self._audio_frame_count,
                "reused_frame_count": self._reused_frame_count,
            }

    def _silence_bytes(self, frame_count):
        return bytes(frame_count * 4)

    def _audio_bytes(self, audio, frame_count):
        import numpy as np

        if audio is None:
            return self._silence_bytes(frame_count)
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        output = samples[:frame_count].tobytes()
        return output + self._silence_bytes(max(0, frame_count - samples.size))

    def _audio_callback(self, in_data, frame_count, time_info, status):
        import pyaudio

        with self._queue_lock:
            packet = None
            audio = None
            if self._queue:
                packet = self._queue.popleft()
                audio = packet.get("audio")
                self._last_frame_info = packet
                self._audio_frame_count += 1
            elif self._last_frame_info is not None:
                packet = self._last_frame_info
                self._reused_frame_count += 1
        output = self._audio_bytes(audio, frame_count)
        if packet is not None:
            frame = packet.get("frame")
            if frame is not None:
                self._submit_video_frame(frame, packet.get("physical_index"))
        return output, pyaudio.paContinue

    def _submit_video_frame(self, frame, physical_index):
        try:
            output = _apply_kt_overlay(frame, physical_index)
        except Exception:
            output = frame
        self.player.add_frame(output)
        with self._queue_lock:
            self._output_frame_count += 1

    def _init_audio_stream(self):
        import pyaudio

        if self._stream is not None:
            return
        audio = pyaudio.PyAudio()
        try:
            rate = _resolve_output_sample_rate(audio, self.SAMPLE_RATE)
            samples_per_frame = max(1, rate // FPS)
            stream = audio.open(
                format=pyaudio.paFloat32, channels=1, rate=rate, output=True,
                frames_per_buffer=samples_per_frame,
                stream_callback=self._audio_callback, start=False,
            )
        except BaseException:
            audio.terminate()
            raise
        self.samples_per_frame = samples_per_frame
        self._audio_backend = audio
        self._stream = stream

    def _close_audio_stream(self):
        stream, self._stream = self._stream, None
        audio, self._audio_backend = self._audio_backend, None
        try:
            if stream is not None:
                try:
                    if stream.is_active():
                        stream.stop_stream()
                finally:
                    stream.close()
        finally:
            if audio is not None:
                audio.terminate()

    def _silent_mode_loop(self):
        from time import monotonic

        while not self._stop_event.is_set():
            deadline = monotonic() + 1 / FPS
            with self._queue_lock:
                packet = self._queue.popleft() if self._queue else None
            if packet is not None and packet.get("frame") is not None:
                self._submit_video_frame(packet["frame"], packet.get("physical_index"))
            self._stop_event.wait(max(0, deadline - monotonic()))

    def start_playing(self):
        if not self._playback_lock.acquire(blocking=False):
            return
        self._stop_event.clear()
        self.running = True
        if sys.platform == "win32":
            try:
                Thread(target=self._run_playback_owned, daemon=True).start()
            except BaseException:
                self._playback_lock.release()
                raise
        else:
            self._run_playback_owned()

    def _run_playback_owned(self):
        try:
            self._run_playback()
        finally:
            self._playback_lock.release()

    def _run_playback(self):
        if self._stop_event.is_set():
            return
        silent_worker = None
        try:
            try:
                self._init_audio_stream()
                if self._stop_event.is_set():
                    return
                self._stream.start_stream()
            except (ImportError, OSError):
                self._close_audio_stream()
                silent_worker = Thread(target=self._silent_mode_loop, daemon=True)
                silent_worker.start()
            if not self._stop_event.is_set():
                self.player.start_playback()
            if self.player._render_thread is not None:
                self.player._render_thread.join()
        finally:
            self.stop_playing()
            try:
                self._close_audio_stream()
            finally:
                if silent_worker is not None:
                    silent_worker.join()

    def stop_playing(self):
        self._stop_event.set()
        self.running = False
        self.player.stop_playback()
