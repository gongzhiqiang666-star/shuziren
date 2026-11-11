"""Audio gain calculation recovered from image_infer_v2."""


from __future__ import annotations
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import sleep, time

import numpy as np


@dataclass
class AudioBatch:
    audio_chunk: np.ndarray
    original_audio_chunk: np.ndarray | None
    audio_path: str | None
    target_face_index: int
    queue_name: str
    wenet_feature: np.ndarray | None = None


def fade_out_gain_curve(fade_out_total: int, fade_frame_index: int, samples: int) -> np.ndarray:
    total = max(1, int(fade_out_total))
    index = max(0, min(total - 1, int(fade_frame_index)))
    start_gain = 1.0 - index / total
    end_gain = 1.0 - (index + 1) / total
    return np.linspace(start_gain, end_gain, samples, dtype=np.float32)


def fade_in_gain_curve(fade_in_total: int, fade_frame_index: int, samples: int) -> np.ndarray:
    total = max(1, int(fade_in_total))
    index = max(0, min(total - 1, int(fade_frame_index)))
    return np.linspace(index / total, (index + 1) / total, samples, dtype=np.float32)


def apply_playback_gain(audio_batch, curve_fn, start_index: int, frame_count: int) -> None:
    for offset, batch in enumerate(audio_batch[:frame_count]):
        samples = batch.original_audio_chunk
        if samples is None or len(samples) == 0:
            continue
        gains = curve_fn(start_index + offset, len(samples))
        batch.original_audio_chunk = (samples * gains).astype(np.float32, copy=False)


def make_silence_audio_batches(
    count: int,
    samples_per_frame: int,
    output_samples_per_frame: int,
    silence_wenet_features: np.ndarray | None = None,
) -> list[AudioBatch]:
    if count <= 0:
        return []

    audio_chunk = np.zeros(samples_per_frame, dtype=np.float32)
    original_audio_chunk = np.zeros(output_samples_per_frame, dtype=np.float32)
    features = [] if silence_wenet_features is None else list(silence_wenet_features[:count])
    if len(features) < count:
        zero_feature = np.zeros((20, 256), dtype=np.float32)
        features.extend([zero_feature] * (count - len(features)))
    return [
        AudioBatch(
            audio_chunk=audio_chunk,
            original_audio_chunk=original_audio_chunk,
            audio_path="<padding_silence>",
            target_face_index=0,
            queue_name="silence",
            wenet_feature=wenet_feature,
        )
        for wenet_feature in features
    ]


def batch_primary_queue(audio_batch: list[AudioBatch]) -> str:
    for batch in audio_batch:
        if (
            batch.queue_name in ("normal", "danmu")
            and not str(batch.audio_path or "").startswith("<")
        ):
            return batch.queue_name
    return "silence"


def peek_preferred_queue(
    audio_queues,
    queue_priority=("danmu", "normal"),
    current_audio_path: str | None = None,
    queue_interrupt_mode: bool = False,
) -> str | None:
    if not queue_interrupt_mode and current_audio_path == "<stable_silence>":
        for name, queue in audio_queues.items():
            if not queue.empty() and any(
                batch.audio_path == current_audio_path for batch in queue.queue
            ):
                return name
    for name in queue_priority:
        if not audio_queues[name].empty():
            return name
    return None


def pull_normal_for_fade_out(
    audio_queues,
    count: int,
    initial_path: str | None,
    samples_per_frame: int,
    output_samples_per_frame: int,
    silence_wenet_features: np.ndarray | None = None,
) -> tuple[list[AudioBatch], str | None]:
    normal_queue = audio_queues["normal"]
    batches: list[AudioBatch] = []
    path = initial_path
    while len(batches) < count and not normal_queue.empty():
        batch = normal_queue.get()
        batches.append(batch)
        path = batch.audio_path

    if len(batches) >= count:
        return batches, path

    batches.extend(
        make_silence_audio_batches(
            count - len(batches),
            samples_per_frame,
            output_samples_per_frame,
            silence_wenet_features,
        )
    )
    if not any(
        batch.queue_name == "normal"
        and not str(batch.audio_path or "").startswith("<")
        for batch in batches
    ):
        path = initial_path
    return batches, path


def finish_normal_fade_out_batch(manager, batches: list[AudioBatch], count: int) -> None:
    """Prepare the selected fade-out batch for synthesis and advance its state."""
    if batches:
        batches.extend(
            manager._make_silence_audio_batches(manager.synthesizer.batch_size - len(batches))
        )

    total = manager._fade_out_total
    remaining = manager._fade_out_remaining
    apply_playback_gain(
        batches,
        lambda index, samples: fade_out_gain_curve(total, index, samples),
        total - remaining,
        count,
    )
    manager._fade_out_remaining -= count
    manager._last_real_queue = "normal"
    if manager._fade_out_remaining <= 0:
        manager._fade_out_remaining = 0
        manager._speech_av_mode = "danmu"


