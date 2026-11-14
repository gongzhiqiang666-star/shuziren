"""Run one bounded, real IndexTTS long-text synthesis and record safe evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import wave

from scripts.voice_store import VoiceStore


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--data-directory", required=True, type=Path)
    parser.add_argument("--report-directory", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args(argv)

    voice_id = VoiceStore(args.data_directory).selected()
    if not voice_id:
        raise RuntimeError("没有已选择的参考音色")
    sentence = "这是一段用于验证数字人长文本语音生成稳定性的测试内容，包含商品介绍、使用场景、注意事项和自然停顿。"
    text = (sentence * 13)[:650]
    request = {
        "voice_id": voice_id,
        "text": text,
        "speed": 1.0,
        "language": "zh-CN",
        "use_cache": False,
    }
    command = [
        sys.executable, "-X", "utf8", "-m", "scripts.tts_worker",
        "--runtime-root", str(args.runtime_root.resolve()),
        "--data-directory", str(args.data_directory.resolve()),
    ]
    environment = os.environ.copy()
    ffmpeg = args.runtime_root.resolve() / "_internal/env/ffmpeg/bin"
    environment["PATH"] = str(ffmpeg) + os.pathsep + environment.get("PATH", "")
    started = time.time()
    process = subprocess.Popen(
        command, cwd=Path(__file__).resolve().parents[1], env=environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    payload = json.dumps(request, ensure_ascii=False) + "\n" + json.dumps({"action": "close"}) + "\n"
    try:
        stdout, stderr = process.communicate(payload, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        raise RuntimeError(f"IndexTTS 长文本生成超过 {args.timeout} 秒")
    lines = [json.loads(line) for line in stdout.splitlines() if line.strip().startswith("{")]
    response = next((line for line in lines if "ok" in line), None)
    if process.returncode != 0 or not response or not response.get("ok"):
        tail = "\n".join(stderr.splitlines()[-20:])
        raise RuntimeError(f"IndexTTS 长文本生成失败（退出码 {process.returncode}）\n{tail}")

    result = response["result"]
    output = Path(result["output"]).resolve()
    with wave.open(str(output), "rb") as reader:
        metadata = {
            "channels": reader.getnchannels(),
            "sample_width": reader.getsampwidth(),
            "sample_rate": reader.getframerate(),
            "frames": reader.getnframes(),
            "duration": reader.getnframes() / reader.getframerate(),
        }
    if metadata["channels"] != 1 or metadata["sample_width"] != 2:
        raise RuntimeError("IndexTTS 长文本输出不是单声道 PCM16 WAV")
    if metadata["sample_rate"] != 24000 or metadata["frames"] <= 0:
        raise RuntimeError("IndexTTS 长文本输出采样率或帧数无效")

    report = {
        "status": "passed",
        "provider": result["provider"],
        "device": result["device"],
        "input_chars": len(text),
        "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "model_loaded": result["model_loaded"],
        "model_load_count": result["model_load_count"],
        "inference_calls": result["inference_calls"],
        "request_seconds": result["request_seconds"],
        "wall_seconds": time.time() - started,
        "output_sha256": result["sha256"],
        "audio": metadata,
    }
    args.report_directory.mkdir(parents=True, exist_ok=True)
    report_path = args.report_directory / "result.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path.resolve()), **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
