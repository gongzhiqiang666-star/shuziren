"""Measure uncached, distinct phrases with one persistent original IndexTTS instance."""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from v122_acceleration import configure_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--voice-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    internal = configure_runtime(args.runtime_root)
    voice = (internal / "assets/characters/voices" / args.voice_id).resolve(strict=True)
    voice.relative_to(internal / "assets/characters/voices")
    from bin.voice_infer_v3.infer_api import VoiceSynthesizer

    started = time.perf_counter()
    synth = VoiceSynthesizer.from_voice_dir(str(internal / "assets/pretrained_models"),
                                            str(voice.parent), voice.name, device="cuda",
                                            voice_infer_version="v3")
    initialization_seconds = time.perf_counter() - started
    results = []
    try:
        for index, sentence in enumerate([
            "大家好，现在验证数字人持续说话的生成速度，请留意声音和画面是否流畅。",
            "这是一段全新的直播话术，我们保持人物模型不变，并继续测量语音合成速度。",
            "现在完成第三段实时语音测试，感谢观看，请观察人物口型和声音是否同步。",
        ]):
            text = sentence + "本次编号" + str(uuid.uuid4().int)[:6] + "。"
            t = time.perf_counter()
            source = synth.synthesize(text, speed=1.0, language="zh-CN", use_cache=False)
            elapsed = time.perf_counter() - t
            if not source or not Path(source).is_file():
                raise RuntimeError("TTS did not produce audio")
            target = output / ("speech-%d.wav" % index)
            shutil.copy2(source, target)
            duration = float(subprocess.check_output([
                str(internal / "env/ffmpeg/bin/ffprobe.exe"), "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(target)], text=True))
            if duration <= 0 or target.stat().st_size <= 44:
                raise RuntimeError("Empty synthesized audio")
            result = {"index": index, "text": text, "seconds": elapsed, "audio_seconds": duration,
                      "rtf": elapsed / duration, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
            results.append(result)
            print("TTS_RESULT", json.dumps(result, ensure_ascii=True), flush=True)
    finally:
        synth.clear()
    result = {"engine": "original v3/IndexTTS", "persistent_instance": True, "use_cache": False,
              "initialization_seconds": initialization_seconds, "phrases": results,
              "unique_audio_hashes": len({r["sha256"] for r in results}) == len(results)}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
