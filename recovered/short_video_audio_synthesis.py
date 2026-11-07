"""Recovered shared text-to-audio pipeline for short videos and IP agents."""

from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List


MIN_TTS_SEGMENT_CHARS = 20
MAX_TTS_SEGMENT_CHARS = 100


def resolve_voice_version(scene: str, language: str) -> str:
    normalized_scene = str(scene or "short_video").strip().lower()
    normalized_language = str(language or "zh-CN").strip().lower().replace("_", "-")
    if normalized_scene == "ip_agent":
        return "v3"
    if normalized_scene == "short_video":
        return "v2" if normalized_language.startswith(("zh", "chinese")) else "v3"
    return "v1"


def normalize_tts_language(language: str, voice_infer_version: str) -> str:
    value = str(language or "zh-CN").strip().lower().replace("_", "-")
    aliases = {
        "zh": "zh-CN", "zh-cn": "zh-CN", "zh-hans": "zh-CN", "zh-sg": "zh-CN",
        "zh-tw": "zh-TW", "zh-hant": "zh-TW", "en": "en-US", "english": "en-US",
        "en-us": "en-US", "en-gb": "en-GB", "fr": "fr-FR", "french": "fr-FR",
        "fr-fr": "fr-FR", "de": "de-DE", "german": "de-DE", "de-de": "de-DE",
        "es": "es-ES", "spanish": "es-ES", "es-es": "es-ES",
        "it": "it-IT", "italian": "it-IT", "it-it": "it-IT",
        "pt": "pt-PT", "portuguese": "pt-PT", "pt-pt": "pt-PT", "pt-br": "pt-BR",
        "ru": "ru-RU", "russian": "ru-RU", "ru-ru": "ru-RU",
        "ja": "ja-JP", "japanese": "ja-JP", "ja-jp": "ja-JP",
        "ko": "ko-KR", "korean": "ko-KR", "ko-kr": "ko-KR",
        "chinese": "zh-CN",
    }
    normalized = aliases.get(value, language or "zh-CN")
    if voice_infer_version == "v1":
        return "zh-CN" if str(normalized).lower().startswith("zh") else "en-US"
    return str(normalized)


def _split_sentence_units(text: str) -> List[str]:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return [part.strip() for part in re.findall(r".*?[。！？!?；;\n]+|.+$", value) if part.strip()]


def split_text_for_tts(text: str, min_chars: int = MIN_TTS_SEGMENT_CHARS,
                       max_chars: int = MAX_TTS_SEGMENT_CHARS) -> List[str]:
    if min_chars <= 0 or max_chars < min_chars:
        raise ValueError("无效的 TTS 分段长度")
    segments, current = [], ""
    for unit in _split_sentence_units(text):
        while len(unit) > max_chars:
            if current:
                segments.append(current); current = ""
            segments.append(unit[:max_chars]); unit = unit[max_chars:]
        if current and len(current) + len(unit) > max_chars:
            segments.append(current); current = ""
        current += unit
        if len(current) >= min_chars and current[-1:] in "。！？!?；;":
            segments.append(current); current = ""
    if current:
        if segments and len(current) < min_chars and len(segments[-1]) + len(current) <= max_chars:
            segments[-1] += current
        else:
            segments.append(current)
    return segments


def _concat_audio_files(audio_paths: List[str], output_path: str) -> str:
    if not audio_paths:
        raise ValueError("没有可合并的音频")
    if len(audio_paths) == 1:
        shutil.copy2(audio_paths[0], output_path)
        return output_path
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg")
    list_path = Path(output_path).with_name("_audio_concat.txt")
    list_path.write_text("".join(f"file '{str(Path(path).resolve()).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n"
                                     for path in audio_paths), encoding="utf-8")
    try:
        result = subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
                                 "-c:a", "pcm_s16le", str(output_path)], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError("ffmpeg 音频合并失败: " + result.stderr[-1000:])
    finally:
        list_path.unlink(missing_ok=True)
    return output_path


def synthesize_text_to_audio(*, text: str, speed: float, language: str, scene: str,
                             voice_id: str, reference_audio: str, reference_text: str,
                             config: Dict[str, Any], project_root: str,
                             use_cache: bool = True) -> Dict[str, str]:
    if not str(text or "").strip():
        raise ValueError("合成文本不能为空")
    version = str(config.get("voice_infer_version") or
                  resolve_voice_version(scene, language)).lower()
    module_name = {"v1": "bin.voice_infer.infer_api", "v2": "bin.voice_infer_v2.infer_api",
                   "v3": "bin.voice_infer_v3.infer_api"}.get(version)
    if not module_name:
        raise ValueError(f"不支持的语音推理版本: {version}")
    synthesizer_cls = importlib.import_module(module_name).VoiceSynthesizer
    models_base_path = config.get("models_base_path") or str(Path(project_root) / "assets/pretrained_models")
    synthesizer = synthesizer_cls(models_base_path, reference_audio, reference_text,
                                  device=config.get("device", "cuda"), voice_id=voice_id,
                                  voice_infer_version=version)
    synthesis_language = normalize_tts_language(language, version)
    output_dir = Path(tempfile.gettempdir()) / "short_video"
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_paths = []
    try:
        for index, segment in enumerate(split_text_for_tts(text)):
            audio_path = synthesizer.synthesize(text=segment, speed=float(speed),
                                                language=synthesis_language, use_cache=use_cache)
            if not audio_path or not Path(audio_path).is_file():
                raise RuntimeError(f"第 {index + 1} 段语音合成失败")
            audio_paths.append(str(audio_path))
        final_audio_path = output_dir / f"{uuid.uuid4().hex}_merged.wav"
        _concat_audio_files(audio_paths, str(final_audio_path))
        return {"audio_path": str(final_audio_path), "voice_infer_version": version,
                "language": synthesis_language}
    finally:
        clear = getattr(synthesizer, "clear", None)
        if callable(clear):
            clear()
