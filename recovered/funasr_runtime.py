"""Recovered shared FunASR model lifecycle used by ASR and audio clipping."""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any, Dict, List, Optional


FUNASR_ASR_DIR_NAME = "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
FUNASR_ASR_FALLBACK_DIR_NAME = "speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
FUNASR_VAD_DIR_NAME = "speech_fsmn_vad_zh-cn-16k-common-pytorch"
FUNASR_PUNC_DIR_NAME = "punc_ct-transformer_zh-cn-common-vocab272727-pytorch"


def resolve_funasr_model_paths(asr_weight_path: str) -> Dict[str, Path]:
    base_path = Path(asr_weight_path).expanduser().resolve()
    if not base_path.is_dir():
        raise FileNotFoundError(f"FunASR 模型目录不存在: {base_path}")
    paths = {
        "asr": base_path / FUNASR_ASR_DIR_NAME,
        "fallback": base_path / FUNASR_ASR_FALLBACK_DIR_NAME,
        "vad": base_path / FUNASR_VAD_DIR_NAME,
        "punc": base_path / FUNASR_PUNC_DIR_NAME,
    }
    missing = [name for name in ("vad", "punc") if not paths[name].is_dir()]
    if not paths["asr"].is_dir() and not paths["fallback"].is_dir():
        missing.append("asr")
    if missing:
        raise FileNotFoundError("缺少 FunASR 模型: " + ", ".join(missing))
    return paths


def load_funasr_model(asr_weight_path: str, *, prefer_fallback: bool = False):
    try:
        from funasr import AutoModel
    except ImportError as error:
        raise RuntimeError("未安装 funasr") from error
    model_paths = resolve_funasr_model_paths(asr_weight_path)
    primary = model_paths["fallback"] if prefer_fallback else model_paths["asr"]
    if not primary.is_dir():
        primary = model_paths["fallback"] if model_paths["fallback"].is_dir() else model_paths["asr"]
    kwargs = {
        "model": str(primary),
        "vad_model": str(model_paths["vad"]),
        "punc_model": str(model_paths["punc"]),
        "disable_update": True,
        "disable_pbar": True,
    }
    try:
        import torch
        kwargs["device"] = "cuda:0" if torch.cuda.is_available() else "cpu"
    except ImportError:
        kwargs["device"] = "cpu"
    print(f"加载 FunASR: asr={primary}, vad={model_paths['vad']}, punc={model_paths['punc']}")
    return AutoModel(**kwargs)


def transcribe_with_funasr(model: Any, audio_path: str, **generate_kwargs: Any) -> List[Dict[str, Any]]:
    if model is None:
        raise ValueError("FunASR 模型不能为空")
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    options = {"input": str(path), "batch_size_s": 300, "sentence_timestamp": True}
    options.update(generate_kwargs)
    result = model.generate(**options)
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


def funasr_result_to_text(result: List[Dict[str, Any]]) -> str:
    return "".join(str(item.get("text") or "") for item in result or []).strip()


def cleanup_funasr_model(model: Optional[Any]) -> None:
    if model is not None:
        for method_name in ("close", "cleanup"):
            method = getattr(model, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
    del model
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
