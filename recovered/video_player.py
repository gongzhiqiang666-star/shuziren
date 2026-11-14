"""Recovered insert completion path for the video player."""


import json
import os
import shutil
import subprocess
import sys
from collections import deque
from contextlib import ExitStack, contextmanager
from fractions import Fraction
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread, current_thread
from time import sleep, time


DEFAULT_FPS = 25
AUDIO_SAMPLE_RATE = 44100
QUEUE_SIZE = 3
STREAM_QUEUE_SIZE = 180
STREAM_PREBUFFER_SECONDS = 2.0


def _bundled_media_candidates(name):
    executable = name + (".exe" if os.name == "nt" else "")
    module_path = Path(__file__).resolve()
    roots = [module_path.parent, module_path.parent.parent, Path(sys.executable).resolve().parent]
    if getattr(sys, "_MEIPASS", None):
        roots.insert(0, Path(sys._MEIPASS))
    relative_paths = (
        Path(executable), Path("bin") / executable, Path("ffmpeg") / "bin" / executable,
        Path("env") / "ffmpeg" / "bin" / executable,
        Path("env_50") / "ffmpeg" / "bin" / executable,
    )
    seen = set()
    for root in roots:
        for relative in relative_paths:
            candidate = (root / relative).resolve()
            if candidate not in seen:
                seen.add(candidate)
                yield candidate


def _resolve_media_executable(name):
    found = shutil.which(name) or shutil.which(name + ".exe")
    if found:
        return os.path.abspath(found)
    for candidate in _bundled_media_candidates(name):
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"未找到 {name} 可执行文件")


def _resolve_ffmpeg_executable() -> str:
    return _resolve_media_executable("ffmpeg")


def _resolve_ffprobe_executable() -> str:
    return _resolve_media_executable("ffprobe")


def _parse_fps_value(value) -> float:
    try:
        if value is None:
            return float(DEFAULT_FPS)
        text = str(value).strip()
        if not text or text.lower() in {"n/a", "nan", "none", "0/0"}:
            return float(DEFAULT_FPS)
        rate = float(Fraction(text))
        return rate if rate > 0 else float(DEFAULT_FPS)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return float(DEFAULT_FPS)


def _resolve_output_sample_rate(py_audio) -> int:
    return _pick_sample_rate(py_audio)


def _drain_process_pipe(pipe, prefix):
    if pipe is None:
        return
    try:
        for line in iter(pipe.readline, b""):
            if not line:
                break
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            text = str(line).rstrip()
            if text:
                print(f"{prefix}{text}")
    except (OSError, ValueError):
        return
    finally:
        try:
            pipe.close()
        except (OSError, ValueError):
            pass


def _close_stream_process(process, stderr_thread):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
    if stderr_thread is not None and stderr_thread is not current_thread():
        stderr_thread.join(timeout=1)


def _finish_insert(self):
    return _finish_insert_if(self, None)


def _finish_insert_if(self, expected_worker):
    with self._switch_lock:
        if expected_worker is not None and self._insert_worker is not expected_worker:
            return
        self._insert_worker = None
        if self._main_worker is not None:
            self._main_worker.resume()
            if self._main_worker.is_stream_source:
                self._main_worker.wait_until_ready(
                    timeout_seconds=STREAM_PREBUFFER_SECONDS + 2.0,
                    min_packets=self._stream_prebuffer_packets(),
                )


