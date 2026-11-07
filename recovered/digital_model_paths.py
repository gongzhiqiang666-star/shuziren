"""Resolve the packaged model assets used by digital-human inference."""

from pathlib import Path


def resolve_digital_model_paths(config, runtime_dir):
    runtime_dir = Path(runtime_dir)
    base = Path(str(config.get("models_base_path") or "assets/pretrained_models").replace("\\", "/"))
    if not base.is_absolute():
        base = runtime_dir / base

    assets = {
        "wenet_conf_path": ("wenet_config", "wenet/conf/train_conformer_multi_cn.yaml"),
        "wenet_model_path": ("wenet_model", "wenet/exp/conformer/wenetmodel.pt"),
        "silence_feature_path": ("silence_feature_path", "image_infer_v2/silence.npy"),
        "model_path": ("image_infer_v2_weights_path", "image_infer_v2/unet_v2.onnx"),
    }
    resolved = {}
    for key, (setting, default) in assets.items():
        configured = config.get(setting)
        if key == "model_path":
            configured = configured or config.get("unet_v2_model")
        path = Path(str(configured or default).replace("\\", "/"))
        if not path.is_absolute():
            runtime_path = runtime_dir / path
            path = runtime_path if configured and runtime_path.is_file() else base / path
        if not path.is_file():
            raise FileNotFoundError(f"数字人模型文件不存在：{path}")
        resolved[key] = str(path)
    return resolved


def resolve_character_dir(config, runtime_dir, model_id):
    base = Path(str(config.get("image_base_dir") or "assets/characters/images").replace("\\", "/"))
    if not base.is_absolute():
        base = Path(runtime_dir) / base
    if not model_id or model_id in {".", ".."} or "/" in model_id or "\\" in model_id:
        raise ValueError("数字人形象 ID 无效")
    directory = (base / model_id).resolve()
    if directory.parent != base.resolve() or not directory.is_dir():
        raise FileNotFoundError(f"数字人形象目录不存在：{directory}")
    return str(directory)
