"""Recovered OpenAI Whisper loading, transcription, and result conversion."""

from __future__ import annotations

import gc
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


WHISPER_MODEL_DIR_NAME = "whisper"
WHISPER_MODEL_NAME = "large-v3"
WHISPER_PUNCTUATION_PROMPT = "请准确识别语音内容，并保留自然的句号、逗号、问号和感叹号。For non-Chinese speech, keep natural punctuation in the target language."
SENTENCE_PUNCTUATION = "。.!！？?；;"


def resolve_whisper_model_path(asr_weight_path: str) -> Path:
    base_path = Path(asr_weight_path)
    model_dir = base_path / WHISPER_MODEL_DIR_NAME
    preferred_path = model_dir / f"{WHISPER_MODEL_NAME}.pt"
    legacy_path = base_path / f"{WHISPER_MODEL_NAME}.pt"
    if preferred_path.is_file():
        return preferred_path
    if legacy_path.is_file():
        return legacy_path
    model_dir.mkdir(parents=True, exist_ok=True)
    return preferred_path


def load_whisper_model(asr_weight_path: str):
    try:
        import whisper
    except ImportError as error:
        raise RuntimeError("未安装 openai-whisper") from error
    model_path = resolve_whisper_model_path(asr_weight_path)
    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
    except ImportError:
        pass
    if model_path.exists():
        print(f"加载 Whisper 模型: {model_path}")
        return whisper.load_model(str(model_path), device=device)
    print(f"Whisper 模型不存在，自动下载到: {model_path}")
    return whisper.load_model(
        WHISPER_MODEL_NAME,
        device=device,
        download_root=str(model_path.parent),
    )


def transcribe_with_whisper(model: Any, audio_path: str, *, word_timestamps: bool = True) -> Dict[str, Any]:
    fp16 = False
    try:
        import torch
        fp16 = torch.cuda.is_available()
    except ImportError:
        pass
    return model.transcribe(
        audio_path, task="transcribe", fp16=fp16, verbose=False,
        word_timestamps=word_timestamps, initial_prompt=WHISPER_PUNCTUATION_PROMPT,
    )


def cleanup_whisper_model(model: Optional[Any]) -> None:
    del model
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def clean_whisper_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = re.sub(r"\s+([，,。.!?！？；;：:])", r"\1", cleaned)
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", cleaned)


def _has_sentence_punctuation(text: str) -> bool:
    return clean_whisper_text(text).endswith(tuple(SENTENCE_PUNCTUATION))


def _default_sentence_end(text: str) -> str:
    cleaned = clean_whisper_text(text)
    if not cleaned or _has_sentence_punctuation(cleaned):
        return cleaned
    return cleaned + ("。" if re.search(r"[\u4e00-\u9fff]", cleaned) else ".")


def _segments_to_punctuated_text(result: Dict[str, Any]) -> str:
    joined = ""
    for segment in result.get("segments") or []:
        punctuated = _default_sentence_end(segment.get("text") or "")
        if not punctuated:
            continue
        if (not joined or
                (re.search(r"[\u4e00-\u9fff]$", joined)
                 and re.search(r"^[\u4e00-\u9fff]", punctuated))):
            joined += punctuated
        else:
            joined += " " + punctuated
    return clean_whisper_text(joined)


def whisper_result_to_text(result: Dict[str, Any]) -> str:
    text = clean_whisper_text(result.get("text") or "")
    if not text:
        return ""
    if _has_sentence_punctuation(text):
        return text
    if result.get("segments"):
        punctuated = _segments_to_punctuated_text(result)
        if punctuated:
            return punctuated
    return _default_sentence_end(text)


def whisper_result_to_sentence_info(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    sentences: List[Dict[str, Any]] = []
    current_text = ""
    current_start: Optional[float] = None
    current_end: Optional[float] = None

    def flush() -> None:
        nonlocal current_text, current_start, current_end
        text = clean_whisper_text(current_text)
        if text and current_start is not None and current_end is not None:
            sentences.append({
                "start": int(max(current_start, 0) * 1000),
                "end": int(max(current_end, current_start) * 1000),
                "text": text,
            })
        current_text = ""
        current_start = None
        current_end = None

    for segment in result.get("segments") or []:
        segment_start = float(segment.get("start") or 0)
        segment_end = float(segment.get("end") or segment_start)
        words = segment.get("words") or []

        if words:
            for word in words:
                word_text = clean_whisper_text(word.get("word") or "")
                if not word_text:
                    continue
                word_start = float(word.get("start") or segment_start)
                word_end = float(word.get("end") or word_start)
                if current_text and current_end is not None and word_start - current_end >= 8.0:
                    flush()
                if current_start is None:
                    current_start = word_start
                current_end = word_end
                current_text += word_text
                if (_has_sentence_punctuation(current_text)
                        or len(clean_whisper_text(current_text)) >= 80):
                    flush()
        else:
            segment_text = clean_whisper_text(segment.get("text") or "")
            if not segment_text:
                continue
            if current_text and current_end is not None and segment_start - current_end >= 8.0:
                flush()
            if current_start is None:
                current_start = segment_start
            current_end = segment_end
            current_text += segment_text
            if (_has_sentence_punctuation(current_text)
                    or len(clean_whisper_text(current_text)) >= 80):
                flush()

    flush()
    return sentences