def process_normal_fade_out_batch(
    manager, initial_path: str | None
) -> tuple[list[AudioBatch], str | None]:
    """Run one batch after the inference loop selects normal audio fade-out."""
    count = min(manager._fade_out_remaining, manager.synthesizer.batch_size)
    batches, path = pull_normal_for_fade_out(
        manager.audio_queues,
        count,
        initial_path,
        manager.samples_per_frame,
        manager.output_samples_per_frame,
        manager.silence_wenet_features,
    )
    finish_normal_fade_out_batch(manager, batches, count)
    return batches, path


def collect_synthesis_inputs(manager, audio_batches: list[AudioBatch], frame_objects):
    """Collect the feature, image, and resolved face metadata columns."""
    features = [batch.wenet_feature for batch in audio_batches]
    images = [frame.image for frame in frame_objects]
    metadata = [
        resolve_face_metadata_for_synthesis(manager, frame.metadata, batch.target_face_index)
        for batch, frame in zip(audio_batches, frame_objects)
    ]
    return features, images, metadata


def synthesize_audio_batch(manager, audio_batches: list[AudioBatch], frame_objects):
    """Run the v2 synthesis call after preparing its three input columns."""
    features, images, metadata = collect_synthesis_inputs(manager, audio_batches, frame_objects)
    started_at = time()
    result = manager.synthesizer.synthesize_batch(
        batch_audio_features=features,
        batch_images=images,
        batch_frame_data=metadata,
    )
    elapsed = time() - started_at
    manager.total_synthesis_time += elapsed
    return result, elapsed


def upload_synthesized_frame(
    player, frame, index, frame_object, audio_batch: AudioBatch, audio
) -> None:
    """Submit one synthesized frame with its original audio and frame metadata."""
    player.upload_frame(
        {
            "frame": frame,
            "index": index,
            "audio": audio,
            "physical_index": frame_object.physical_index,
            "audio_path": audio_batch.audio_path,
            "audio_queue": audio_batch.queue_name,
        }
    )


def process_audio_batch(manager, audio_batches: list[AudioBatch], frame_objects, start_index: int):
    """Synthesize one batch and submit its frames in output order."""
    frames, elapsed = synthesize_audio_batch(manager, audio_batches, frame_objects)
    for offset, frame in enumerate(frames):
        if offset < len(audio_batches):
            audio = audio_batches[offset].original_audio_chunk
        else:
            audio = np.zeros_like(audio_batches[0].original_audio_chunk)
        upload_synthesized_frame(
            manager.player,
            frame,
            start_index + offset,
            frame_objects[offset],
            audio_batches[offset],
            audio,
        )
    return len(frames), elapsed


def next_batch_start_index(manager, current_index: int) -> int | None:
    """Return the starting index, or None when the player buffer is full."""
    queue_length = manager.player.get_queue_length()
    if queue_length >= manager.buffer_threshold:
        return None
    if queue_length > 0:
        return manager.player.get_last_queue_item()["index"] + 1
    return current_index


def read_preloaded_frame_batch(manager):
    """Read a complete synthesis batch, or discard it on queue timeout."""
    frames = []
    try:
        for _ in range(manager.synthesizer.batch_size):
            frames.append(manager.preloaded_frame_queue.get(timeout=5))
    except Empty:
        return None
    return frames


def run_preloaded_inference_iteration(manager, current_index: int, audio_path: str | None):
    """Run one recovered inference iteration and return its index, path and stop flag."""
    with manager.processing_lock:
        start_index = next_batch_start_index(manager, current_index)
        if start_index is not None:
            audio_batches, audio_path = get_next_audio_batch(manager, audio_path)
            read_started_at = time()
            if manager.input_mode in ("camera", "video", "rtmp"):
                frames = get_camera_frame_batch(manager, start_index)
            elif manager.preloaded_frame_queue is None:
                sleep(0.5)
                return start_index, audio_path, False
            else:
                frames = read_preloaded_frame_batch(manager)
                if frames is None:
                    return start_index, audio_path, not (manager.player and manager.player.running)

            read_elapsed = time() - read_started_at
            manager.total_read_time += read_elapsed
            frame_count, synthesis_elapsed = process_audio_batch(
                manager, audio_batches, frames, start_index
            )
            manager.batch_count += 1
            record_rate_stats(manager, frame_count, read_elapsed, synthesis_elapsed)
            return start_index, audio_path, False

    sleep(0.005)
    return current_index, audio_path, False


def run_preloaded_inference_loop(manager, audio_path: str | None = None) -> None:
    """Process audio with live or preloaded frames while playback is active."""
    current_index = 0
    while manager.player and manager.player.running:
        current_index, audio_path, should_stop = run_preloaded_inference_iteration(
            manager, current_index, audio_path
        )
        if should_stop:
            return


@dataclass
class FrameData:
    image: np.ndarray | None
    metadata: object
    physical_index: int


