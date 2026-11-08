#!/usr/bin/env python3
"""Runs confirmed v122 APIs inside the bundled CPython 3.10 environment."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def _runtime():
    configured = os.environ.get("V122_RUNTIME_ROOT")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _load():
    runtime = _runtime(); internal = runtime / "_internal"
    os.chdir(str(internal)); sys.path.insert(0, str(internal))
    import yaml
    config = yaml.safe_load((internal / "config/config.yaml").read_text(encoding="utf-8")) or {}
    config["runtime_dir"] = str(internal)
    return runtime, internal, config


def main(argv=None):
    parser = argparse.ArgumentParser(); subs = parser.add_subparsers(dest="action", required=True)
    avatar = subs.add_parser("avatar-preprocess"); avatar.add_argument("video"); avatar.add_argument("name"); avatar.add_argument("id")
    voice = subs.add_parser("voice-create"); voice.add_argument("audio"); voice.add_argument("transcript"); voice.add_argument("name"); voice.add_argument("id")
    speech = subs.add_parser("speech-generate"); speech.add_argument("voice_id"); speech.add_argument("transcript"); speech.add_argument("text"); speech.add_argument("output")
    drive = subs.add_parser("avatar-drive"); drive.add_argument("model_id"); drive.add_argument("audio"); drive.add_argument("output")
    args = parser.parse_args(argv); runtime, internal, config = _load()
    from live.clone_manager import CloneManager
    manager = CloneManager(config)
    if args.action == "avatar-preprocess":
        manager.clone_video_local(args.video, args.name, args.id, "720p", False)
        result = internal / "assets/characters/images" / args.id
    elif args.action == "voice-create":
        manager.clone_voice_local(args.audio, args.name, args.id, "zh", False)
        result = internal / "assets/characters/voices" / args.id
        (result / "ref_text.txt").write_text(args.transcript.strip(), encoding="utf-8")
    elif args.action == "speech-generate":
        from tools.generate_short_video.audio_synthesis import synthesize_text_to_audio
        voice_dir = internal / "assets/characters/voices" / args.voice_id
        generated = synthesize_text_to_audio(text=args.text, speed=1.0, language="zh-CN", scene="live",
            voice_id=args.voice_id, reference_audio=str(voice_dir / "ref_audio.wav"),
            reference_text=args.transcript, config={**config, "voice_infer_version": "v2"},
            project_root=str(internal), use_cache=False)
        result = Path(args.output); result.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(generated["audio_path"], result)
    else:
        from bin.image_clone.infer_api import generate_video
        model_dir = internal / "assets/characters/images" / args.model_id
        result = Path(args.output); result.parent.mkdir(parents=True, exist_ok=True)
        generate_video(str(model_dir), args.audio, str(result), str(internal / config["wenet_config"]),
            str(internal / config["wenet_model"]), str(internal / config["unet_v2_model"]),
            device="cuda:0", batch_size=int(config.get("batch_size", 4)),
            silence_feature_path=str(internal / config["image_infer_v2_silence_path"]))
    print(json.dumps({"ok": True, "output": str(result)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
