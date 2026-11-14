"""X11 real FunASR -> local TTS -> recorded MP4 replacement validation."""

import argparse
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

from recovered.funasr_sentences import recognize_media_sentences
from scripts.recorded_interaction import render_replacements
from scripts.voice_store import VoiceStore


def _run(command, *, timeout=120):
    return subprocess.run(command, check=True, capture_output=True, timeout=timeout)


def _wav_duration_ms(path):
    with wave.open(str(path), "rb") as reader:
        return round(reader.getnframes() * 1000 / reader.getframerate())


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--reference-data", required=True, type=Path)
    parser.add_argument("--report-directory", required=True, type=Path)
    parser.add_argument("--engine", choices=("indextts", "zipvoice", "omnivoice"), default="zipvoice")
    parser.add_argument("--model-root", type=Path)
    args = parser.parse_args(argv)
    runtime, report = args.runtime_root.resolve(), args.report_directory.resolve()
    internal = runtime / "_internal"
    ffmpeg = internal / "env" / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffprobe = ffmpeg.with_name("ffprobe.exe")
    asr_root = internal / "assets" / "pretrained_models" / "asr"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise FileNotFoundError("bundled FFmpeg/FFprobe is missing")
    report.mkdir(parents=True, exist_ok=True)
    outcome = {"task": "X11-02", "status": "failed", "engine": args.engine,
               "scope": "real-funasr-local-tts-recorded-mp4-transaction"}
    process = None
    try:
        source_voices = VoiceStore(args.reference_data.resolve())
        source_id = source_voices.selected()
        if not source_id:
            raise ValueError("reference data has no selected voice")
        source_voice = source_voices.get(source_id)
        transcript = source_voice["transcript"]
        voices = VoiceStore(report)
        imported = voices.import_audio(
            source_voices.audio_path(source_id), transcript, "X11隔离验证音色", ffmpeg,
            authorization_type=source_voice.get("authorization_type") or "unknown",
            authorization_reference=source_voice.get("authorization_reference"),
        )
        voices.select(imported["id"])
        requests = [
            {"voice_id": imported["id"], "text": "欢迎来到数字人录播互动测试。现在验证语音识别、时间区间和回复替换流程。",
             "speed": 1.0, "language": "zh-CN", "use_cache": False},
            {"voice_id": imported["id"], "text": "好的，已经为您记录。",
             "speed": 1.0, "language": "zh-CN", "use_cache": False},
        ]
        command = [sys.executable, "-X", "utf8", "-m", "scripts.tts_worker",
                   "--runtime-root", str(runtime), "--data-directory", str(report),
                   "--engine", args.engine]
        if args.model_root is not None:
            command.extend(["--model-root", str(args.model_root.resolve())])
        worker_log = (report / "tts-worker.log").open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=worker_log,
                text=True, encoding="utf-8")
            payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in
                                 [*requests, {"action": "close"}]) + "\n"
            stdout, _ = process.communicate(payload, timeout=240)
        finally:
            worker_log.close()
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        results = [item["result"] for item in events if item.get("ok")]
        if process.returncode != 0 or len(results) != 2:
            raise RuntimeError("local TTS did not produce two results")
        source_audio, reply_audio = map(lambda item: Path(item["output"]), results)
        source_video = report / "source.mp4"
        _run([str(ffmpeg), "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
              "color=c=0x203040:s=320x240:r=25", "-i", str(source_audio), "-map", "0:v:0",
              "-map", "1:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
              "-shortest", str(source_video)], timeout=60)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(ffmpeg.parent) + os.pathsep + old_path
        try:
            sentences = recognize_media_sentences(str(source_video), str(asr_root))
        finally:
            os.environ["PATH"] = old_path
        if not sentences:
            raise RuntimeError("FunASR returned no timed sentences")
        start_ms = min(int(item["start"]) for item in sentences)
        end_ms = max(int(item["end"]) for item in sentences)
        reply_ms = _wav_duration_ms(reply_audio)
        if end_ms - start_ms < reply_ms:
            raise RuntimeError("ASR candidate interval is shorter than the real reply")
        output = report / "recorded-reply.mp4"
        rendered = render_replacements(source_video, [{"start_ms": start_ms, "end_ms": end_ms,
            "reply_audio": str(reply_audio), "source_id": "funasr-candidate-1"}], output,
            ffmpeg=ffmpeg, timeout=60)
        os.environ["PATH"] = str(ffmpeg.parent) + os.pathsep + old_path
        try:
            output_sentences = recognize_media_sentences(str(output), str(asr_root))
        finally:
            os.environ["PATH"] = old_path
        output_text = "".join(str(item.get("text") or "") for item in output_sentences)
        if "好" not in output_text or "记录" not in output_text:
            raise RuntimeError("final media ASR did not contain the real reply")
        probe = json.loads(subprocess.check_output([str(ffprobe), "-v", "error", "-show_streams",
            "-show_format", "-of", "json", str(output)], timeout=30))
        video = next(item for item in probe["streams"] if item["codec_type"] == "video")
        audio = next(item for item in probe["streams"] if item["codec_type"] == "audio")
        authorization = source_voice.get("authorization_type") or "unknown"
        production_eligible = authorization in {"self_recorded", "consented", "licensed"}
        outcome.update(status="passed", reference_authorization=authorization,
            production_eligible=production_eligible,
            authorization_blocker=None if production_eligible else "参考音授权状态未登记，不得用于发布",
            tts=[{key: item.get(key) for key in ("duration", "sample_rate", "provider", "device",
                                                  "model_loaded", "model_load_count", "sha256")}
                 for item in results], asr_sentences=sentences, replacement={"start_ms": start_ms,
                 "end_ms": end_ms, "reply_duration_ms": reply_ms},
            output_asr_sentences=output_sentences, render=rendered,
            media={"width": video["width"], "height": video["height"],
                   "frames": int(video.get("nb_frames") or 0), "video_codec": video["codec_name"],
                   "audio_codec": audio["codec_name"], "duration": float(probe["format"]["duration"])})
    except Exception as error:
        outcome["error"] = f"{type(error).__name__}: {error}"
        if process is not None and process.poll() is None:
            process.kill(); process.wait(timeout=10)
    finally:
        (report / "result.json").write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": outcome["status"], "report": str(report / "result.json"),
                      "error": outcome.get("error")}, ensure_ascii=False))
    return 0 if outcome["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