def extend_camera_buffer_from_history(manager, batch_size: int, start_index: int) -> None:
    """Fill a short camera buffer by cycling through the latest live batch."""
    buffer = manager.camera_frame_buffer
    if len(buffer) >= batch_size:
        return
    with manager.live_frame_lock:
        history = list(manager._last_live_frame_batch)

    if history:
        for offset in range(batch_size - len(buffer)):
            frame = history[offset % len(history)]
            buffer.append(FrameData(frame.image, frame.metadata, start_index + len(buffer)))
    else:
        missing = batch_size - len(buffer)
        if missing > 0:
            buffer.extend(create_dummy_frame_batch(manager)[:missing])


def take_camera_buffer_batch(manager, batch_size: int):
    """Take the leading frames and keep the remaining buffer for the next batch."""
    buffer = manager.camera_frame_buffer
    batch = buffer[:batch_size]
    manager.camera_frame_buffer = buffer[batch_size:]
    return batch


def get_camera_frame_batch(manager, start_index: int) -> list[FrameData]:
    """Read queued live frames, fill any shortfall, and take one synthesis batch."""
    batch_size = manager.synthesizer.batch_size
    buffer = manager.camera_frame_buffer
    queue = manager.live_frame_queue
    if queue is not None:
        while len(buffer) < batch_size:
            try:
                incoming = queue.get(timeout=0.0 if buffer else 0.04)
            except Empty:
                break
            if incoming:
                buffer.extend(incoming)
            if queue.empty():
                break

    extend_camera_buffer_from_history(manager, batch_size, start_index)
    return take_camera_buffer_batch(manager, batch_size)


def create_dummy_frame_batch(manager) -> list[FrameData]:
    """Create the shared black image and per-frame metadata for a dummy batch."""
    image = np.zeros((manager.window_height, manager.window_width, 3), dtype=np.uint8)
    return [
        FrameData(image, {"is_no_face": True}, 0)
        for _ in range(manager.synthesizer.batch_size)
    ]


def resolve_face_metadata_for_synthesis(manager, metadata, target_face_index: int) -> dict:
    """Select a usable face, then fall back to the frame-level metadata."""
    if not isinstance(metadata, dict):
        return {"is_no_face": True}

    faces = dict.get(metadata, "faces")
    if isinstance(faces, dict):
        faces = [faces]
    else:
        faces = faces or []

    candidates = []
    if 0 <= target_face_index < len(faces):
        candidates.append(target_face_index)
    if faces and 0 not in candidates:
        candidates.append(0)
    candidates.extend(index for index in range(len(faces)) if index not in candidates)

    for index in candidates:
        face = face_slot_from_detection(faces[index])
        if not face.get("is_no_face", False):
            return face

    if dict.get(metadata, "is_no_face", False) or not has_valid_bounding_box(metadata):
        return {"is_no_face": True}
    result = {"bounding_box": metadata["bounding_box"], "is_no_face": False}
    for field in ("landmarks", "full_mask"):
        if field in metadata:
            result[field] = metadata[field]
    return result


def has_valid_bounding_box(metadata: dict) -> bool:
    box = dict.get(metadata, "bounding_box")
    if box is None:
        return False
    first, second, third, fourth = box
    return bool(second - first > 0 and fourth - third > 0)


def face_slot_from_detection(detection) -> dict:
    if not isinstance(detection, dict) or dict.get(detection, "is_no_face", False):
        return {"is_no_face": True}
    if "bounding_box" not in detection:
        return {"is_no_face": True}

    result = {"is_no_face": False, "bounding_box": np.array(detection["bounding_box"])}
    if not has_valid_bounding_box(result):
        return {"is_no_face": True}
    for field in ("landmarks", "full_mask"):
        if field in detection:
            result[field] = detection[field]
    return result


def select_normal_fade_out_batch(
    manager, initial_path: str | None, preferred_queue: str | None
) -> tuple[list[AudioBatch], str | None] | None:
    """Handle an active fade-out, or let the caller continue regular selection."""
    if manager._speech_av_mode != "fading_out":
        return None
    if preferred_queue != "danmu" and manager.audio_queues["danmu"].empty():
        manager._speech_av_mode = "normal"
    elif manager.audio_queues["normal"].empty():
        manager._speech_av_mode = "danmu"
    else:
        return process_normal_fade_out_batch(manager, initial_path)

    manager._fade_out_remaining = 0
    manager._fade_out_total = 0
    return None


