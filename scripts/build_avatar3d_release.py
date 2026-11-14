#!/usr/bin/env python3
"""Package the built 3D preview, pinned CC0 sample, and local-only Node server."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'web' / 'dist'
SAMPLE_HASH = '63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c'


def main() -> None:
    if not (DIST / 'index.html').is_file():
        raise SystemExit('请先在 web 目录执行 npm run build。')
    sample = DIST / 'avatar-assets' / 'mpfb.glb'
    if not sample.is_file() or hashlib.sha256(sample.read_bytes()).hexdigest() != SAMPLE_HASH:
        raise SystemExit('构建目录中缺少正确的 CC0 人物。请先运行资源准备脚本，再重新构建。')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    output = ROOT / 'releases' / 'shuziren-avatar3d-v0.3-preview.zip'
    output.parent.mkdir(exist_ok=True)
    files = {}
    for source in sorted(DIST.rglob('*')):
        if source.is_symlink():
            raise SystemExit('构建目录存在符号链接，拒绝打包。')
        if source.is_file():
            files['app/' + source.relative_to(DIST).as_posix()] = source.read_bytes()
    files['start.mjs'] = (ROOT / 'scripts' / 'serve_avatar3d.mjs').read_bytes()
    files['start-mac.command'] = b'#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\nnode start.mjs --dir app\n'
    files['start-windows.cmd'] = b'@echo off\r\ncd /d "%~dp0"\r\nnode start.mjs --dir app\r\npause\r\n'
    files['START_HERE.txt'] = (ROOT / 'docs' / 'AVATAR3D_LOCAL.md').read_bytes()
    files['ASSET_LICENSE.md'] = (ROOT / 'docs' / 'AVATAR3D_ASSETS.md').read_bytes()
    files['THREE_LICENSE.txt'] = (ROOT / 'web' / 'node_modules' / 'three' / 'LICENSE').read_bytes()
    files['VUE_LICENSE.txt'] = (ROOT / 'web' / 'node_modules' / 'vue' / 'LICENSE').read_bytes()
    # HeadAudio is already included by the static-directory copy; do not duplicate
    # its modules, or bundle the upstream training/build dependencies.
    for notice in ('LICENSE', 'NOTICE.md'):
        if 'app/vendor/headaudio/' + notice not in files:
            raise SystemExit('构建目录缺少 HeadAudio 的许可或来源记录，请重新准备资源并构建。')
    manifest = {
        'version': '0.3.0-preview', 'source_revision': revision, 'source_dirty': dirty,
        'purpose': 'Local true-3D rendering and lip-sync evaluation, not production Taobao broadcasting',
        'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in files.items()},
    }
    files['MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo('shuziren-avatar3d-preview/' + name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name.endswith('.command') else 0o100644) << 16
            archive.writestr(info, data)
    print(json.dumps({'file': str(output), 'bytes': output.stat().st_size, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'source_revision': revision, 'source_dirty': dirty}, ensure_ascii=False))


if __name__ == '__main__':
    main()
