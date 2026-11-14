"""Validate the staged original-video WeNet provider on an actual CPU model."""

import argparse
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from scripts.v122_acceleration import configure_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--audio', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    runtime = args.runtime_root.resolve(strict=True)
    audio = args.audio.resolve(strict=True)
    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    internal = configure_runtime(runtime)

    import numpy as np
    import torch
    from bin.image_infer_v2.wenet.compute_ctc_att_bnf import get_weget, load_ppg_model

    model_root = internal / 'assets/pretrained_models'
    config = model_root / 'wenet/conf/train_conformer_multi_cn.yaml'
    weights = model_root / 'wenet/exp/conformer/wenetmodel.pt'
    started = time.perf_counter()
    model = load_ppg_model(str(config), str(weights), 'cpu')
    loaded = time.perf_counter()
    model_devices = sorted({str(parameter.device) for parameter in model.parameters()})
    features = np.asarray(get_weget(str(audio), model, 560000))
    from recovered.image_infer_audio import extract_audio_features
    product_manager = SimpleNamespace(
        wenet_model=str(weights), wenet_conf_path=str(config),
        wenet_model_path=str(weights), device='cpu',
    )
    aligned = extract_audio_features(product_manager, str(audio))
    ended = time.perf_counter()
    if model_devices != ['cpu']:
        raise RuntimeError(f'WeNet model escaped CPU: {model_devices}')
    if features.ndim != 2 or features.shape[0] < 21 or not np.isfinite(features).all():
        raise RuntimeError(f'invalid WeNet features: {features.shape}')
    if not aligned or any(np.asarray(window).shape != (20, 256) for window in aligned):
        raise RuntimeError('product feature alignment did not produce 20x256 windows')
    product_devices = sorted({str(parameter.device) for parameter in product_manager.wenet_model.parameters()})
    if product_devices != ['cpu']:
        raise RuntimeError(f'product WeNet model escaped CPU: {product_devices}')
    report = {
        'passed': True,
        'device': 'cpu',
        'model_devices': model_devices,
        'feature_shape': list(features.shape),
        'product_aligned_windows': len(aligned),
        'product_window_shape': list(np.asarray(aligned[0]).shape),
        'product_model_devices': product_devices,
        'finite': True,
        'nonzero': bool(np.any(features)),
        'model_load_seconds': loaded - started,
        'feature_seconds': ended - loaded,
        'audio_sha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
        'feature_sha256': hashlib.sha256(features.tobytes()).hexdigest(),
        'torch_version': torch.__version__,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