def pull_selected_audio_batch(manager, queue_name: str | None, initial_path: str | None):
    """Drain the chosen queue up to the synthesis batch size and pad the shortfall."""
    batch_size = manager.synthesizer.batch_size
    batches = []
    if queue_name:
        queue = manager.audio_queues[queue_name]
        while len(batches) < batch_size and not queue.empty():
            batches.append(queue.get())

    path = batches[-1].audio_path if batches else initial_path
    if path is not None and type(path) is not str:
        raise TypeError("audio_path must be str or None")

    missing = batch_size - len(batches)
    if missing > 0:
        batches.extend(manager._make_silence_audio_batches(missing))

    primary_queue = batch_primary_queue(batches)
    if primary_queue == "danmu":
        manager._speech_av_mode = "danmu"
        manager._last_real_queue = "danmu"
        manager._fade_in_remaining = 0
    elif primary_queue == "normal":
        if manager._speech_av_mode == "danmu" or manager._pending_fade_in:
            if manager.idle_fade_in_frames > 0 and not manager.pause_event.is_set():
                manager._fade_in_total = manager.idle_fade_in_frames
                manager._fade_in_remaining = manager.idle_fade_in_frames
                print(f"\n[Speech] 回话术音频渐强 ({manager.idle_fade_in_frames}帧)")
            manager._pending_fade_in = False
        manager._speech_av_mode = "normal"
        manager._last_real_queue = "normal"
    else:
        if manager._speech_av_mode == "danmu":
            manager._pending_fade_in = True
            manager._speech_av_mode = "normal"
        manager._last_real_queue = "silence"

    if manager._fade_in_remaining > 0 and primary_queue == "normal":
        count = min(batch_size, manager._fade_in_remaining)
        start = manager._fade_in_total - manager._fade_in_remaining
        apply_playback_gain(
            batches,
            lambda index, samples: fade_in_gain_curve(
                manager._fade_in_total, index, samples
            ),
            start,
            count,
        )
        manager._fade_in_remaining -= count

    return batches, path


def pull_priority_audio_batch(
    manager, current_path: str | None, interrupted_or_paused: bool
) -> tuple[list[AudioBatch], str | None]:
    """Select and pull a batch after the scheduler reaches queue selection."""
    name = manager._peek_preferred_queue(current_path, interrupted_or_paused)
    return pull_selected_audio_batch(manager, name, current_path)


def pull_audio_batch_after_mode_update(
    manager,
    current_path: str | None,
    preferred_queue: str | None,
    interrupted_or_paused: bool,
) -> tuple[list[AudioBatch], str | None]:
    """Dispatch a batch once the scheduler has updated its speech mode."""
    if manager._speech_av_mode == "fading_out":
        if preferred_queue != "danmu" and manager.audio_queues["danmu"].empty():
            manager._speech_av_mode = "normal"
        elif manager.audio_queues["normal"].empty():
            manager._speech_av_mode = "danmu"
        else:
            return process_normal_fade_out_batch(manager, current_path)

        manager._fade_out_remaining = 0
        manager._fade_out_total = 0

    return pull_priority_audio_batch(manager, current_path, interrupted_or_paused)


def get_next_audio_batch(
    manager, current_path: str | None
) -> tuple[list[AudioBatch], str | None]:
    """Run the recovered speech mode and queue dispatch for one batch."""
    interrupted_or_paused = manager.is_interrupt or manager.pause_event.is_set()
    preferred_queue = manager._peek_preferred_queue(None, False)

    if (
        manager._speech_av_mode == "normal"
        and preferred_queue == "danmu"
        and manager._last_real_queue == "normal"
        and manager.is_interrupt
        and not manager.pause_event.is_set()
        and manager.idle_fade_out_frames > 0
    ):
        manager._speech_av_mode = "fading_out"
        manager._fade_out_total = manager.idle_fade_out_frames
        manager._fade_out_remaining = manager.idle_fade_out_frames
        print(f"\n[Speech] 话术音频渐弱 ({manager.idle_fade_out_frames}帧)")

    return pull_audio_batch_after_mode_update(
        manager, current_path, preferred_queue, interrupted_or_paused
    )


def publish_live_frame_batch(manager, frames, detections) -> None:
    """Build, count, cache, and enqueue one live worker batch."""
    frame_batch = manager._build_live_frame_batch(frames, detections)
    manager._rate_log_driving_frames += len(frame_batch)
    with manager.live_frame_lock:
        manager._last_live_frame_batch = frame_batch

    queue = manager.live_frame_queue
    if queue.full():
        try:
            queue.get_nowait()
        except Empty:
            pass

    try:
        queue.put_nowait(frame_batch)
    except Exception:
        pass


def run_live_frame_worker(manager) -> None:
    """Read and publish live batches until stopped or the input ends."""
    stop_event = manager.live_frame_stop_event
    while stop_event and not stop_event.is_set():
        if not manager.face_reader_iterator:
            sleep(0.02)
            continue

        try:
            frames, detections = next(manager.face_reader_iterator)
            if stop_event.is_set():
                break
            publish_live_frame_batch(manager, frames, detections)
        except StopIteration:
            if stop_event.is_set():
                break
            if manager.input_mode == "rtmp" and manager.face_reader:
                reader = manager.face_reader
                for _ in range(3):
                    if stop_event.wait(.5):
                        break
                    try:
                        reader.reconnect(stop_event)
                    except (OSError, RuntimeError, ValueError, TimeoutError):
                        continue
                    if not stop_event.is_set():
                        manager.face_reader_iterator = iter(reader)
                    break
                else:
                    print("RTMP 输入重连失败。")
                    break
                continue
            if (
                manager.input_mode == "video"
                and manager.face_reader
                and hasattr(manager.face_reader, "rewind")
            ):
                manager.face_reader.rewind()
                manager.face_reader_iterator = iter(manager.face_reader)
                continue
            print("实时帧数据流结束。")
            break

        except Exception as exc:
            print(f"实时帧流水线异常: {exc}")
            sleep(0.05)

    print("实时帧流水线已停止。")