def _stream_prebuffer_packets(self):
    fps = self.fps if self.fps > 1 else 1
    return max(1, int(fps * STREAM_PREBUFFER_SECONDS) // 2)


def _get_active_worker(self):
    with self._switch_lock:
        if self._insert_worker is not None:
            return self._insert_worker, "insert"
        return self._main_worker, "main"


_EOF = object()


def _pick_sample_rate(pa):
    import pyaudio

    device = pa.get_default_output_device_info()
    default_rate = int(device["defaultSampleRate"])
    candidates = [48000, 44100, 32000]
    if default_rate > 0:
        candidates.insert(0, default_rate)
    for rate in dict.fromkeys(candidates):
        try:
            if pa.is_format_supported(
                rate, output_device=device["index"],
                output_channels=1, output_format=pyaudio.paFloat32,
            ):
                return rate
        except ValueError:
            continue
    return AUDIO_SAMPLE_RATE


class _AudioOutput:
    """Play the decoder's mono float32 PCM packets through PortAudio."""

    def __init__(self):
        import pyaudio

        self._audio = pyaudio.PyAudio()
        try:
            self.sample_rate = _resolve_output_sample_rate(self._audio)
            self._stream = self._audio.open(
                format=pyaudio.paFloat32, channels=1, rate=self.sample_rate,
                output=True,
            )
        except Exception:
            self._audio.terminate()
            raise

    def play(self, audio_bytes):
        self._stream.write(audio_bytes)

    def close(self):
        try:
            self._stream.close()
        finally:
            self._audio.terminate()


class _WindowOutput:
    """OpenCV window backend for decoded BGR frames."""

    def __init__(self, width, height):
        import cv2

        self._cv2 = cv2
        self.window_name = "Video Player"
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        try:
            cv2.resizeWindow(self.window_name, width, height)
        except Exception:
            self.close()
            raise

    def render(self, frame):
        self._cv2.imshow(self.window_name, frame)
        return self._cv2.waitKey(1) != 27

    def close(self):
        self._cv2.destroyWindow(self.window_name)


class _VirtualCamOutput:
    """Send decoded BGR frames to a virtual camera as RGB."""

    def __init__(self, width, height, fps):
        import cv2
        import pyvirtualcam

        self._cv2 = cv2
        self._size = (width, height)
        if sys.platform == "win32":
            from .virtual_cam import ensure_virtual_cam

            ensure_virtual_cam()
        self._camera = pyvirtualcam.Camera(width=width, height=height, fps=fps)

    def render(self, frame):
        if frame.shape[:2] != self._size[::-1]:
            frame = self._cv2.resize(frame, self._size)
        self._camera.send(self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB))
        return True

    def close(self):
        self._camera.close()


