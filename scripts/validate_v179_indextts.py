"""Run v179 IndexTTS with a locally generated Windows SAPI reference.

This is a candidate validator only.  It does not patch the reference package,
read its saved user voices, or publish audio.  Run it with the reference
product's primary ``_internal/env/python.exe`` so the product selects its own
validated CUDA/DeepSpeed path.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_sapi_streaming import powershell_command
from scripts.validate_tts_quality import character_error_rate
from scripts.v122_acceleration import configure_runtime


REFERENCE_TEXT = "欢迎来到数字人直播间，现在使用本机系统声音验证语音克隆技术链。"
SYNTHESIS_TEXTS = (
    "这是候选方案的本机语音生成验证，本次结果只用于技术测试。",
    "现在继续使用同一个模型实例生成第二句话，检查常驻复用是否正常。",
    "最后生成第三段不同文本，并确认没有错误复用上一段缓存。",
)


def wav_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as audio:
        return {
            "channels": audio.getnchannels(),
            "sample_width": audio.getsampwidth(),
            "sample_rate": audio.getframerate(),
            "frames": audio.getnframes(),
            "duration_seconds": audio.getnframes() / audio.getframerate(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--report-directory", required=True, type=Path)
    parser.add_argument("--voice", default="Microsoft Huihui Desktop")
    args = parser.parse_args()

    runtime = args.runtime_root.resolve(strict=True)
    report_directory = args.report_directory.resolve()
    report_directory.mkdir(parents=True, exist_ok=True)
    voice_directory = report_directory / "sapi-reference" / "windows-sapi"
    voice_directory.mkdir(parents=True, exist_ok=True)
    reference = voice_directory / "ref_audio.wav"
    (voice_directory / "ref_text.txt").write_text(REFERENCE_TEXT, encoding="utf-8")
    subprocess.run(powershell_command(reference, REFERENCE_TEXT, args.voice), check=True)

    internal = configure_runtime(runtime)
    from bin.voice_infer_v3.infer_api import VoiceSynthesizer
    import deepspeed
    import torch

    started = time.perf_counter()
    synthesizer = VoiceSynthesizer.from_voice_dir(
        str(internal / "assets/pretrained_models"),
        str(voice_directory.parent),
        voice_directory.name,
        device="cuda",
        voice_infer_version="v3",
    )
    initialization_seconds = time.perf_counter() - started
    outputs = []
    try:
        for index, text in enumerate(SYNTHESIS_TEXTS, 1):
            generated_at = time.perf_counter()
            source = synthesizer.synthesize(
                text, speed=1.0, language="zh-CN", use_cache=False
            )
            generation_seconds = time.perf_counter() - generated_at
            if not source or not Path(source).is_file():
                raise RuntimeError(f"v179 IndexTTS did not return audio for phrase {index}")
            output = report_directory / f"generated-{index}.wav"
            shutil.copy2(source, output)
            properties = wav_info(output)
            if properties["channels"] != 1 or properties["sample_width"] != 2:
                raise RuntimeError(f"unexpected generated WAV format: {properties}")
            if properties["duration_seconds"] <= 0 or output.stat().st_size <= 44:
                raise RuntimeError("generated WAV is empty")
            outputs.append({
                "index": index,
                "text": text,
                "generation_seconds": generation_seconds,
                **properties,
                "bytes": output.stat().st_size,
                "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            })
    finally:
        synthesizer.clear()

    if len({item["sha256"] for item in outputs}) != len(outputs):
        raise RuntimeError("distinct uncached phrases produced duplicate audio")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["MODELSCOPE_OFFLINE"] = "1"
    from recovered.funasr_runtime import (
        funasr_result_to_text,
        load_funasr_model,
        transcribe_with_funasr,
    )
    asr = load_funasr_model(
        str(internal / "assets/pretrained_models/asr"), prefer_fallback=True
    )
    for item in outputs:
        output = report_directory / f"generated-{item['index']}.wav"
        transcript = funasr_result_to_text(
            transcribe_with_funasr(asr, str(output), sentence_timestamp=False)
        )
        item["asr_transcript"] = transcript
        item["asr_cer"] = character_error_rate(item["text"], transcript)
    if any(item["asr_cer"] > 0.35 for item in outputs):
        raise RuntimeError("one or more generated phrases exceeded the 0.35 ASR CER gate")
    report = {
        "result": "passed",
        "scope": "v179 original IndexTTS using the primary bundled environment",
        "runtime_root": str(runtime),
        "reference": {
            "source": "Windows SAPI Microsoft Huihui Desktop",
            "authorization": "local operating-system synthetic voice; technical validation only",
            "text": REFERENCE_TEXT,
            "wav": wav_info(reference),
        },
        "persistent_instance": True,
        "use_cache": False,
        "runtime": {
            "python": str(Path(__import__("sys").executable).resolve()),
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "deepspeed": deepspeed.__version__,
            "reference_source_or_model_files_changed": False,
        },
        "initialization_seconds": initialization_seconds,
        "outputs": outputs,
        "unique_output_hashes": True,
        "asr_gate": {"engine": "bundled offline FunASR", "maximum_cer": 0.35, "passed": True},
        "human_listening_review": "not_performed",
    }
    (report_directory / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
