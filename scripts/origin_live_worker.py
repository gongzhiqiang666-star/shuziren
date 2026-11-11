"""Run local video playback in the configured media interpreter."""

import argparse
import json
from pathlib import Path
from queue import Empty, Queue
import sys
import threading
import time

from scripts.v122_acceleration import configure_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--audio-device", type=int, required=True)
    args = parser.parse_args()
    video = args.video.resolve(strict=True)
    stopped = threading.Event()

    commands = Queue(maxsize=4)

    def read_commands():
        try:
            for line in sys.stdin:
                if line.strip() == "stop":
                    break
                commands.put_nowait(json.loads(line))
        finally:
            stopped.set()

    runtime = configure_runtime(args.runtime_root)
    from recovered.digital_image_runtime import create_image_runtime
    import numpy
    import scipy.linalg
    import torch
    import librosa
    from bin.image_infer_v2.wenet.compute_ctc_att_bnf import load_ppg_model

    # librosa resolves its audio I/O imports lazily.
    _ = librosa.load
    if not torch.cuda.is_available():
        raise RuntimeError("本地视频直驱需要可用的 CUDA 运行环境")
    threading.Thread(target=read_commands, daemon=True).start()
    manager = create_image_runtime({}, runtime, {
        "window_width": 720, "window_height": 1280, "image_output_mode": "camera",
        "is_interrupt": False, "video_path_for_driving": str(video), "enable_occluder": False,
        "occluder_model_path": "", "origin_idle_video_mode": True,
    })
    try:
        if stopped.is_set():
            return
        manager.configure_console_audio_output(args.audio_device)
        manager.buffer_threshold = 8
        manager.wenet_model = load_ppg_model(manager.wenet_conf_path, manager.wenet_model_path, manager.device)
        if stopped.is_set():
            return
        manager.start_playing()
        deadline = time.monotonic() + 15
        while not stopped.wait(.05):
            if not manager.worker_thread.is_alive() or not manager.player.running:
                raise RuntimeError("本地视频播放意外停止")
            frames = manager.player.get_playback_stats_snapshot()["output_frames"]
            if frames:
                print(json.dumps({"event": "running", "frames": frames}), flush=True)
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("本地视频首帧输出超时")
        while not stopped.wait(.1):
            if not manager.worker_thread.is_alive() or not manager.player.running:
                raise RuntimeError("本地视频播放意外停止")
            try:
                command = commands.get_nowait()
            except Empty:
                continue
            if command.get("action") == "seek":
                manager.seek_to_ms(command["position_ms"])
                print(json.dumps({"event": "seek", "position_ms": command["position_ms"]}), flush=True)
            elif command.get("action") == "insert":
                source = Path(command["path"])
                error = None
                try:
                    if manager._in_interact or manager._has_queued_interact():
                        raise ValueError("上一条插播尚未结束")
                    manager.add_audio_to_queue(str(source), "danmu")
                except Exception as exc:
                    error = str(exc)
                finally:
                    source.unlink(missing_ok=True)
                print(json.dumps({"event": "insert", "task_id": command["task_id"], "error": error}), flush=True)
    finally:
        manager.stop_playing()
        manager.tape.close()
    print(json.dumps({"event": "stopped", "frames": manager.player.get_playback_stats_snapshot()["output_frames"]}), flush=True)


if __name__ == "__main__":
    main()
