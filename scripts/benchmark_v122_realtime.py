"""Real v122 frame synthesis + NVENC soak test, without logging into a platform.

Run with the authorized runtime's CPython 3.10. Audio is prepared before the
timed section: this measures rendering/encoding, not live TTS or mic latency.
"""

import argparse
import hashlib
import json
import subprocess
import queue
import threading
import time
from pathlib import Path

from v122_acceleration import accelerated_unet, configure_runtime, windows_timer_precision


@windows_timer_precision()
def buffered_render(reader, synth, features, sequence, encoder, frame_count, fps, batch_size, prebuffer, np):
    """Bounded producer/consumer with real frame deadlines, not a replay cache."""
    frames_queue = queue.Queue(maxsize=prebuffer + batch_size)
    stop = threading.Event()
    batches, samples, failures = [], [], []
    producer_started = time.perf_counter()

    def put(value):
        while not stop.is_set():
            try:
                frames_queue.put(value, timeout=0.1)
                return
            except queue.Full:
                pass

    def produce():
        try:
            for offset in range(0, frame_count, batch_size):
                if stop.is_set():
                    break
                t = time.perf_counter()
                images, metadata = reader._load_batch_frames(sequence[offset:offset + batch_size])
                frames = synth.synthesize_batch(features[offset:offset + batch_size], images, metadata)
                elapsed = time.perf_counter() - t
                if len(frames) != batch_size:
                    raise RuntimeError("Producer dropped frames")
                batches.append({"offset": offset, "compute_seconds": elapsed,
                                "including_encode_write_seconds": elapsed,
                                "ready_seconds": time.perf_counter() - producer_started,
                                "late_seconds": 0})
                for index, frame in enumerate(frames):
                    put((offset + index, frame))
        except BaseException as error:
            failures.append(error)
        finally:
            put(None)

    def sample_gpu():
        while not stop.is_set():
            try:
                value = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                                        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
                if value.returncode == 0:
                    samples.append({"elapsed": time.perf_counter() - producer_started, "values": value.stdout.strip()})
            except (OSError, subprocess.TimeoutExpired):
                pass
            stop.wait(2)

    producer = threading.Thread(target=produce, name="v122-render-producer", daemon=True)
    sampler = threading.Thread(target=sample_gpu, name="v122-gpu-sampler", daemon=True)
    producer.start()
    sampler.start()
    readiness_lags, write_lags, starvation = [], [], 0
    first_ready = None

    def take():
        nonlocal starvation
        if frames_queue.empty():
            starvation += 1
        item = frames_queue.get(timeout=30)
        if item is None:
            if failures:
                raise failures[0]
            raise RuntimeError("Frame producer ended early")
        return item

    try:
        # Prefill real newly synthesized images before starting the playback clock.
        pending = [take() for _ in range(min(prebuffer, frame_count))]
        prefill_seconds = time.perf_counter() - producer_started
        playback_started = time.perf_counter()
        starvation = 0
        for expected in range(frame_count):
            index, frame = pending[expected] if expected < len(pending) else take()
            due = playback_started + expected / fps
            time.sleep(max(0, due - time.perf_counter()))
            ready = time.perf_counter()
            if index != expected or frame.dtype != np.uint8 or frame.shape != pending[0][1].shape:
                raise RuntimeError("Invalid or reordered buffered frame")
            if first_ready is None:
                first_ready = ready - producer_started
            encoder.stdin.write(np.ascontiguousarray(frame).tobytes())
            readiness_lags.append(max(0, ready - due))
            write_lags.append(max(0, time.perf_counter() - due - 1 / fps))
            if expected % 100 == 3:
                print("FRAMES", expected + 1, "/", frame_count, flush=True)
        seconds = time.perf_counter() - playback_started
    finally:
        stop.set()
        producer.join(timeout=30)
        sampler.join(timeout=6)
    if producer.is_alive():
        raise RuntimeError("Synthesis worker failed to stop")
    if failures:
        raise failures[0]
    return seconds, batches, samples, {
        "prebuffer_frames": prebuffer, "prefill_seconds": prefill_seconds,
        "first_frame_since_producer_start_ms": first_ready * 1000,
        "frame_deadline_misses_over_5ms": sum(v > 0.005 for v in readiness_lags),
        "max_frame_late_ms": max(readiness_lags) * 1000,
        "frame_late_p95_ms": float(np.percentile(readiness_lags, 95)) * 1000,
        "encoder_deadline_misses": sum(v > 0.005 for v in write_lags),
        "queue_starvation_events": starvation,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--person-id", required=True)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--backend", choices=["cuda", "tensorrt"], default="tensorrt")
    parser.add_argument("--unpaced", action="store_true", help="Measure maximum throughput")
    parser.add_argument("--buffer-frames", type=int, default=0, help="Bounded real-frame prebuffer; 8 = 320ms at 25fps")
    args = parser.parse_args()
    if args.seconds <= 0 or Path(args.person_id).name != args.person_id:
        parser.error("positive duration and a single person directory name are required")
    if args.buffer_frames and (args.buffer_frames < 4 or args.unpaced):
        parser.error("buffered playback requires at least four frames and paced output")
    runtime = args.runtime_root.resolve()
    audio = args.audio.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = args.cache.resolve()
    internal = configure_runtime(runtime)

    import cv2
    import numpy as np
    import torch
    import yaml
    from bin.image_clone.infer_api import VideoSynthesizer
    from bin.image_infer_v2.infer_api import FrameSynthesizer

    config = yaml.safe_load((internal / "config/config.yaml").read_text(encoding="utf-8"))
    person = (internal / "assets/characters/images" / args.person_id).resolve(strict=True)
    person.relative_to(internal / "assets/characters/images")
    ffmpeg = internal / "env/ffmpeg/bin/ffmpeg.exe"
    ffprobe = ffmpeg.with_name("ffprobe.exe")
    prepared_audio = output / "input.wav"
    subprocess.run([str(ffmpeg), "-nostdin", "-v", "error", "-y", "-stream_loop", "-1",
                    "-i", str(audio), "-t", str(args.seconds), "-ac", "1", "-ar", "24000",
                    "-c:a", "pcm_s16le", str(prepared_audio)], check=True)
    initialization_started = time.perf_counter()
    with accelerated_unet(cache, backend="cuda"):
        reader = VideoSynthesizer(str(person), str(internal / config["unet_v2_model"]),
                                  str(internal / config["wenet_config"]),
                                  str(internal / config["wenet_model"]), device="cuda:0",
                                  batch_size=4, silence_feature_path=str(internal / config["image_infer_v2_silence_path"]))
    # Retain original Wenet and original frame loader, release unused offline UNet.
    reader.ort_session = None
    torch.cuda.empty_cache()
    feature_started = time.perf_counter()
    features = reader.extract_audio_features(str(prepared_audio))
    feature_seconds = time.perf_counter() - feature_started
    fps, batch_size = 25, 4
    frame_count = (min(len(features), args.seconds * fps) // batch_size) * batch_size
    if frame_count == 0:
        raise RuntimeError("No usable audio features")
    frame_sequence = reader._generate_frame_sequence(frame_count)
    with accelerated_unet(cache, backend=args.backend) as sessions:
        synth = FrameSynthesizer(str(person), str(internal / config["unet_v2_model"]), device="cuda:0")
        if synth.batch_size != batch_size:
            raise RuntimeError("Runtime batch size changed; benchmark must be adapted")
        images, metadata = reader._load_batch_frames(frame_sequence[:batch_size])
        # Complete engine building and warmup before timing, without caching outputs.
        warmup_started = time.perf_counter()
        for _ in range(3):
            warm = synth.synthesize_batch(features[:batch_size], images, metadata)
        warmup_seconds = time.perf_counter() - warmup_started
        if len(warm) != batch_size or not all(np.isfinite(x).all() for x in warm):
            raise RuntimeError("Invalid warmup frames")
        height, width = warm[0].shape[:2]
        initialization_seconds = time.perf_counter() - initialization_started
        video = output / "realtime.mp4"
        command = [str(ffmpeg), "-nostdin", "-v", "error", "-y", "-f", "rawvideo",
                   "-pix_fmt", "bgr24", "-s", "%dx%d" % (width, height), "-r", str(fps),
                   "-i", "pipe:0", "-i", str(prepared_audio), "-map", "0:v:0", "-map", "1:a:0",
                   "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll", "-b:v", "4M",
                   "-g", "50", "-bf", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                   "-movflags", "+faststart", str(video)]
        batches, gpu_samples, buffer_result = [], [], {}
        with (output / "encoder.log").open("wb") as log:
            encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            started = time.perf_counter()
            try:
                if args.buffer_frames:
                    render_seconds, batches, gpu_samples, buffer_result = buffered_render(
                        reader, synth, features, frame_sequence, encoder, frame_count, fps,
                        batch_size, args.buffer_frames, np)
                offsets = [] if args.buffer_frames else range(0, frame_count, batch_size)
                for offset in offsets:
                    due_start = started + offset / fps
                    if not args.unpaced:
                        time.sleep(max(0, due_start - time.perf_counter()))
                    batch_started = time.perf_counter()
                    images, metadata = reader._load_batch_frames(frame_sequence[offset:offset + batch_size])
                    frames = synth.synthesize_batch(features[offset:offset + batch_size], images, metadata)
                    if len(frames) != batch_size:
                        raise RuntimeError("Synthesis dropped frames")
                    ready_at = time.perf_counter()
                    for frame in frames:
                        if frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                            raise RuntimeError("Invalid output image")
                        encoder.stdin.write(np.ascontiguousarray(frame).tobytes())
                    completed = time.perf_counter()
                    batches.append({"offset": offset, "compute_seconds": ready_at - batch_started,
                                    "including_encode_write_seconds": completed - batch_started,
                                    "ready_seconds": ready_at - started,
                                    "late_seconds": max(0, completed - (started + (offset + batch_size) / fps))})
                    if offset % 100 == 0:
                        sample = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
                        if sample.returncode == 0:
                            gpu_samples.append({"offset": offset, "values": sample.stdout.strip()})
                        print("FRAMES", offset + batch_size, "/", frame_count, flush=True)
                if not args.buffer_frames:
                    render_seconds = time.perf_counter() - started
            finally:
                encoder.stdin.close()
                try:
                    encoder_exit = encoder.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    encoder.kill()
                    encoder.wait()
                    raise
        if encoder_exit:
            raise RuntimeError("NVENC failed; see encoder.log")
        providers = [s.get_providers() for s in sessions]
    probe = json.loads(subprocess.check_output([str(ffprobe), "-v", "error", "-show_streams",
                                               "-show_format", "-of", "json", str(video)], text=True))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    if int(stream["nb_frames"]) != frame_count:
        raise RuntimeError("Encoded frame count does not match synthesis")
    decode = subprocess.run([str(ffmpeg), "-nostdin", "-v", "error", "-i", str(video), "-f", "null", "-"],
                            capture_output=True, text=True, timeout=120)
    if decode.returncode:
        raise RuntimeError("Output failed full decode")
    batch_times = [b["including_encode_write_seconds"] for b in batches]
    result = {"backend": args.backend, "paced": not args.unpaced, "frames": frame_count,
              "video_seconds": frame_count / fps, "width": width, "height": height, "target_fps": fps,
              "wall_seconds": render_seconds, "capacity_fps": frame_count / sum(batch_times),
              "initialization_including_features_seconds": initialization_seconds,
              "feature_seconds": feature_seconds, "extra_warmup_seconds": warmup_seconds,
              "first_batch_ready_ms": batches[0]["ready_seconds"] * 1000,
              "batch_p95_ms": float(np.percentile(batch_times, 95)) * 1000,
              "deadline_miss_batches": sum(b["late_seconds"] > 0.005 for b in batches),
              "max_late_ms": max(b["late_seconds"] for b in batches) * 1000,
              "providers": providers, "gpu_samples": gpu_samples, "batches": batches,
              "source_audio_precomputed": True, "live_tts_tested": False,
              "virtual_camera_or_platform_tested": False, "full_decode_exit": decode.returncode,
              "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest()}
    result["buffered_playback"] = buffer_result
    result["capacity_scope"] = "synthesis_and_frame_read" if buffer_result else "synthesis_and_encoder_pipe_write"
    if buffer_result:
        # Batch deadlines apply to the unbuffered probe only; frame deadlines are authoritative here.
        result["deadline_miss_batches"] = None
        result["max_late_ms"] = None
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "probe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
    print("RESULT", json.dumps({k: v for k, v in result.items() if k not in {"batches", "gpu_samples"}}), flush=True)


if __name__ == "__main__":
    main()
