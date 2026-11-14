"""Dispatch local voice synthesis to the matching inference module."""

from importlib import import_module

MODULES = {
    "v1": "bin.voice_infer.infer_api",
    "v2": "bin.voice_infer_v2.infer_api",
    "v3": "bin.voice_infer_v3.infer_api",
    # Product routing uses the already validated resident OmniVoice provider
    # for Southeast Asian languages. The recovered F5 service clients remain
    # importable compatibility adapters, but are not an undeclared runtime
    # dependency of the product path.
    "malai_local": "bin.voice_infer_v2.infer_api",
    "vietnam_local": "bin.voice_infer_v2.infer_api",
}

DEFAULT_LANGUAGES = {"malai_local": "ms-MY", "vietnam_local": "vi-VN"}


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
        return synthesizer.synthesize(
            text=text, speed=speed, language=DEFAULT_LANGUAGES.get(version))
    finally:
        synthesizer.clear()