def stop_live_frame_pipeline(manager) -> None:
    if manager.live_frame_stop_event:
        manager.live_frame_stop_event.set()
    if manager.live_frame_thread and manager.live_frame_thread.is_alive():
        manager.live_frame_thread.join(timeout=2)
        if manager.live_frame_thread.is_alive():
            print("警告：实时帧流水线线程未能正常停止。")

    manager.live_frame_thread = None
    manager.live_frame_stop_event = None
    manager.live_frame_queue = None
    manager.camera_frame_buffer = []


def start_live_frame_pipeline(manager) -> None:
    stop_live_frame_pipeline(manager)
    manager.live_frame_queue = Queue(maxsize=4)
    manager.live_frame_stop_event = Event()
    manager._last_live_frame_batch = []
    manager._live_frame_physical_index = 0
    manager.live_frame_thread = Thread(
        target=run_live_frame_worker,
        args=(manager,),
        daemon=True,
        name="live-frame-pipeline",
    )
    manager.live_frame_thread.start()
    print("实时帧流水线已启动。")


def stop_playing(manager) -> None:
    """Stop playback, capture, and preloading, then discard queued audio."""
    if manager.player:
        manager.player.stop_playing()
        manager.player = None

    if manager.live_frame_stop_event:
        manager.live_frame_stop_event.set()
    if manager.face_reader:
        manager.face_reader.stop_capture()
        manager.face_reader = None
    stop_live_frame_pipeline(manager)
    manager.face_reader_iterator = None

    if manager.preload_stop_event:
        manager.preload_stop_event.set()
    if manager.preload_thread and manager.preload_thread.is_alive():
        manager.preload_thread.join(timeout=2)
    manager.preload_thread = None

    for audio_queue in manager.audio_queues.values():
        audio_queue.queue.clear()


def sample_playback_rates(manager) -> tuple[float, float]:
    """Sample output and reused frames per second and advance the baseline."""
    snapshot = manager.player.get_playback_stats_snapshot()
    previous = manager._last_playback_stats or {
        "time": manager._rate_log_started_at,
        "output_frames": 0,
        "reused_frames": 0,
    }
    elapsed = max(snapshot["time"] - previous["time"], 0.001)
    output_frames = max(snapshot["output_frames"] - previous.get("output_frames", 0), 0)
    reused_frames = max(snapshot["reused_frames"] - previous.get("reused_frames", 0), 0)
    manager._last_playback_stats = snapshot
    return output_frames / elapsed, reused_frames / elapsed


def record_rate_stats(manager, frame_count: int, read_elapsed: float, synthesis_elapsed: float) -> None:
    now = time()
    if manager._rate_log_started_at is None:
        manager._rate_log_started_at = now

    manager._rate_log_frames += max(0, frame_count)
    manager._rate_log_read_time += max(0.0, read_elapsed)
    manager._rate_log_synthesis_time += max(0.0, synthesis_elapsed)
    elapsed = now - manager._rate_log_started_at
    if elapsed < manager.rate_log_interval:
        return

    frames = manager._rate_log_frames
    read_time = manager._rate_log_read_time
    synthesis_time = manager._rate_log_synthesis_time
    process_time = read_time + synthesis_time
    generated_fps = frames / elapsed if elapsed > 0 else 0.0
    synthesis_fps = frames / synthesis_time if synthesis_time > 0 else 0.0
    process_fps = frames / process_time if process_time > 0 else 0.0
    driving_fps = manager._rate_log_driving_frames / elapsed if elapsed > 0 else 0.0
    output_queue_length = manager.player.get_queue_length() if manager.player else 0
    driving_queue_length = manager.live_frame_queue.qsize() if manager.live_frame_queue else 0
    divisor = max(frames, 1)
    playback = ""
    if manager.player and hasattr(manager.player, "get_playback_stats_snapshot"):
        output_fps, reused_fps = sample_playback_rates(manager)
        playback = f"，播放{output_fps:.1f}帧/秒，复用{reused_fps:.1f}帧/秒"
    message = (
        f"[直播帧率] 近{elapsed:.1f}秒：合成速度{synthesis_fps:.1f}FPS"
        f"({synthesis_fps / 25.0:.2f}x实时)，总处理{process_fps:.1f}FPS，"
        f"按需生成{generated_fps:.1f}帧/秒{playback}，"
        f"驱动{driving_fps:.1f}帧/秒，输出队列{output_queue_length}，"
        f"驱动队列{driving_queue_length}，读帧{read_time / divisor * 1000:.1f}ms/帧，"
        f"合成{synthesis_time / divisor * 1000:.1f}ms/帧"
    )
    print(message + "。")

    manager._rate_log_started_at = now
    manager._rate_log_frames = 0
    manager._rate_log_read_time = 0.0
    manager._rate_log_synthesis_time = 0.0
    manager._rate_log_driving_frames = 0


