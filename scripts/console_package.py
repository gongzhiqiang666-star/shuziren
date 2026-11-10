"""Build, verify and stage a Windows console source package from a Git revision."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


MANIFEST = 'package-manifest.json'
ROOTS = {'scripts', 'recovered', 'packaging'}
SUFFIXES = {'.py', '.js', '.html', '.css', '.md', '.txt', '.yaml', '.json', '.cmd', '.ps1'}
REQUIRED = {'scripts/local_console.py', 'scripts/local-console/index.html', 'packaging/start-console.cmd',
            'packaging/requirements-console.txt', 'packaging/README.md'}


def allowed(name):
    path = PurePosixPath(name)
    if not path.parts or path.as_posix() != name or path.parts[0] not in ROOTS or path.suffix not in SUFFIXES:
        return False
    if path.parts[:2] in {('scripts', 'v122-proof'), ('scripts', 'fixtures')}:
        return False
    for part in path.parts:
        if (part in {'.', '..'} or part.endswith(('.', ' ')) or re.search(r'[<>:"\\|?*\x00-\x1f]', part)
                or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])', part.split('.')[0])):
            return False
    return True


def digest(data):
    return hashlib.sha256(data).hexdigest()


def zip_entry(name, data, archive):
    info = ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    archive.writestr(info, data)


def build(output, revision='HEAD'):
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', revision+'^{commit}'], text=True).strip()
    tracked = subprocess.check_output(['git', 'archive', '--format=zip', commit, *sorted(ROOTS)])
    with ZipFile(io.BytesIO(tracked)) as source:
        files = {item.filename: source.read(item) for item in source.infolist() if not item.is_dir() and allowed(item.filename)}
    if not REQUIRED <= files.keys():
        raise ValueError('Revision lacks required console package files')
    manifest = {'version': 1, 'commit': commit,
                'files': {name: digest(data) for name, data in sorted(files.items())}}
    with ZipFile(output, 'x') as archive:
        for name, data in sorted(files.items()):
            zip_entry(name, data, archive)
        zip_entry(MANIFEST, json.dumps(manifest, indent=2).encode(), archive)
    return manifest


def read_package(archive):
    entries = archive.infolist()
    names = [item.filename for item in entries]
    if len(names) != len(set(name.casefold() for name in names)) or MANIFEST not in names:
        raise ValueError('Missing manifest or duplicate paths')
    if sum(item.file_size for item in entries) > 64 * 1024 * 1024:
        raise ValueError('Source package exceeds size budget')
    if any(not allowed(name) for name in names if name != MANIFEST):
        raise ValueError('Unsupported package path')
    manifest = json.loads(archive.read(MANIFEST))
    files = manifest.get('files') if isinstance(manifest, dict) else None
    if (not isinstance(files, dict) or manifest.get('version') != 1 or not REQUIRED <= files.keys()
            or not isinstance(manifest.get('commit'), str) or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', manifest['commit'])
            or set(files) != set(names) - {MANIFEST}):
        raise ValueError('Package contents disagree with manifest')
    for name, expected in files.items():
        if digest(archive.read(name)) != expected:
            raise ValueError(f'Package file hash mismatch: {name}')
    return manifest


def install(archive, destination):
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Choose an unused install directory: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as package:
        manifest = read_package(package)
        with tempfile.TemporaryDirectory(prefix='.shuziren-stage-', dir=destination.parent) as temporary:
            stage = Path(temporary) / 'app'
            stage.mkdir()
            for name in (*manifest['files'], MANIFEST):
                target = stage.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(package.read(name))
            stage.rename(destination)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    builder = commands.add_parser('build')
    builder.add_argument('--output', required=True, type=Path)
    builder.add_argument('--revision', default='HEAD')
    for name in ('verify', 'install'):
        command = commands.add_parser(name)
        command.add_argument('--archive', required=True, type=Path)
        if name == 'install':
            command.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'build':
        manifest = build(args.output, args.revision)
    elif args.command == 'install':
        manifest = install(args.archive, args.destination)
    else:
        with ZipFile(args.archive) as package:
            manifest = read_package(package)
    print(json.dumps({'status': 'ok', 'commit': manifest['commit'], 'files': len(manifest['files'])}))


if __name__ == '__main__':
    main()
