"""Recovered API wrapper that returns synthesized preview audio as base64."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict

from .short_video_audio_synthesis import synthesize_text_to_audio


def generate_audio(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    try:
        voice_id = str(data.get("voice_id") or "").strip()
        if not voice_id:
            raise ValueError("voice_id 不能为空")
        project_root = str(config.get("project_root") or Path.cwd())
        voice_base_dir = Path(config.get("voice_base_dir") or
                              Path(project_root) / "assets/characters/voices")
        voice_model_dir = voice_base_dir / voice_id
        reference_audio_path = voice_model_dir / "ref_audio.wav"
        reference_text_path = voice_model_dir / "ref_text.txt"
        if not reference_audio_path.is_file():
            raise FileNotFoundError(f"'ref_audio.wav' not found in {voice_model_dir}")
        if not reference_text_path.is_file():
            raise FileNotFoundError(f"'ref_text.txt' not found in {voice_model_dir}")
        synthesis_result = synthesize_text_to_audio(
            text=str(data.get("text") or ""), speed=float(data.get("speed", 1.0)),
            language=str(data.get("language") or "zh-CN"), scene="short_video",
            voice_id=voice_id, reference_audio=str(reference_audio_path),
            reference_text=reference_text_path.read_text(encoding="utf-8").strip(),
            config=dict(config, voice_infer_version=data.get("voice_infer_version") or
                        config.get("voice_infer_version")), project_root=project_root,
            use_cache=bool(data.get("use_cache", True)),
        )
        audio_file = Path(synthesis_result["audio_path"])
        return {"success": True, **synthesis_result,
                "audio_data": "data:audio/wav;base64," + base64.b64encode(audio_file.read_bytes()).decode("ascii")}
    except Exception as error:
        return {"success": False, "error": str(error)}
