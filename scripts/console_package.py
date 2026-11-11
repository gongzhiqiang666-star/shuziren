"""Build, verify and stage a Windows console source package from a Git revision."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
import re
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


MANIFEST = 'package-manifest.json'
ROOTS = {'scripts', 'recovered', 'packaging'}
SUFFIXES = {'.py', '.js', '.html', '.css', '.md', '.txt', '.yaml', '.json', '.cmd', '.ps1'}
REQUIRED = {'scripts/local_console.py', 'scripts/local-console/index.html', 'packaging/start-console.cmd',
            'packaging/requirements-console.txt', 'packaging/README.md'}
COMMIT_ID = re.compile(r'[0-9a-f]{40}(?:[0-9a-f]{24})?')


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
    manifest = {'version': 1, 'commit': commit, 'data_schema': 1,
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
            or not isinstance(manifest.get('commit'), str) or not COMMIT_ID.fullmatch(manifest['commit'])
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


def read_active(root):
    path = root / 'active.json'
    if not path.exists():
        return {'current': None, 'previous': None}
    state = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(state, dict) or set(state) != {'current', 'previous'} or any(
            value is not None and (not isinstance(value, str) or not COMMIT_ID.fullmatch(value))
            for value in state.values()):
        raise ValueError('Invalid installed version selection')
    return state


def write_active(root, state):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(root / 'active.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def check_release(root, commit):
    release = root / 'releases' / commit
    if release.resolve().parent != root / 'releases' or release.is_symlink():
        raise ValueError('Installed release is outside its version directory')
    manifest = json.loads((release / MANIFEST).read_text(encoding='utf-8'))
    files = manifest.get('files', {})
    if (manifest.get('commit') != commit or manifest.get('version') != 1 or manifest.get('data_schema', 1) != 1
            or not isinstance(files, dict) or not REQUIRED <= files.keys()):
        raise ValueError('Installed release is incompatible or incomplete')
    for name, expected in files.items():
        if not allowed(name):
            raise ValueError('Unsupported installed path')
        target = release.joinpath(*PurePosixPath(name).parts)
        if not target.resolve().is_relative_to(release.resolve()) or target.is_symlink() or digest(target.read_bytes()) != expected:
            raise ValueError(f'Installed file hash mismatch: {name}')
    return release, manifest


def console_command(data, port, python=None):
    command = [str(python or sys.executable), '-B', '-X', 'utf8', '-m', 'scripts.local_console', '--data-directory', str(data)]
    if port is not None:
        command.extend(('--port', str(port)))
    return command


def console_environment():
    return {**{key: value for key, value in os.environ.items() if key.upper() not in {'PYTHONPATH', 'PYTHONHOME'}},
            'PYTHONNOUSERSITE': '1'}


def configured_media(data):
    from scripts.local_console_config import ConfigStore
    from scripts.media_runtime import inspect_runtime, runtime_python

    config = ConfigStore(data).load()
    configured = config['runtime_root']
    if not configured or not inspect_runtime(configured)['ready']:
        raise ValueError('Configure a complete independent media runtime before starting with media')
    return config, runtime_python(configured)


def check_startup(release, root, media=None):
    with tempfile.TemporaryDirectory(prefix='.health-', dir=root) as temporary:
        data = Path(temporary)
        expected_runtime = ''
        python = None
        if media is not None:
            from scripts.local_console_config import ConfigStore

            config, python = media
            expected_runtime = config['runtime_root']
            ConfigStore(data).save(config)
        child = subprocess.Popen(console_command(data, 0, python), cwd=release, env=console_environment(),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        line = Queue(maxsize=1)
        reader = threading.Thread(target=lambda: line.put(child.stdout.readline().strip()), daemon=True)
        reader.start()
        try:
            try:
                address = line.get(timeout=15)
            except Empty as error:
                raise RuntimeError('Candidate startup timed out') from error
            if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}/', address):
                raise RuntimeError('Candidate did not publish a local console address')
            with urlopen(address + 'api/state', timeout=5) as response:
                state = json.load(response)
                if state['config']['runtime_root'] != expected_runtime or state['config']['version'] != 1:
                    raise RuntimeError('Candidate did not load the expected isolated configuration')
            if media is not None:
                with urlopen(address + 'api/live/devices', timeout=5) as response:
                    if not isinstance(json.load(response).get('devices'), list):
                        raise RuntimeError('Candidate did not enumerate media devices')
            request = Request(address + 'api/shutdown', data=b'{"confirm":true}', headers={
                'Content-Type': 'application/json', 'Origin': address.rstrip('/'), 'X-Console-Token': state['token']})
            with urlopen(request, timeout=5):
                pass
            if child.wait(timeout=10):
                raise RuntimeError('Candidate console did not exit cleanly')
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
            reader.join(timeout=5)
            child.stdout.close()


def switch_release(root, archive=None, with_media=False):
    from scripts.local_console import InstanceLock

    root = root.resolve()
    with InstanceLock(root / '.deployment'), InstanceLock(root / 'data'):
        media = configured_media(root / 'data') if with_media else None
        active = read_active(root)
        if archive is None:
            commit = active['previous']
            if commit is None:
                raise ValueError('No previous release is available')
        else:
            with ZipFile(archive) as package:
                manifest = read_package(package)
            if manifest.get('data_schema', 1) != 1:
                raise ValueError('Package requires an unsupported user-data schema')
            commit = manifest['commit']
            release = root / 'releases' / commit
            if not release.exists():
                install(archive, release)
            if check_release(root, commit)[1] != manifest:
                raise ValueError('This commit already has a different installed manifest')
        if commit != active['current']:
            release, _ = check_release(root, commit)
            check_startup(release, root, media)
            active = {'current': commit, 'previous': active['current']}
            write_active(root, active)
        return active


def run_release(root, port, with_media=False):
    from scripts.local_console import InstanceLock

    root = root.resolve()
    with InstanceLock(root / '.deployment'):
        commit = read_active(root)['current']
        if commit is None:
            raise ValueError('Install a release first')
        release, _ = check_release(root, commit)
        data = root / 'data'
        python = configured_media(data)[1] if with_media else None
        return subprocess.call(console_command(data, port, python), cwd=release, env=console_environment())


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
    for name in ('deploy', 'rollback', 'run'):
        command = commands.add_parser(name)
        command.add_argument('--root', required=True, type=Path)
        command.add_argument('--with-media', action='store_true')
        if name == 'deploy':
            command.add_argument('--archive', required=True, type=Path)
        if name == 'run':
            command.add_argument('--port', type=int)
    migration = commands.add_parser('migrate-data')
    migration.add_argument('--root', type=Path, required=True)
    migration.add_argument('--source', type=Path, required=True)
    legacy = commands.add_parser('migrate-v122-assets')
    legacy.add_argument('--root', type=Path, required=True)
    legacy.add_argument('--runtime', type=Path, required=True)
    legacy.add_argument('--voice', type=Path, action='append', default=[])
    legacy.add_argument('--avatar', type=Path, action='append', default=[])
    legacy.add_argument('--products', type=Path)
    legacy_products = commands.add_parser('migrate-v122-products')
    legacy_products.add_argument('--root', type=Path, required=True)
    legacy_products.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'migrate-v122-products':
        from scripts.console_data_migration import migrate_v122_products
        print(json.dumps(migrate_v122_products(args.root, args.source), ensure_ascii=False))
        return 0
    if args.command == 'migrate-v122-assets':
        from scripts.console_data_migration import migrate_v122_assets
        print(json.dumps(migrate_v122_assets(args.root, args.runtime, args.voice, args.avatar, args.products), ensure_ascii=False))
        return 0
    if args.command == 'migrate-data':
        from scripts.console_data_migration import migrate_data
        print(json.dumps(migrate_data(args.source, args.root), ensure_ascii=False))
        return 0
    if args.command == 'run':
        return run_release(args.root, args.port, args.with_media)
    if args.command in {'deploy', 'rollback'}:
        print(json.dumps(switch_release(args.root, getattr(args, 'archive', None), args.with_media)))
        return 0
    if args.command == 'build':
        manifest = build(args.output, args.revision)
    elif args.command == 'install':
        manifest = install(args.archive, args.destination)
    else:
        with ZipFile(args.archive) as package:
            manifest = read_package(package)
    print(json.dumps({'status': 'ok', 'commit': manifest['commit'], 'files': len(manifest['files'])}))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (BadZipFile, OSError, ValueError) as error:
        print(f'Console package operation failed: {error}', file=sys.stderr)
        raise SystemExit(1) from None
