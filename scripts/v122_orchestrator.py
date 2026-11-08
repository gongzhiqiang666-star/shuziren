"""Stage-by-stage first-proof orchestration with no shell invocation."""

import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path

try:
    from scripts.v122_proof import normalization_command, parse_ffprobe, validate_audio_probe, validate_video_probe
except ImportError:
    from v122_proof import normalization_command, parse_ffprobe, validate_audio_probe, validate_video_probe


STAGES = ("materials", "avatar", "voice", "tts", "drive", "mp4")


class StageError(RuntimeError):
    def __init__(self, stage, code, detail=""):
        super().__init__(code + (": " + detail if detail else "")); self.stage = stage; self.code = code


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def _execute(stage, command, runner):
    started = time.time()
    result = runner(command, cwd=None, capture_output=True, text=True, shell=False)
    if result.returncode:
        detail = str(getattr(result, "stderr", ""))[-1000:]
        raise StageError(stage, "V122_" + stage.upper() + "_FAILED", detail)
    return round(time.time() - started, 3)


def _probe(stage, ffprobe, path, runner):
    command = [str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    result = runner(command, cwd=None, capture_output=True, text=True, shell=False)
    if result.returncode: raise StageError(stage, "V122_FFPROBE_FAILED", str(result.stderr)[-1000:])
    try: return parse_ffprobe(json.loads(result.stdout))
    except (ValueError, TypeError) as error: raise StageError(stage, "V122_FFPROBE_INVALID", str(error))


def run_pipeline(package_root, state, adapter, ffmpeg, runner=subprocess.run, on_update=None):
    root = Path(package_root).resolve(); run_dir = root / "runs" / Path(state["run_id"]).name
    outputs = run_dir / "outputs"; outputs.mkdir(parents=True, exist_ok=True)
    def update(stage, status, error="", seconds=None):
        value = {"status": status, "error": error}
        if seconds is not None: value["seconds"] = seconds
        state["stages"][stage] = value
        if on_update: on_update(state)
    try:
        update("materials", "running")
        person_source = run_dir / state["materials"]["person"]["path"]
        voice_source = run_dir / state["materials"]["voice"]["path"]
        person = run_dir / "materials/person-normalized.mp4"; voice = run_dir / "materials/voice-normalized.wav"
        _execute("materials", normalization_command(ffmpeg, person_source, person, "person"), runner)
        _execute("materials", normalization_command(ffmpeg, voice_source, voice, "voice"), runner)
        if not person.is_file() or not voice.is_file(): raise StageError("materials", "MAT_CONVERT_OUTPUT_MISSING")
        ffprobe = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix)
        try: validate_video_probe(_probe("materials", ffprobe, person, runner)); validate_audio_probe(_probe("materials", ffprobe, voice, runner))
        except Exception as error:
            if isinstance(error, StageError): raise
            raise StageError("materials", str(error))
        update("materials", "passed")
        model_id = "person-" + uuid.uuid4().hex[:12]; voice_id = "voice-" + uuid.uuid4().hex[:12]
        update("avatar", "running"); seconds = _execute("avatar", adapter.avatar_preprocess(person, "第一阶段人物", model_id), runner); update("avatar", "passed", seconds=seconds)
        transcript = state["text"]["reference_transcript"]
        update("voice", "running"); seconds = _execute("voice", adapter.voice_create(voice, transcript, "第一阶段音色", voice_id), runner); update("voice", "passed", seconds=seconds)
        marked = state["text"]["new_script"].strip() + "。验证编号" + uuid.uuid4().hex[:6]
        wav = outputs / "generated.wav"; before = wav.stat().st_mtime_ns if wav.exists() else 0
        update("tts", "running"); seconds = _execute("tts", adapter.speech_generate(voice_id, transcript, marked, wav), runner)
        if not wav.is_file() or not wav.stat().st_size or wav.stat().st_mtime_ns <= before: raise StageError("tts", "V122_TTS_OUTPUT_NOT_FRESH")
        wav_hash = _sha256(wav); update("tts", "passed", seconds=seconds)
        raw_video = outputs / "avatar-video.mp4"
        update("drive", "running"); seconds = _execute("drive", adapter.avatar_drive(model_id, wav, raw_video), runner)
        if not raw_video.is_file() or not raw_video.stat().st_size: raise StageError("drive", "V122_DRIVE_OUTPUT_MISSING")
        update("drive", "passed", seconds=seconds)
        final = outputs / "final.mp4"; update("mp4", "running")
        mux = [str(ffmpeg), "-nostdin", "-v", "error", "-y", "-i", str(raw_video), "-i", str(wav),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", str(final)]
        seconds = _execute("mp4", mux, runner)
        if not final.is_file() or not final.stat().st_size: raise StageError("mp4", "V122_MP4_OUTPUT_MISSING")
        if not _probe("mp4", ffprobe, final, runner).get("has_audio_video"):
            raise StageError("mp4", "V122_MP4_STREAMS_MISSING")
        state["outputs"] = {"wav": "/api/media/generated.wav", "mp4": "/api/media/final.mp4",
                            "wav_sha256": wav_hash, "drive_wav_sha256": wav_hash,
                            "model_id": model_id, "voice_id": voice_id, "final_text": marked}
        update("mp4", "passed", seconds=seconds); return state
    except StageError as error:
        update(error.stage, "failed", error.code); return state