def initialize_playback_stats(manager) -> None:
    """Reset session totals and the rolling rate window before playback."""
    manager.stats_start_time = time()
    manager.batch_count = 0
    manager.total_read_time = 0.0
    manager.total_synthesis_time = 0.0
    manager.total_frames_processed = 0
    manager._rate_log_started_at = time()
    manager._rate_log_frames = 0
    manager._rate_log_read_time = 0.0
    manager._rate_log_synthesis_time = 0.0
    manager._rate_log_driving_frames = 0
    manager._last_playback_stats = None


def start_camera_capture(manager) -> None:
    """Initialize the configured camera reader and its frame iterator."""
    try:
        manager.face_reader.start_capture(manager.camera_index, manager.camera_resolution)
        manager.face_reader_iterator = iter(manager.face_reader)
    except Exception as exc:
        print(f"启动摄像头失败: {exc}")
        raise RuntimeError(f"摄像头启动失败: {exc}") from exc


def start_video_capture(manager) -> None:
    """Initialize the configured video reader, allowing playback on failure."""
    if not manager.face_reader:
        return

    try:
        manager.face_reader.start_capture(manager.video_path_for_driving)
        manager.face_reader_iterator = iter(manager.face_reader)
    except Exception as exc:
        print(f"启动视频驱动失败: {exc}")
        manager.face_reader = None


def start_rtmp_capture(manager) -> None:
    """Start RTMP capture and use the dimensions reported by the reader."""
    if not manager.face_reader:
        return

    try:
        manager.face_reader.start_capture(manager.rtmp_url_for_driving)
        manager.face_reader_iterator = iter(manager.face_reader)
        if manager.face_reader and manager.face_reader.output_width > 0:
            manager.window_width = manager.face_reader.output_width
            manager.window_height = manager.face_reader.output_height
            print(
                f"根据RTMP流方向自动调整窗口尺寸: "
                f"{manager.window_width}x{manager.window_height}"
            )
    except Exception as exc:
        print(f"启动RTMP流驱动失败: {exc}")
        manager.face_reader = None


def initialize_playback_capture(manager) -> None:
    """Start the configured driving input before playback workers consume frames."""
    if manager.input_mode == "camera" and manager.face_reader:
        start_camera_capture(manager)
    elif manager.input_mode == "video":
        start_video_capture(manager)
    elif manager.input_mode == "rtmp":
        start_rtmp_capture(manager)

    if manager.input_mode in ("camera", "video", "rtmp") and manager.face_reader_iterator:
        start_live_frame_pipeline(manager)


def initialize_playback_player(manager) -> bool:
    """Initialize a missing player and report whether playback can proceed."""
    if manager.player is None:
        init_player = getattr(manager, "init_player", None)
        if init_player is None:
            initialize_output_player(manager)
        else:
            init_player()
    return bool(manager.player)


def start_playback_threads(manager) -> None:
    """Launch the output player and then the audio processing loop."""
    if not initialize_playback_player(manager):
        return

    Thread(target=manager.player.start_playing).start()
    Thread(target=run_preloaded_inference_loop, args=(manager,)).start()


def start_playing(manager) -> None:
    """Reset session state, start capture, and launch playback workers."""
    initialize_playback_stats(manager)
    initialize_playback_capture(manager)
    start_playback_threads(manager)


def get_queue_lengths(manager) -> dict[str, int]:
    """Return the current number of audio batches in each configured queue."""
    return {name: queue.qsize() for name, queue in manager.audio_queues.items()}


def build_silent_wenet_features(manager, feature_audio: np.ndarray) -> np.ndarray:
    """Prepare the silent feature data for a decoded input waveform."""
    frame_count = len(feature_audio) // manager.samples_per_frame
    features = manager.silence_wenet_features
    if features is None or features.shape[0] == 0:
        return np.zeros((20, 256), dtype=np.float32)

    feature_count = features.shape[0]
    repeats = (frame_count + feature_count - 1) // feature_count
    return np.tile(features, (repeats, 1, 1))[:frame_count]


def append_danmu_tail_silence(
    manager, audio_path: str, queue_name: str, use_silent_features: bool, target_face_index: int
) -> None:
    """Append silent frames after an unpaused, normally synthesized danmu clip."""
    if queue_name != "danmu" or use_silent_features or manager.pause_event.is_set():
        return

    count = manager.danmu_tail_silence_frames
    if count <= 0:
        return

    audio_chunk = np.zeros(manager.samples_per_frame, dtype=np.float32)
    original_audio_chunk = np.zeros(manager.output_samples_per_frame, dtype=np.float32)
    features = manager.silence_wenet_features
    feature = features[0] if features is not None and len(features) else np.zeros(
        (20, 256), dtype=np.float32
    )
    for _ in range(count):
        manager.audio_queues[queue_name].put(
            AudioBatch(audio_chunk, original_audio_chunk, audio_path, target_face_index,
                       queue_name, feature)
        )


