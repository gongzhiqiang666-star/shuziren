"""Recovered ASR dispatcher used while creating local voice references."""

from __future__ import annotations

from typing import List, Tuple

from .funasr_runtime import (cleanup_funasr_model, funasr_result_to_text,
                             load_funasr_model, transcribe_with_funasr)
from .whisper_runtime import (cleanup_whisper_model, load_whisper_model,
                              transcribe_with_whisper, whisper_result_to_text)


ASR_LANG_ZH = "zh"
ASR_LANG_OTHER = "other"


def normalize_asr_lang(asr_lang: str) -> str:
    value = str(asr_lang or ASR_LANG_ZH).strip().lower().replace("_", "-")
    return ASR_LANG_ZH if value in {"zh", "zh-cn", "zh-hans", "cn", "chinese"} else ASR_LANG_OTHER


def process_audio_batch(model_dir: str, audio_path_list: List[str],
                        asr_lang: str = ASR_LANG_ZH) -> List[Tuple[str, str]]:
    engine = normalize_asr_lang(asr_lang)
    model = None
    results = []
    try:
        if engine == ASR_LANG_ZH:
            model = load_funasr_model(model_dir)
            for audio_path in audio_path_list:
                result = transcribe_with_funasr(model, audio_path)
                results.append((audio_path, funasr_result_to_text(result).strip()))
        else:
            model = load_whisper_model(model_dir)
            for audio_path in audio_path_list:
                result = transcribe_with_whisper(model, audio_path, word_timestamps=False)
                results.append((audio_path, whisper_result_to_text(result).strip()))
        return results
    finally:
        if engine == ASR_LANG_ZH:
            cleanup_funasr_model(model)
        else:
            cleanup_whisper_model(model)
