"""Validated audio replacement plan for the recorded-interaction candidate."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class Replacement:
    start_ms: int
    end_ms: int
    reply_audio: str
    source_id: str


def validate_replacements(items, *, duration_ms, max_items=100):
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 1:
        raise ValueError("positive integer duration required")
    if not isinstance(items, (list, tuple)) or len(items) > max_items:
        raise ValueError("replacement count exceeds limit")
    result = []
    previous_end = 0
    seen = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("replacement must be an object")
        if set(raw) != {"start_ms", "end_ms", "reply_audio", "source_id"}:
            raise ValueError("replacement fields are invalid")
        start, end = raw["start_ms"], raw["end_ms"]
        if any(not isinstance(value, int) or isinstance(value, bool) for value in (start, end)):
            raise ValueError("replacement times must be integers")
        if start < previous_end or end <= start or end > duration_ms:
            raise ValueError("replacement intervals overlap or exceed media")
        source_id = str(raw["source_id"] or "").strip()
        if not source_id or source_id in seen:
            raise ValueError("replacement source identity is missing or duplicated")
        supplied = Path(str(raw["reply_audio"] or ""))
        if supplied.is_symlink():
            raise ValueError("replacement audio is not a regular file")
        path = supplied.resolve()
        if not path.is_file():
            raise ValueError("replacement audio is not a regular file")
        result.append(Replacement(start, end, str(path), source_id))
        previous_end = end
        seen.add(source_id)
    return result


def mix_replacements(original_audio, replacements):
    """Silence approved intervals and overlay replies without shifting the source."""
    from pydub import AudioSegment

    output = original_audio
    for item in replacements:
        with Path(item.reply_audio).open("rb") as source:
            reply = AudioSegment.from_file(source, format="wav")
        budget = item.end_ms - item.start_ms
        if len(reply) > budget:
            raise ValueError(f"reply audio exceeds approved interval: {item.source_id}")
        silence = AudioSegment.silent(duration=budget, frame_rate=output.frame_rate)
        silence = silence.set_channels(output.channels).set_sample_width(output.sample_width)
        output = output[:item.start_ms] + silence + output[item.end_ms:]
        output = output.overlay(reply, position=item.start_ms)
    return output


def render_replacements(source_video, items, output_video, *, ffmpeg, timeout=300, cancel_check=None):
    """Atomically replace approved audio intervals while copying the video track."""
    source = Path(source_video).expanduser().resolve()
    output = Path(output_video).expanduser().resolve()
    executable = Path(ffmpeg).expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError("source video is not a regular file")
    if output.suffix.lower() != ".mp4" or output == source:
        raise ValueError("output video must be a different MP4 path")
    if not executable.is_file():
        raise ValueError("ffmpeg executable is missing")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("positive timeout required")
    if cancel_check is not None and not callable(cancel_check):
        raise TypeError("cancel_check must be callable")
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_name(f".{output.stem}.{uuid4().hex}.pending.mp4")
    workspace = Path(tempfile.mkdtemp(prefix="recorded-interaction-", dir=str(output.parent)))
    original_wav, mixed_wav = workspace / "original.wav", workspace / "mixed.wav"

    def run(arguments):
        process = subprocess.Popen(
            [str(executable), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *arguments],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + float(timeout)
        try:
            while process.poll() is None:
                if cancel_check is not None and cancel_check():
                    process.terminate()
                    try:
                        process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.communicate()
                    raise InterruptedError("recorded interaction render cancelled")
                if time.monotonic() >= deadline:
                    process.kill(); process.communicate()
                    raise subprocess.TimeoutExpired(process.args, timeout)
                time.sleep(0.05)
            stdout, stderr = process.communicate()
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
            return stdout, stderr
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.communicate()
            raise

    try:
        run(["-i", str(source), "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", str(original_wav)])
        from pydub import AudioSegment
        with original_wav.open("rb") as stream:
            original = AudioSegment.from_file(stream, format="wav")
        replacements = validate_replacements(items, duration_ms=len(original))
        mixed = mix_replacements(original, replacements)
        with mixed_wav.open("wb") as stream:
            mixed.export(stream, format="wav")
            stream.flush(); os.fsync(stream.fileno())
        run(["-i", str(source), "-i", str(mixed_wav), "-map", "0:v:0", "-map", "1:a:0",
             "-c:v", "copy", "-c:a", "aac", "-map_metadata", "0", "-movflags", "+faststart",
             str(pending)])
        if not pending.is_file() or pending.stat().st_size <= 0:
            raise RuntimeError("recorded interaction output is empty")
        os.replace(pending, output)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        return {"output": str(output), "sha256": digest, "duration_ms": len(mixed),
                "replacement_count": len(replacements)}
    finally:
        with suppress(OSError):
            pending.unlink(missing_ok=True)
        shutil.rmtree(workspace, ignore_errors=True)
