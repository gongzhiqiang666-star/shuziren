"""Construct the packaged image-inference runtime from recovered parameters."""

from importlib import import_module
from pathlib import Path

from .digital_model_paths import resolve_character_dir, resolve_digital_model_paths


def create_image_runtime(config, runtime_dir, params):
    assets = resolve_digital_model_paths(config, runtime_dir)
    common = {
        **assets,
        "window_width": params["window_width"],
        "window_height": params["window_height"],
        "device": config.get("device") or "cuda:0",
        "image_output_mode": params["image_output_mode"],
        "is_interrupt": params["is_interrupt"],
        "video_path_for_driving": params["video_path_for_driving"],
        "enable_occluder": params["enable_occluder"],
        "occluder_model_path": params["occluder_model_path"],
    }
    face_dir = config.get("face_model_dir")
    if face_dir:
        common["face_model_dir"] = str(Path(runtime_dir) / face_dir)
    else:
        packaged_faces = Path(runtime_dir) / (config.get("models_base_path") or "assets/pretrained_models") / "face_detect"
        if packaged_faces.is_dir():
            common["face_model_dir"] = str(packaged_faces)
    if params["origin_idle_video_mode"]:
        module = import_module(".bin.image_infer_origin_frame.infer_api", __package__)
        return module.VideoStreamManager(**common)

    data_dir = ""
    if params["model_id"]:
        data_dir = resolve_character_dir(config, runtime_dir, params["model_id"])
    module = import_module(".bin.image_infer_v2.infer_api", __package__)
    return module.VideoStreamManager(
        **common,
        data_dir=data_dir,
        input_mode=params["input_mode"],
        camera_index=params["camera_index"],
        camera_resolution=params["camera_resolution"],
        rtmp_url_for_driving=params["rtmp_url_for_driving"],
        enable_action_generalization=params["enable_action_generalization"],
        auth_token=config.get("token") or "",
    )