class Player:
    """Recovered source switching and EOF dispatch."""

    def __init__(self, width=720, height=1280, output_mode="window",
                 frame_processor=None):
        from threading import Lock

        self.fps = DEFAULT_FPS
        self.width = width
        self.height = height
        self.output_mode = output_mode
        self._frame_processor = frame_processor
        self._switch_lock = Lock()
        self._main_worker = None
        self._insert_worker = None

        self._output = None
        self._audio_output = None
        self._stop_event = Event()
        self._play_thread = None

    _get_active_worker = _get_active_worker
    _finish_insert = _finish_insert
    _stream_prebuffer_packets = _stream_prebuffer_packets

    def start(self, source, loop: bool = True):
        """Start decoding and playing the main source."""
        self.stop()
        audio = None
        try:
            with self._switch_lock:
                self._stop_event.clear()
                self.fps = _probe_fps(source)
                if self.output_mode == "window" and self._audio_output is None:
                    audio = _AudioOutput()
                    self._audio_output = audio
                self._main_worker = _SourceWorker(
                    source, loop, frame_processor=self._frame_processor,
                    audio_sample_rate=getattr(self._audio_output, "sample_rate", AUDIO_SAMPLE_RATE),
                )
                self._main_worker.start()
                self._main_worker.wait_until_ready(timeout_seconds=0.75)
                if self._main_worker.last_error:
                    raise RuntimeError(
                        f"视频源解码失败: {self._main_worker.last_error}"
                    )
                if self._main_worker.finished and not self._main_worker.has_media_packets():
                    raise RuntimeError("视频源没有可播放画面")
                thread = Thread(target=self._run_playback, args=(audio,), daemon=True)
                thread.start()
                self._play_thread = thread
        except Exception:
            try:
                self.stop()
            finally:
                if audio is not None:
                    self._audio_output = None
                    audio.close()
            raise

    def insert_video(self, video_path: str):
        """Pause the main source while a one-shot insert is decoded."""
        with self._switch_lock:
            if self._main_worker is None:
                raise RuntimeError("The main playback source has not been started")
            worker = _SourceWorker(
                video_path, False, frame_processor=self._frame_processor,
                audio_sample_rate=getattr(self._audio_output, "sample_rate", AUDIO_SAMPLE_RATE),
            )
            worker.start()
            try:
                self._main_worker.pause()
                if self._insert_worker is not None:
                    self._insert_worker.stop()
            except Exception:
                worker.stop()
                if self._insert_worker is None:
                    self._main_worker.resume()
                raise
            self._insert_worker = worker

    def stop(self):
        self._stop_event.set()
        with self._switch_lock:
            insert, main = self._insert_worker, self._main_worker
            self._insert_worker = self._main_worker = None
            play_thread = self._play_thread
            self._play_thread = None
            had_session = insert is not None or main is not None or play_thread is not None
        try:
            if insert is not None:
                insert.stop()
        finally:
            if main is not None:
                main.stop()
            if play_thread is not None and play_thread is not current_thread():
                play_thread.join()
        if had_session:
            self._stop_frame_processor()

    def _stop_frame_processor(self):
        if self._frame_processor is not None:
            stop_processor = getattr(self._frame_processor, "stop", None)
            if callable(stop_processor): stop_processor()

    def _close_outputs(self):
        output,self._output=self._output,None
        audio,self._audio_output=self._audio_output,None
        try:
            if output is not None: output.close()
        finally:
            if audio is not None: audio.close()

    def _run_playback(self, audio=None):
        output = None
        try:
            if self._output is None:
                if self.output_mode == "window":
                    output = _WindowOutput(self.width, self.height)
                elif self.output_mode in ("vcam", "camera"):
                    output = _VirtualCamOutput(self.width, self.height, self.fps)
                self._output = output
            self._play_loop()
        finally:
            self._close_outputs()

    def _play_loop(self):
        """Consume packets from the active source until EOF or stop."""
        clock_origin = None
        previous_worker = None
        while not self._stop_event.is_set():
            active = self._get_active_worker()
            worker, _ = active
            if worker is None:
                return
            if worker is not previous_worker:
                clock_origin = None
                previous_worker = worker
            packet = self._read_active_packet(active)
            if packet is _EOF:
                return
            if packet is None:
                self._stop_event.wait(0.01)
                continue
            clock_origin, keep_playing = self._play_timed_packet(
                packet, clock_origin, self._stop_event
            )
            if not keep_playing:
                return

    def _play_timed_packet(self, packet, clock_origin, stop_event):
        """Play one packet and return the clock origin and continuation flag."""
        pts = float(packet["pts"])
        if clock_origin is None:
            clock_origin = (time(), pts)
        else:
            wall_start, pts_start = clock_origin
            remaining = wall_start + max(0.0, pts - pts_start) - time()
            while remaining > 0 and not stop_event.is_set():
                sleep(0.05)
                remaining -= 0.05
        return clock_origin, self._dispatch_packet(packet)

    def _dispatch_packet(self, packet):
        """Render a decoded packet and return whether playback should continue."""
        if self._output is not None and not self._output.render(packet["frame"]):
            self.stop()
            return False
        if self._audio_output is not None:
            self._audio_output.play(packet["audio"])
        return True

    def _read_active_packet(self, active=None):
        """Read one packet from the active worker and handle insert EOF."""
        worker, source = self._get_active_worker() if active is None else active
        if worker is None:
            return None
        try:
            packet = worker.get()
        except Empty:
            return None
        if packet is _EOF and source == "insert":
            _finish_insert_if(self, worker)
            return None
        return packet


def _is_stream_source(source) -> bool:
    return isinstance(source, str) and "://" in source.strip().lower()


def _open_media_source(source: str):
    import av

    options = {}
    if _is_stream_source(source):
        options = {"rw_timeout": "15000000", "stimeout": "15000000"}
    return av.open(source, options=options)


