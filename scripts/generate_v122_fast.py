"""Generate a real v122 MP4 using the opt-in, process-local accelerator."""

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from v122_acceleration import accelerated_unet, configure_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--person-id", required=True)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--backend", choices=["cuda", "tensorrt"], default="tensorrt")
    args = parser.parse_args()
    audio = args.audio.resolve(strict=True)
    output = args.output.resolve()
    cache = args.cache.resolve()
    if output.exists() or output == audio:
        parser.error("output must be a new file")
    internal = configure_runtime(args.runtime_root)
    import yaml
    from bin.image_clone.infer_api import VideoSynthesizer

    person = (internal / "assets/characters/images" / args.person_id).resolve(strict=True)
    person.relative_to(internal / "assets/characters/images")
    config = yaml.safe_load((internal / "config/config.yaml").read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    before_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
    started = time.perf_counter()
    with accelerated_unet(cache, backend=args.backend) as sessions:
        synth = VideoSynthesizer(str(person), str(internal / config["unet_v2_model"]),
                                 str(internal / config["wenet_config"]), str(internal / config["wenet_model"]),
                                 device="cuda:0", batch_size=4,
                                 silence_feature_path=str(internal / config["image_infer_v2_silence_path"]))
        initialized = time.perf_counter()
        synth.process_single_file(str(audio), str(output))
        elapsed = time.perf_counter() - started
        providers = [s.get_providers() for s in sessions]
    probe_tool = internal / "env/ffmpeg/bin/ffprobe.exe"
    probe = json.loads(subprocess.check_output([str(probe_tool), "-v", "error", "-show_streams",
                                               "-show_format", "-of", "json", str(output)], text=True))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    if not any(s["codec_type"] == "audio" for s in probe["streams"]):
        raise RuntimeError("Generated MP4 has no audio")
    if before_hash != hashlib.sha256(audio.read_bytes()).hexdigest():
        raise RuntimeError("Input audio changed during generation")
    result = {"backend": args.backend, "providers": providers,
              "initialization_seconds": initialized - started, "total_seconds": elapsed,
              "frames": int(video["nb_frames"]), "duration": float(video["duration"]),
              "width": video["width"], "height": video["height"], "fps": video["avg_frame_rate"],
              "wav_sha256": before_hash, "video_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix(".result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("RESULT", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
