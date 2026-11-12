"""Copy authorized local media components into an unused independent directory."""
import argparse
import json
from pathlib import Path
import shutil
import stat
import subprocess

from scripts.media_runtime import (
    INDEPENDENT, LEGACY_PYTHON, MANIFEST_NAME, MEDIA_FILES, MODEL_FILES, PROVIDER_FILES,
    inspect_runtime, runtime_python,
)


ENV_DIRS = ('DLLs', 'Lib', 'Library', 'CUDA', 'ffmpeg', 'nltk_data', 'share', 'include', 'libs', 'conda-meta', 'etc')
PROVIDERS = ('bin/voice_infer_v3/indextts', 'bin/image_clone/wenet')
ZIPVOICE_PROVIDER = 'bin/voice_infer/zipvoice'
OMNIVOICE_PROVIDER = 'bin/voice_infer_v2/omnivoice'
ORIGIN_VIDEO_PROVIDER = 'bin/image_infer_v2/wenet'


def reparse(path):
    return bool(getattr(path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) or path.is_symlink()


def ignore_caches(directory, names):
    return [name for name in names if name.startswith('._') or name in {'__pycache__', '.git'}
            or name.endswith(('.pyc', '.pyo', '.pdb')) or reparse(Path(directory) / name)]


def ignore_provider(directory, names):
    excluded = ignore_caches(directory, names)
    return excluded + [name for name in names if name not in excluded and (Path(directory) / name).is_file()
                       and Path(name).suffix.lower() not in {'.py', '.txt', '.json', '.yaml', '.yml'}]


def stage(reference, destination, *, include_zipvoice=False, include_omnivoice=False, include_origin_video=False):
    reference = reference.resolve(strict=True)
    destination = destination.resolve()
    if destination.is_relative_to(reference) or reference.is_relative_to(destination):
        raise ValueError('Source and destination must be separate directories')
    source = reference / '_internal'
    required = (LEGACY_PYTHON, *MEDIA_FILES[1:], *MODEL_FILES, *PROVIDER_FILES)
    if include_zipvoice:
        required += (f'_internal/{ZIPVOICE_PROVIDER}/bin/infer_zipvoice.py',)
    if include_omnivoice:
        required += (f'_internal/{OMNIVOICE_PROVIDER}/models/omnivoice.py',)
    if include_origin_video:
        required += (f'_internal/{ORIGIN_VIDEO_PROVIDER}/compute_ctc_att_bnf.py',)
    for name in required:
        path = reference / name
        if not path.is_file() or not path.resolve().is_relative_to(source.resolve()) or reparse(path):
            raise ValueError(f'Reference media component is missing or outside source: {name}')
    destination.mkdir(parents=True, exist_ok=False)
    internal = destination / '_internal'
    environment = internal / 'env'
    environment.mkdir(parents=True)

    def copy_tree(relative, ignore):
        base = source / relative
        if not base.resolve().is_relative_to(source.resolve()) or reparse(base):
            raise ValueError(f'Reference component escapes source: {relative}')
        shutil.copytree(base, internal / relative, ignore=ignore)

    source_env = source / 'env'
    for name in ENV_DIRS:
        if (source_env / name).is_dir():
            copy_tree('env/' + name, ignore_caches)
    for path in source_env.iterdir():
        is_runtime_file = path.name == 'python.exe' or path.suffix.lower() == '.dll'
        if is_runtime_file and not path.name.startswith('._') and not reparse(path) and path.is_file():
            shutil.copy2(path, environment / path.name)
    (internal / 'bin').mkdir()
    (internal / 'bin/__init__.py').write_text('', encoding='utf-8')
    for relative in PROVIDERS:
        copy_tree(relative, ignore_provider)
    if include_zipvoice:
        copy_tree(ZIPVOICE_PROVIDER, ignore_provider)
    if include_omnivoice:
        copy_tree(OMNIVOICE_PROVIDER, ignore_provider)
    if include_origin_video:
        copy_tree(ORIGIN_VIDEO_PROVIDER, ignore_provider)
    for name in MODEL_FILES:
        original = reference / name
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    (destination / MANIFEST_NAME).write_text(json.dumps({**INDEPENDENT, 'python': LEGACY_PYTHON}, indent=2), encoding='utf-8')
    report = inspect_runtime(destination)
    probe = subprocess.run([str(runtime_python(destination)), '-I', '-c',
        'import sys,json; print(json.dumps({"version":list(sys.version_info[:3]),"prefix":sys.prefix}))'],
        check=True, capture_output=True, text=True, timeout=30, cwd=destination)
    python = json.loads(probe.stdout)
    if Path(python['prefix']).resolve() != environment.resolve() or not report['ready']:
        raise ValueError('Copied interpreter or required inputs failed verification')
    result = {'scope': 'locally-staged-components', 'inference_verified': False, 'python': python, **report}
    (destination / 'staging-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--include-zipvoice', action='store_true',
                        help='Stage ZipVoice Python sources; supply its model root separately')
    parser.add_argument('--include-omnivoice', action='store_true',
                        help='Stage OmniVoice Python sources; supply its model root separately')
    parser.add_argument('--include-origin-video', action='store_true',
                        help='Stage the WeNet provider required for direct local video driving')
    args = parser.parse_args()
    result = stage(args.reference, args.destination, include_zipvoice=args.include_zipvoice,
                   include_omnivoice=args.include_omnivoice, include_origin_video=args.include_origin_video)
    print(json.dumps({'ready': result['ready'], 'python': result['python'], 'checks': len(result['checks'])}))


if __name__ == '__main__':
    main()
