"""Dispatch local voice synthesis to the matching inference module."""

from importlib import import_module

MODULES = {
    "v1": "bin.voice_infer.infer_api",
    "v2": "bin.voice_infer_v2.infer_api",
    "v3": "bin.voice_infer_v3.infer_api",
    "malai_local": "bin.voice_infer_malai_local.infer_api",
    "vietnam_local": "bin.voice_infer_vietnam_local.infer_api",
}


def synthesize_local_audio(main_config, voice_id, text, speed, version="v1"):
    synthesizer_type = import_module(MODULES[version]).VoiceSynthesizer
    synthesizer = synthesizer_type.from_voice_dir(
        models_base_path=main_config.get("models_base_path", "assets/pretrained_models"),
        voice_base_dir=main_config["voice_base_dir"],
        voice_id=voice_id,
        device=main_config.get("device", "cuda"),
        voice_infer_version=version,
    )
    try:
        return synthesizer.synthesize(text=text, speed=speed)
    finally:
        synthesizer.clear()
