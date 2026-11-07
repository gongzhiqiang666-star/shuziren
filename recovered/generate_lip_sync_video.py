"""Recovered short-video orchestration around image_infer_v2."""

from __future__ import annotations

import importlib
import shutil
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from .short_video_audio_synthesis import synthesize_text_to_audio


def _get_project_root() -> str:
    return str(Path(__file__).resolve().parent.parent)


def _resolve_config_path(value: str, project_root: str) -> Path:
    path = Path(str(value or "")).expanduser()
    return path.resolve() if path.is_absolute() else (Path(project_root) / path).resolve()


def _resolve_model_dir(model_id: str, config: Dict[str, Any]) -> Tuple[str, str]:
    project_root = str(config.get("project_root") or _get_project_root())
    image_base_dir = _resolve_config_path(config.get("image_base_dir", "assets/characters/images"), project_root)
    model_dir = image_base_dir / str(model_id)
    if not model_dir.is_dir():
        raise FileNotFoundError(f"数字人模型不存在: {model_dir}")
    info_path = model_dir / "video_info.yaml"
    info = yaml.safe_load(info_path.read_text(encoding="utf-8")) if info_path.is_file() else {}
    configured = (info or {}).get("model_path") or config.get("unet_v2_model") or config.get("image_infer_v2_weights_path")
    if not configured:
        raise ValueError("未配置 image_infer_v2 模型权重")
    model_path = _resolve_config_path(configured, project_root)
    if not model_path.is_file():
        raise FileNotFoundError(f"推理模型不存在: {model_path}")
    return str(model_dir), str(model_path)


def _resolve_voice_assets(voice_id: str, config: Dict[str, Any]) -> Tuple[str, str, str]:
    project_root = str(config.get("project_root") or _get_project_root())
    voice_base_dir = _resolve_config_path(config.get("voice_base_dir", "assets/characters/voices"), project_root)
    voice_model_dir = voice_base_dir / str(voice_id)
    reference_audio_path = voice_model_dir / "ref_audio.wav"
    reference_text_path = voice_model_dir / "ref_text.txt"
    if not reference_audio_path.is_file():
        raise FileNotFoundError(f"缺少参考音频: {reference_audio_path}")
    if not reference_text_path.is_file():
        raise FileNotFoundError(f"缺少参考文本: {reference_text_path}")
    return str(voice_model_dir), str(reference_audio_path), reference_text_path.read_text(encoding="utf-8").strip()


def _generate_silent_audio(output_path: str, duration_seconds: float) -> str:
    if duration_seconds <= 0:
        raise ValueError("静音时长必须大于零")
    sample_rate = 24000
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\0\0" * round(sample_rate * duration_seconds))
    return str(output_path)


def _render_pencil_art_short_video(model_dir: str, audio_path: str, output_path: str,
                                   config_params: Dict[str, Any]) -> str:
    infer_api = importlib.import_module("bin.image_infer_v2.infer_api")
    manager = infer_api.VideoStreamManager(
        data_dir=model_dir,
        wenet_conf_path=config_params["wenet_conf_path"],
        wenet_model_path=config_params["wenet_model_path"],
        model_path=config_params["model_path"],
        silence_feature_path=config_params.get("silence_feature_path"),
        window_width=int(config_params.get("window_width", 1280)),
        window_height=int(config_params.get("window_height", 720)),
        buffer_threshold=int(config_params.get("buffer_threshold", 25)),
        device=str(config_params.get("device", "cuda:0")),
        batch_size=int(config_params.get("batch_size", 4)),
        image_output_mode="video",
        input_mode="file",
        enable_action_generalization=bool(config_params.get("enable_action_generalization", False)),
    )
    try:
        result = manager.process_single_file(audio_path, output_path=output_path)
        rendered = result if isinstance(result, str) else output_path
        if not Path(rendered).is_file():
            raise RuntimeError("数字人口型渲染未生成视频")
        return str(rendered)
    finally:
        manager.stop_playing()


def create_short_video(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    try:
        project_root = str(config.get("project_root") or _get_project_root())
        model_id = str(data.get("model_id") or "").strip()
        if not model_id:
            raise ValueError("model_id 不能为空")
        model_dir, model_path = _resolve_model_dir(model_id, config)
        short_video_id = str(data.get("short_video_id") or uuid.uuid4())
        output_base_dir = _resolve_config_path(
            data.get("custom_output_dir") or config.get("video_output_dir", "short_videos"), project_root
        )
        output_dir = output_base_dir / short_video_id
        output_dir.mkdir(parents=True, exist_ok=True)
        mode = str(data.get("mode") or "text").lower()
        if mode == "audio":
            source_audio = Path(str(data.get("audio_path") or ""))
            if source_audio.is_file():
                audio_path = str(source_audio.resolve())
            else:
                audio_path = _generate_silent_audio(str(output_dir / "silent.wav"),
                                                    float(data.get("silent_duration", 3.0)))
        elif mode == "text":
            voice_id = str(data.get("voice_id") or "").strip()
            _, reference_audio, reference_text = _resolve_voice_assets(voice_id, config)
            synthesis_result = synthesize_text_to_audio(
                text=str(data.get("text") or ""), speed=float(data.get("speed", 1.0)),
                language=str(data.get("language") or "zh-CN"), scene="short_video",
                voice_id=voice_id, reference_audio=reference_audio, reference_text=reference_text,
                config=dict(config, voice_infer_version=data.get("voice_infer_version") or
                            config.get("voice_infer_version")), project_root=project_root,
                use_cache=bool(data.get("use_cache", True)),
            )
            audio_path = synthesis_result["audio_path"]
        else:
            raise ValueError(f"不支持的短视频模式: {mode}")
        config_params = {
            "model_path": model_path,
            "wenet_conf_path": str(_resolve_config_path(config.get("wenet_config"), project_root)),
            "wenet_model_path": str(_resolve_config_path(config.get("wenet_model"), project_root)),
            "silence_feature_path": str(_resolve_config_path(config.get("image_infer_v2_silence_path"), project_root))
                if config.get("image_infer_v2_silence_path") else None,
            "enable_action_generalization": bool(data.get(
                "enable_action_generalization", config.get("enable_action_generalization", False)
            )),
            **{key: config[key] for key in ("window_width", "window_height", "buffer_threshold", "device", "batch_size") if key in config},
        }
        video_output_file = output_dir / "video.mp4"
        video_path = _render_pencil_art_short_video(model_dir, audio_path,
                                                     str(video_output_file), config_params)
        video_info = {
            "id": short_video_id,
            "name": str(data.get("name") or short_video_id),
            "model_id": model_id,
            "mode": mode,
            "video_path": video_path,
            "audio_path": audio_path,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        (output_dir / "video_info.yaml").write_text(
            yaml.safe_dump(video_info, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        return {"success": True, "short_video_id": short_video_id,
                "video_path": video_path, "audio_path": audio_path,
                "output_dir": str(output_dir), "video_info": video_info}
    except Exception as error:
        return {"success": False, "error": str(error)}


generate_lip_sync_video = create_short_video
