"""Recovered local voice-reference preparation API."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .voice_clone_asr import process_audio_batch


def _resolve_ffmpeg_executable() -> str:
    configured = os.environ.get("FFMPEG_HOME", "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_dir():
            candidate = candidate / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not found:
        raise FileNotFoundError("PATH 或 FFMPEG_HOME 中未找到 ffmpeg")
    return found


def _subprocess_startupinfo():
    if os.name != "nt" or not hasattr(subprocess, "STARTUPINFO"):
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def _save_manifest(exp_dir: str, results: list) -> None:
    manifest_path = Path(exp_dir, "slice_manifest.json")
    with manifest_path.open("w", encoding="utf-8") as stream:
        json.dump(results, stream, ensure_ascii=False, indent=2)


def _export_reference_audio(source_path: str, target_path: str) -> None:
    source, target = Path(source_path), Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".wav":
        shutil.copy2(source, target)
        return
    subprocess.run([_resolve_ffmpeg_executable(), "-y", "-i", str(source), "-ac", "1",
                    "-ar", "16000", "-c:a", "pcm_s16le", str(target)],
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                   startupinfo=_subprocess_startupinfo())


def _replace_directory_with_retry(source: Path, target: Path) -> None:
    """Rename a prepared directory after Windows media handles finish closing."""
    for attempt in range(30):
        try:
            source.replace(target)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 29:
                raise
            time.sleep(0.1)


def clone_voice_local(audio_path: str, voice_name: str, output_dir: str,
                      asr_weight_path: str, asr_lang: str = "zh") -> str:
    source = Path(audio_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() not in {".wav", ".mp3"}:
        raise ValueError("仅支持 wav/mp3 格式")
    clean_name = Path(str(voice_name).strip()).name
    if not clean_name or clean_name in {".", ".."}:
        raise ValueError("声音名称不能为空")
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    exp_dir = output_root / clean_name
    transaction = uuid.uuid4().hex
    staging = output_root / f".{clean_name}.pending-{transaction}"
    backup = output_root / f".{clean_name}.backup-{transaction}"
    staging.mkdir()
    try:
        normalized_audio_path = staging / "normalized_input.wav"
        command = [_resolve_ffmpeg_executable(), "-y", "-i", str(source), "-vn", "-ac", "1",
                   "-ar", "16000", "-c:a", "pcm_s16le", str(normalized_audio_path)]
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              startupinfo=_subprocess_startupinfo(), timeout=300, check=False)
        if proc.returncode:
            raise RuntimeError("ffmpeg 音频标准化失败: " + proc.stderr.decode(errors="replace")[-1000:])
        asr_results = process_audio_batch(asr_weight_path, [str(normalized_audio_path)], asr_lang)
        valid_results = [
            {"audio_path": recognized_path, "text": clean_text.strip()}
            for recognized_path, clean_text in asr_results
            if clean_text.strip()
        ]
        if not valid_results:
            raise RuntimeError("ASR 未识别到有效文本")
        selected = max(valid_results, key=lambda item: len(item.get("text")))
        manifest_results = []
        for item in valid_results:
            recognized = Path(item["audio_path"])
            published = exp_dir / recognized.relative_to(staging) if recognized.is_relative_to(staging) else recognized
            manifest_results.append({"audio_path": str(published), "text": item["text"]})
        _save_manifest(str(staging), manifest_results)
        _export_reference_audio(selected["audio_path"], str(staging / "ref_audio.wav"))
        (staging / "ref_text.txt").write_text(selected["text"], encoding="utf-8")
        if exp_dir.exists():
            _replace_directory_with_retry(exp_dir, backup)
        try:
            _replace_directory_with_retry(staging, exp_dir)
        except Exception:
            if backup.exists() and not exp_dir.exists():
                _replace_directory_with_retry(backup, exp_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return str(exp_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists() and not exp_dir.exists():
            _replace_directory_with_retry(backup, exp_dir)