def _probe_stream_fps(source: str) -> float:
    result = subprocess.run(
        [
            _resolve_ffprobe_executable(), "-v", "error", "-rw_timeout", "15000000",
            "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate,r_frame_rate",
            "-of", "json", source,
        ],
        capture_output=True,
        check=True,
        timeout=15,
    )
    for stream in json.loads(result.stdout).get("streams", []):
        for key in ("avg_frame_rate", "r_frame_rate"):
            try:
                rate = _parse_fps_value(stream.get(key))
            except (TypeError, ValueError):
                continue
            if rate != float(DEFAULT_FPS) or str(stream.get(key, "")).strip() in {str(DEFAULT_FPS), f"{DEFAULT_FPS}/1"}:
                return rate
    return float(DEFAULT_FPS)


def _probe_fps(source) -> float:
    try:
        if _is_stream_source(source):
            return _probe_stream_fps(source)
        with _open_media_source(source) as container:
            return float(container.streams.video[0].average_rate or DEFAULT_FPS)
    except Exception:
        return float(DEFAULT_FPS)


@contextmanager
def _open_stream_source_via_ffmpeg(source: str, audio_sample_rate: int):
    import av

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    process = subprocess.Popen(
        [
            _resolve_ffmpeg_executable(), "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats",
            "-rw_timeout", "15000000", "-fflags", "+genpts",
            "-i", source, "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "rawvideo", "-pix_fmt", "bgr24",
            "-c:a", "pcm_f32le", "-ac", "1", "-ar", str(audio_sample_rate),
            "-f", "nut", "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
    )
    stderr_thread = Thread(target=_drain_process_pipe, args=(process.stderr, "[video_player.ffmpeg] "), daemon=True)
    stderr_thread.start()
    try:
        with process.stdout, av.open(process.stdout, format="nut") as container:
            yield container
    finally:
        _close_stream_process(process, stderr_thread)


def _take_audio_chunk(audio_buffer, sample_count: int) -> bytes:
    import numpy as np

    if sample_count <= 0:
        return b""
    samples = np.zeros(sample_count, dtype=np.float32)
    for index in range(min(sample_count, len(audio_buffer))):
        samples[index] = audio_buffer.popleft()
    np.clip(samples, -1.0, 1.0, out=samples)
    return samples.tobytes()


class _SourceWorker:
    """Recovered queue interface for a playback source."""

    def __init__(self, source, loop: bool, frame_processor=None, audio_sample_rate: int = AUDIO_SAMPLE_RATE):
        self._packet_iterator = _iter_packets
        self.source = source
        self.loop = loop
        self.frame_processor = frame_processor
        self.audio_sample_rate = audio_sample_rate
        self.is_stream_source = _is_stream_source(source)
        self.queue = Queue(maxsize=STREAM_QUEUE_SIZE if self.is_stream_source else QUEUE_SIZE)
        self.stop_event = Event()
        self.pause_event = Event()
        self.discard_event = Event()
        self.thread = None
        self.finished = False
        self.last_error = ""
        self._frame_processor_failed = False
        self.keep_warm_when_paused = self.is_stream_source

    @classmethod
    def _from_packet_iterator(cls,source,loop,packet_iterator,frame_processor=None,audio_sample_rate=AUDIO_SAMPLE_RATE):
        instance=cls(source,loop,frame_processor,audio_sample_rate); instance._packet_iterator=packet_iterator; return instance

    def get(self, timeout: float = 0.1):
        return self.queue.get(timeout=timeout)

    def _clear_queue(self):
        with self.queue.mutex:
            self.queue.queue.clear()

    def pause(self):
        if self.keep_warm_when_paused:
            self._clear_queue()
            self.discard_event.set()
        else:
            self.pause_event.set()

    def resume(self):
        self.pause_event.clear()
        self.discard_event.clear()

    def start(self):
        self.thread = Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.pause_event.clear()
        self.discard_event.set()
        self._clear_queue()
        try:
            self.queue.put_nowait(_EOF)
        except Exception:
            pass

        if self.thread is not None and self.thread.is_alive() and self.thread is not current_thread():
            self.thread.join(timeout=1)
        self.thread = None

    def wait_until_ready(self, timeout_seconds: float = 0.5, min_packets: int = 1):
        deadline = time() + timeout_seconds
        min_packets = max(1, min_packets)
        while time() < deadline and not self.stop_event.is_set():
            if self.queue.qsize() >= min_packets or self.finished:
                return
            sleep(0.01)

    def has_media_packets(self):
        with self.queue.mutex:
            return any(item is not _EOF for item in self.queue.queue)

    def _apply_frame_processor(self, item):
        if self.frame_processor is None or self._frame_processor_failed:
            return item
        try:
            return self.frame_processor.process(item)
        except Exception:
            self._frame_processor_failed = True
            return item

    def _enqueue_packet(self, packet):
        """Retry a pending packet until accepted, stopped, or discarded."""
        while not self.stop_event.is_set() and not self.discard_event.is_set():
            try:
                self.queue.put(packet, timeout=0.1)
            except Exception:
                continue
            return

    def _run(self):
        try:
            for packet in self._packet_iterator(
                self.source, self.loop, self.stop_event, self.pause_event, self.audio_sample_rate
            ):
                if self.stop_event.is_set():
                    break
                self._enqueue_packet(self._apply_frame_processor(packet))
        except Exception as error:
            self.last_error = str(error) or error.__class__.__name__
        finally:
            self.finished = True
            if not self.stop_event.is_set():
                try:
                    self.queue.put(_EOF, timeout=0.1)
                except Exception:
                    pass


def _ready_packets(video_buffer, audio_buffer, sample_rate, remainder=0.0, *, force=False):
    """Assemble decoded frames with their supplied presentation durations."""
    packets = []
    while video_buffer:
        frame, pts, duration = video_buffer[0]
        exact_count = duration * sample_rate + remainder
        sample_count = max(0, int(exact_count))
        if not force and len(audio_buffer) < sample_count:
            break
        video_buffer.popleft()
        packets.append({
            "frame": frame,
            "audio": _take_audio_chunk(audio_buffer, sample_count),
            "pts": float(pts),
        })
        remainder = exact_count - sample_count
    return packets, remainder


def _iter_packets(source, loop, stop_event, pause_event, audio_sample_rate=AUDIO_SAMPLE_RATE):
    import av

    while not stop_event.is_set():
        video_buffer, audio_buffer = deque(), deque()
        remainder = 0
        try:
            with ExitStack() as media:
                container = None
                if _is_stream_source(source):
                    try:
                        container = media.enter_context(
                            _open_stream_source_via_ffmpeg(source, audio_sample_rate)
                        )
                    except Exception:
                        pass
                if container is None:
                    container = media.enter_context(_open_media_source(source))
                video = container.streams.video[0]
                audio = next(iter(container.streams.audio), None)
                streams = [video] if audio is None else [video, audio]
                resampler = av.AudioResampler(format="flt", layout="mono", rate=audio_sample_rate)
                duration = 1 / Fraction(video.average_rate or DEFAULT_FPS)
                pending = None
                pending_duration = duration
                for frame in container.decode(*streams):
                    while pause_event.is_set() and not stop_event.wait(0.01):
                        pass
                    if stop_event.is_set():
                        return
                    if isinstance(frame, av.AudioFrame):
                        for samples in resampler.resample(frame):
                            audio_buffer.extend(samples.to_ndarray().ravel())
                    else:
                        pts = frame.pts * frame.time_base if frame.pts is not None and frame.time_base is not None else None
                        if pts is None:
                            pts = 0 if pending is None else pending[1] + duration
                        if pending is not None:
                            video_buffer.append((*pending, max(0, pts - pending[1]) or duration))
                        pending = (frame.to_ndarray(format="bgr24"), pts)
                        pending_duration = (frame.duration * frame.time_base
                                            if frame.duration and frame.time_base else duration)
                    packets, remainder = _ready_packets(
                        video_buffer, audio_buffer, audio_sample_rate, remainder, force=audio is None
                    )
                    yield from packets

                if audio is not None:
                    for samples in resampler.resample(None):
                        audio_buffer.extend(samples.to_ndarray().ravel())
                if pending is None:
                    return
                video_buffer.append((*pending, pending_duration))
                packets, _ = _ready_packets(video_buffer, audio_buffer, audio_sample_rate, remainder, force=True)
                yield from packets
        except Exception:
            if not loop or stop_event.is_set():
                raise
            if not _is_stream_source(source):
                raise
            sleep(0.5)
        if not loop:
            return