def enqueue_audio_frames(
    manager, audio_path: str, queue_name: str, target_face_index: int,
    feature_audio: np.ndarray, output_audio: np.ndarray, features: np.ndarray,
) -> None:
    """Pair each feature frame with its two rate-specific waveform slices."""
    for index, feature in enumerate(features):
        feature_start = index * manager.samples_per_frame
        feature_end = feature_start + manager.samples_per_frame
        if feature_end > len(feature_audio):
            feature_audio = np.pad(feature_audio, (0, feature_end - len(feature_audio)))

        output_start = index * manager.output_samples_per_frame
        output_end = output_start + manager.output_samples_per_frame
        if output_end > len(output_audio):
            output_audio = np.pad(output_audio, (0, output_end - len(output_audio)))

        manager.audio_queues[queue_name].put(
            AudioBatch(
                audio_chunk=feature_audio[feature_start:feature_end],
                original_audio_chunk=output_audio[output_start:output_end],
                audio_path=audio_path,
                target_face_index=target_face_index,
                queue_name=queue_name,
                wenet_feature=feature,
            )
        )


def add_audio_to_queue(
    manager,
    audio_path: str,
    queue_name: str = "normal",
    use_silent_features: bool = False,
    target_face_index: int = 0,
) -> None:
    """Decode an input clip and submit its aligned waveform and feature frames."""
    if queue_name not in manager.audio_queues:
        raise ValueError(f"未知的队列名称: {queue_name}")

    import librosa

    output_audio, _ = librosa.load(audio_path, sr=manager.output_sample_rate, mono=True)
    feature_audio, _ = librosa.load(audio_path, sr=manager.feature_sample_rate, mono=True)
    if use_silent_features or manager.pause_event.is_set():
        features = build_silent_wenet_features(manager, feature_audio)
    else:
        extract = getattr(manager, "extract_audio_features", None)
        features = extract_audio_features(manager, audio_path) if extract is None else extract(audio_path)

    enqueue_audio_frames(
        manager, audio_path, queue_name, target_face_index,
        feature_audio, output_audio, features,
    )
    append_danmu_tail_silence(
        manager, audio_path, queue_name, use_silent_features, target_face_index
    )


def extract_audio_features(manager, audio_path: str) -> list[np.ndarray]:
    """Extract WeNet bottleneck features and align windows to 25 fps."""
    import librosa
    from bin.image_infer_v2.wenet.compute_ctc_att_bnf import get_weget

    waveform, _ = librosa.load(audio_path, sr=16000)
    frame_count = int(len(waveform) / 16000 * 25)
    features = get_weget(audio_path, manager.wenet_model, 560000)
    window_count = features.shape[0] - 20
    intervals = max(frame_count - 1, 1)
    windows = []
    for index in range(frame_count):
        start = int(index / intervals * window_count)
        windows.append(features[start:start + 20, :])
    return windows


def initialize_speech_state(manager, output_sample_rate: int = 24000) -> None:
    """Create the audio queues and set the scheduling and fade defaults."""
    manager.feature_sample_rate = 16000
    resolved_rate = resolve_output_sample_rate(output_sample_rate)
    if resolved_rate != output_sample_rate:
        print(f"音频输出采样率已调整为声卡支持值: {resolved_rate} Hz")
    manager.output_sample_rate = resolved_rate
    manager.fps = 25
    manager.samples_per_frame = manager.feature_sample_rate // manager.fps
    manager.output_samples_per_frame = manager.output_sample_rate // manager.fps
    manager.processing_lock = Lock()
    manager.pause_event = Event()
    manager.live_frame_lock = Lock()
    manager.audio_queues = {"normal": Queue(), "danmu": Queue()}
    manager.queue_priority = ["danmu", "normal"]
    manager.idle_fade_out_frames = 13
    manager.danmu_tail_silence_frames = 12
    manager.idle_fade_in_frames = 13
    manager._speech_av_mode = "normal"
    manager._last_real_queue = "silence"
    manager._pending_fade_in = False
    manager._fade_out_total = 0
    manager._fade_out_remaining = 0
    manager._fade_in_total = 0
    manager._fade_in_remaining = 0


def resolve_output_sample_rate(preferred_rate: int, channels: int = 1) -> int:
    """Probe output support using a temporary PyAudio instance."""
    from .frame_player_kt import _resolve_output_sample_rate

    try:
        from pyaudio import PyAudio

        audio = PyAudio()
    except Exception:
        return 48000

    try:
        return _resolve_output_sample_rate(audio, preferred_rate, channels)
    finally:
        audio.terminate()


def configure_playback_audio(manager) -> None:
    """Pass the negotiated output rate and frame size to the player."""
    manager.player.SAMPLE_RATE = manager.output_sample_rate
    manager.player.samples_per_frame = manager.output_samples_per_frame


