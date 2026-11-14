"""Console media runtime layout and required-file inventory."""
import argparse
import hashlib
import json
from pathlib import Path


MANIFEST_NAME = 'shuziren-runtime.json'
INDEPENDENT = {'version': 1, 'layout': 'shuziren-media-v1'}
INDEPENDENT_PYTHON = '_internal/env/Scripts/python.exe'
LEGACY_PYTHON = '_internal/env/python.exe'
MEDIA_FILES = (INDEPENDENT_PYTHON, '_internal/env/ffmpeg/bin/ffmpeg.exe',
               '_internal/env/ffmpeg/bin/ffprobe.exe')
MODEL_FILES = tuple('_internal/assets/pretrained_models/' + name for name in (
    'indextts/config.yaml', 'indextts/gpt.pth', 'indextts/dvae.pth', 'indextts/bigvgan_generator.pth',
    'indextts/bpe.model', 'indextts/checkpoints/bpe.model',
    'indextts/wetext/zh/tn/tagger.fst', 'indextts/wetext/zh/tn/verbalizer.fst',
    'indextts/wetext/en/tn/tagger.fst', 'indextts/wetext/en/tn/verbalizer.fst',
    'wenet/conf/train_conformer_multi_cn.yaml',
    'wenet/exp/conformer/wenetmodel.pt', 'image_infer_v2/unet_v2.onnx',
    'image_infer_v2/input_mask.npy', 'image_infer_v2/input_mask_re.npy',
    'face_detect/pfpld_robust_sim_bs1_8003.onnx', 'face_detect/scrfd_500m_bnkps_shape640x640.onnx',
))
PROVIDER_FILES = ('_internal/bin/voice_infer_v3/indextts/infer.py',
                  '_internal/bin/image_clone/wenet/compute_ctc_att_bnf.py')
ORIGIN_VIDEO_PROVIDER = 'bin/image_infer_v2/wenet'
ORIGIN_VIDEO_SILENCE = '_internal/assets/pretrained_models/image_infer_v2/silence.npy'
ORIGIN_VIDEO_FILES = (f'_internal/{ORIGIN_VIDEO_PROVIDER}/compute_ctc_att_bnf.py', ORIGIN_VIDEO_SILENCE)


def independent_runtime(root):
    manifest = Path(root) / MANIFEST_NAME
    if not manifest.exists():
        return False
    try:
        value = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ValueError('独立媒体运行目录清单无法读取') from error
    if (not isinstance(value, dict) or set(value) - (INDEPENDENT.keys() | {'python'})
            or any(value.get(key) != expected for key, expected in INDEPENDENT.items())
            or type(value.get('version')) is not int
            or value.get('python', INDEPENDENT_PYTHON) not in (INDEPENDENT_PYTHON, LEGACY_PYTHON)):
        raise ValueError('独立媒体运行目录清单版本无效')
    return value


def runtime_python(root):
    root = Path(root).resolve()
    manifest = independent_runtime(root)
    if manifest:
        return checked_path(root, manifest.get('python', INDEPENDENT_PYTHON))
    return root / LEGACY_PYTHON


def checked_path(root, relative):
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('独立媒体运行文件路径越界')
    return path


def inspect_runtime(root, *, include_origin_video=False):
    root = Path(root).resolve()
    manifest = independent_runtime(root)
    if not manifest:
        raise ValueError('缺少独立媒体运行目录清单')
    checks = []
    media = (manifest.get('python', INDEPENDENT_PYTHON), *MEDIA_FILES[1:])
    groups = [('environment', media), ('models', MODEL_FILES), ('providers', PROVIDER_FILES)]
    if include_origin_video:
        groups.append(('origin_video', ORIGIN_VIDEO_FILES))
    for group, files in groups:
        for name in files:
            try:
                present = checked_path(root, name).is_file()
            except (ValueError, OSError):
                present = False
            checks.append({'path': name, 'group': group, 'present': present})
    return {'layout': INDEPENDENT['layout'], 'checks': checks, 'ready': all(item['present'] for item in checks)}


def runtime_fingerprints(root, *, include_origin_video=False):
    root = Path(root).resolve()
    report = inspect_runtime(root, include_origin_video=include_origin_video)
    if not report['ready']:
        raise ValueError('独立媒体目录缺少必需文件')
    files = {}
    for item in report['checks']:
        path = checked_path(root, item['path'])
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        files[item['path']] = digest.hexdigest()
    return {'version': 1, 'layout': report['layout'], 'files': files}


def verify_fingerprints(root, expected):
    if not isinstance(expected, dict) or set(expected) != {'version', 'layout', 'files'} or (
            type(expected['version']) is not int or expected['version'] != 1
            or expected['layout'] != INDEPENDENT['layout'] or not isinstance(expected['files'], dict)):
        raise ValueError('媒体指纹清单格式无效')
    include_origin_video = any(name in expected['files'] for name in ORIGIN_VIDEO_FILES)
    actual = runtime_fingerprints(root, include_origin_video=include_origin_video)['files']
    if actual.keys() != expected['files'].keys():
        raise ValueError('媒体指纹清单与当前布局文件清单不一致')
    mismatches = [name for name, digest in actual.items() if digest != expected['files'][name]]
    return {'verified': not mismatches, 'files': len(actual), 'mismatches': mismatches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('initialize', 'check', 'fingerprint', 'verify'))
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--include-origin-video', action='store_true', help='Include direct video requirements in check or fingerprint')
    args = parser.parse_args()
    if args.include_origin_video and args.command not in ('check', 'fingerprint'):
        parser.error('--include-origin-video requires check or fingerprint')
    root = args.root.resolve()
    if args.command in ('fingerprint', 'verify'):
        if args.inventory is None:
            parser.error('--inventory is required')
        if args.command == 'fingerprint':
            inventory = runtime_fingerprints(root, include_origin_video=args.include_origin_video)
            with args.inventory.open('x', encoding='utf-8') as stream:
                json.dump(inventory, stream, indent=2)
            return 0
        expected = json.loads(args.inventory.read_text(encoding='utf-8'))
        result = verify_fingerprints(root, expected)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['verified'] else 1
    if args.command == 'initialize':
        root.mkdir(parents=True, exist_ok=True)
        with (root / MANIFEST_NAME).open('x', encoding='utf-8') as manifest:
            json.dump(INDEPENDENT, manifest, indent=2)
    result = inspect_runtime(root, include_origin_video=args.include_origin_video)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if args.command == 'initialize' or result['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
