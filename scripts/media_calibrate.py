#!/usr/bin/env python3
"""Generate/measure a flash-beep transport signal. This does not grade avatar lips."""
from __future__ import annotations

import argparse
import array
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
import wave


PULSE_SECONDS = (1, 3, 5, 7, 9)
DURATION = 12


class CalibrationError(RuntimeError):
    pass


def ffmpeg(args, *, max_bytes=8 * 1024 * 1024):
    try:
        result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *args], capture_output=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CalibrationError("FFmpeg不可用或处理超时。") from None
    if result.returncode or len(result.stdout) > max_bytes:
        raise CalibrationError("FFmpeg处理失败；请核对本地文件、音视频轨道和支持的编码器。")
    return result.stdout


def generate(output: Path, fps=25, offset_ms=0):
    if output.exists():
        raise CalibrationError("输出文件已存在，拒绝覆盖。")
    if output.suffix.lower() != ".mkv" or fps not in {25, 30, 50, 60} or not -500 <= offset_ms <= 500:
        raise CalibrationError("使用.mkv输出，fps可选25/30/50/60，测试偏移范围-500至500毫秒。")
    output.parent.mkdir(parents=True, exist_ok=True)
    rate = 16000
    samples = array.array("h", [0]) * (DURATION * rate)
    for second in PULSE_SECONDS:
        start = round((second + offset_ms / 1000) * rate)
        for index in range(round(0.08 * rate)):
            samples[start + index] = round(0.7 * 32767 * math.sin(2 * math.pi * 1000 * index / rate))
    if sys.byteorder != "little":
        samples.byteswap()
    with tempfile.TemporaryDirectory(prefix="shuziren-calibration-") as temporary:
        wav_path = Path(temporary) / "pulses.wav"
        with wave.open(str(wav_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(rate)
            audio.writeframes(samples.tobytes())
        # Frame numbers make flash onsets exact at the selected frame rate.
        flash = "+".join("between(n," + str(second * fps) + "," + str(second * fps + max(1, round(0.08 * fps)) - 1) + ")" for second in PULSE_SECONDS)
        ffmpeg(["-n", "-f", "lavfi", "-i", f"color=c=black:s=640x360:r={fps}:d={DURATION}", "-i", str(wav_path), "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='" + flash + "'", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-shortest", str(output)])


def onset_indices(values, threshold, minimum_gap):
    result = []
    previous_on = False
    for index, value in enumerate(values):
        on = value >= threshold
        if on and not previous_on and (not result or index - result[-1] >= minimum_gap):
            result.append(index)
        previous_on = on
    return result


def analyze(recording: Path, fps=25, expected=5, target_ms=80.0, crop=""):
    if not recording.is_file() or fps not in {25, 30, 50, 60} or not 3 <= expected <= 20 or not 0 <= target_ms <= 2000:
        raise CalibrationError("输入文件、fps、脉冲数量或目标误差无效。")
    if crop and not re.fullmatch(r"[1-9][0-9]{0,4}:[1-9][0-9]{0,4}:[0-9]{1,5}:[0-9]{1,5}", crop):
        raise CalibrationError("crop须为width:height:x:y整数，不接受任意滤镜表达式。")
    video_filter = ("crop=" + crop + "," if crop else "") + f"fps={fps}:start_time=0,scale=8:8,format=gray"
    # Use one normalized container origin for both streams. Padding from PTS=0
    # preserves a stream's initial offset rather than resetting each separately.
    common = ["-copyts", "-start_at_zero", "-i", str(recording), "-t", "120"]
    video = ffmpeg([*common, "-map", "0:v:0", "-vf", video_filter, "-an", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"])
    pcm = ffmpeg([*common, "-map", "0:a:0", "-vn", "-af", "aresample=16000:async=1:first_pts=0", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"])
    if not video or len(video) % 64 or not pcm or len(pcm) % 2:
        raise CalibrationError("无法提取完整音视频样本。")
    means = [sum(video[index:index + 64]) / 64 for index in range(0, len(video), 64)]
    if max(means) - min(means) < 80:
        raise CalibrationError("未识别出高对比闪光；请让校准区域充满画面或指定crop。")
    visual = [index / fps for index in onset_indices(means, (max(means) + min(means)) / 2, max(1, fps // 2))]
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    size = 80  # 5 ms at 16 kHz
    rms = [math.sqrt(sum((v / 32768) ** 2 for v in samples[index:index + size]) / len(samples[index:index + size])) for index in range(0, len(samples), size)]
    if not rms or max(rms) < 0.01:
        raise CalibrationError("音轨过小或静音，不能可靠识别蜂鸣。")
    audible = [index * 0.005 for index in onset_indices(rms, max(rms) * 0.25, 100)]
    if len(visual) != expected or len(audible) != expected:
        raise CalibrationError(f"预期{expected}组闪光/蜂鸣，识别到{len(visual)}/{len(audible)}；拒绝把缺失、额外声音或错误配对当成测量结果。")
    # The reference has fixed 2-second spacing; allow 150 ms acquisition jitter.
    for times in (visual, audible):
        if any(abs((b - a) - 2) > 0.15 for a, b in zip(times, times[1:])):
            raise CalibrationError("识别事件不符合2秒参考间隔，可能混入其他画面或声音。")
    offsets = [(a - v) * 1000 for a, v in zip(audible, visual)]
    ordered = sorted(abs(value) for value in offsets)
    data_hash = hashlib.sha256()
    with recording.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            data_hash.update(chunk)
    return {
        "schema": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "kind": "flash_beep_transport_only",
        "recording_sha256": data_hash.hexdigest(), "pulses": [{"video_seconds": round(v, 4), "audio_seconds": round(a, 4), "audio_minus_video_ms": round(delta, 3)} for v, a, delta in zip(visual, audible, offsets)],
        "median_audio_minus_video_ms": round(statistics.median(offsets), 3), "maximum_absolute_ms": round(max(ordered), 3), "p95_absolute_ms": round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3),
        "frame_resolution_ms": round(1000 / fps, 3), "audio_window_ms": 5, "target_ms": target_ms, "within_target": all(abs(value) <= target_ms for value in offsets),
        "sign_convention": "positive means audio arrives later than video", "not_measured": ["人物发音对应的口型", "牙齿与嘴周细节", "未包含在该录制中的平台链路"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("generate")
    create.add_argument("output", type=Path)
    create.add_argument("--fps", type=int, default=25)
    create.add_argument("--audio-offset-ms", type=int, default=0, help="Inject a KNOWN test offset; default is zero")
    measure = sub.add_parser("analyze")
    measure.add_argument("recording", type=Path)
    measure.add_argument("--output", type=Path, required=True)
    measure.add_argument("--fps", type=int, default=25)
    measure.add_argument("--expected", type=int, default=5)
    measure.add_argument("--target-ms", type=float, default=80)
    measure.add_argument("--crop", default="")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            generate(args.output, args.fps, args.audio_offset_ms)
            print("Reference created: " + str(args.output))
            print("Synthetic transport signal only; no avatar quality was tested.")
            return 0
        result = analyze(args.recording, args.fps, args.expected, args.target_ms, args.crop)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: result[key] for key in ("median_audio_minus_video_ms", "maximum_absolute_ms", "within_target", "frame_resolution_ms")}, ensure_ascii=False))
        return 0 if result["within_target"] else 2
    except (CalibrationError, OSError) as error:
        print(str(error) if isinstance(error, CalibrationError) else "本地文件不可读写，校准未完成。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