def initialize_output_player(manager) -> None:
    """Create the output player for the configured display mode."""
    if manager.image_output_mode == "window":
        from .frame_player_kt import StreamPlayer
    else:
        from .frame_player_cam import StreamPlayer

    manager.player = StreamPlayer(manager.window_width, manager.window_height)
    configure_playback_audio(manager)


def load_single_frame_data(manager, frame_idx: int) -> FrameData:
    """Read a numbered image and its coordinate metadata."""
    from ast import literal_eval
    from pathlib import Path

    import cv2

    physical_index = frame_idx % manager.total_frames
    frame_number = str(physical_index).zfill(6)
    frame_path = Path(manager.frames_dir) / f"{frame_number}.jpg"
    position_path = Path(manager.positions_dir) / f"{frame_number}.txt"
    image = cv2.imread(str(frame_path))

    metadata = {}
    with position_path.open() as positions:
        for line in positions:
            key, separator, value = line.partition(":")
            key = key.strip()
            if separator and key in ("bounding_box", "bbox", "landmarks", "positions", "lmk"):
                metadata[key] = np.array(literal_eval(value.strip()))
    return FrameData(image, metadata, physical_index)


def load_batch_frame_data(manager, frame_indices: list[int]) -> list[FrameData]:
    """Submit each frame read and collect results in input order."""
    from functools import partial

    load_frame = getattr(manager, "_load_single_frame_data", None)
    if load_frame is None:
        load_frame = partial(load_single_frame_data, manager)
    futures = [manager.executor.submit(load_frame, index) for index in frame_indices]
    return [future.result() for future in futures]


def run_preload_frames_worker(manager) -> None:
    """Keep the disk-frame buffer filled in synthesis-sized batches."""
    queue = manager.preloaded_frame_queue
    stop = manager.preload_stop_event
    if queue is None or stop is None:
        return

    while not stop.is_set():
        needed = min(queue.maxsize - queue.qsize(), manager.synthesizer.batch_size)
        if needed <= 0:
            sleep(0.01)
            continue
        generate_sequence = getattr(manager, "_generate_frame_sequence", None)
        if generate_sequence is not None:
            indices = generate_sequence(needed)
        elif manager.enable_action_generalization:
            indices = generate_action_frame_sequence(manager, needed)
        else:
            indices = generate_sequential_frame_sequence(manager, needed)
        for frame in load_batch_frame_data(manager, indices):
            if stop.is_set():
                return
            queue.put(frame)


def generate_sequential_frame_sequence(manager, needed_frames: int) -> list[int]:
    """Generate sequential frame indices and advance the wrapped cursor."""
    indices = []
    for _ in range(needed_frames):
        indices.append(manager.sequence_frame_position)
        manager.sequence_frame_position = (
            manager.sequence_frame_position + 1
        ) % manager.total_frames
    return indices


def generate_action_frame_sequence(manager, needed_frames: int) -> list[int]:
    """Generate motion segments with a cursor that reflects at frame boundaries."""
    from random import choice, randint

    total_frames = manager.total_frames
    if total_frames < 2:
        return [0] * needed_frames

    indices = []
    for _ in range(needed_frames):
        if manager.processed_frame_count >= manager.target_frame_count:
            manager.target_frame_count = max(25, total_frames * randint(5, 15) // 100)
            manager.current_direction = choice([1, -1])
            manager.processed_frame_count = 0

        indices.append(manager.current_frame_position)
        manager.current_frame_position += manager.current_direction
        if manager.current_frame_position >= total_frames:
            manager.current_frame_position = total_frames - 2
            manager.current_direction = -1
        elif manager.current_frame_position < 0:
            manager.current_frame_position = 1
            manager.current_direction = 1
        manager.processed_frame_count += 1
    return indices


def initialize_frame_sequence_state(manager) -> None:
    """Initialize both frame cursors and the action segment state."""
    manager.current_frame_position = 0
    manager.current_direction = None
    manager.target_frame_count = 0
    manager.processed_frame_count = 0
    manager.sequence_frame_position = 0


def initialize_frame_preload(manager) -> None:
    """Create and start the file-frame buffer after the synthesizer is ready."""
    initialize_frame_sequence_state(manager)
    manager.preloaded_frame_queue = Queue(maxsize=4 * manager.synthesizer.batch_size)
    manager.preload_stop_event = Event()
    manager.preload_thread = Thread(
        target=run_preload_frames_worker, args=(manager,), daemon=True,
    )
    manager.preload_thread.start()


def initialize_file_frame_source(manager, data_dir) -> None:
    """Set up the numbered frame directories and their loading executor."""
    from concurrent.futures import ThreadPoolExecutor
    from os import listdir
    from pathlib import Path

    root = Path(data_dir)
    manager.frames_dir = root / "frames"
    manager.positions_dir = root / "positions"
    manager.total_frames = sum(name.endswith(".jpg") for name in listdir(manager.frames_dir))
    manager.executor = ThreadPoolExecutor(max_workers=manager.synthesizer.batch_size)
