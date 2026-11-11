"""Run local video playback in the configured media interpreter."""

import argparse
import json
from pathlib import Path
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

    def await_stop():
        sys.stdin.readline()
        stopped.set()

    runtime = configure_runtime(args.runtime_root)
    from recovered.digital_image_runtime import create_image_runtime
    import numpy
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("本地视频直驱需要可用的 CUDA 运行环境")
    threading.Thread(target=await_stop, daemon=True).start()
    manager = create_image_runtime({}, runtime, {
        "window_width": 720, "window_height": 1280, "image_output_mode": "camera",
        "is_interrupt": False, "video_path_for_driving": str(video), "enable_occluder": False,
        "occluder_model_path": "", "origin_idle_video_mode": True,
    })
    try:
        if stopped.is_set():
            return
        manager.configure_console_audio_output(args.audio_device)
        if stopped.is_set():
            return
        manager.start_playing()
        deadline = time.monotonic() + 15
        while not stopped.wait(.05):
            if not manager.worker_thread.is_alive() or not manager.player.running:
                raise RuntimeError("本地视频播放意外停止")
            if manager.player.get_playback_stats_snapshot()["output_frames"]:
                print(json.dumps({"event": "running"}), flush=True)
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("本地视频首帧输出超时")
        while not stopped.wait(.1):
            if not manager.worker_thread.is_alive() or not manager.player.running:
                raise RuntimeError("本地视频播放意外停止")
    finally:
        manager.stop_playing()
        manager.tape.close()
    print(json.dumps({"event": "stopped"}), flush=True)


if __name__ == "__main__":
    main()
