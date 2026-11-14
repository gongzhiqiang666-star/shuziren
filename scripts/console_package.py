"""Build, verify and stage a Windows console source package from a Git revision."""
import argparse
from contextlib import closing, ExitStack
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
import uuid
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


# Keep the documented ``python scripts/console_package.py ...`` form isolated
# from unrelated third-party packages that also use the top-level name scripts.
if __package__ in (None, ''):
    repository_root = str(Path(__file__).resolve().parent.parent)
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)


MANIFEST = 'package-manifest.json'
ROOTS = {'scripts', 'recovered', 'packaging'}
SUFFIXES = {'.py', '.js', '.html', '.css', '.md', '.txt', '.yaml', '.json', '.cmd', '.ps1'}
REQUIRED = {'scripts/local_console.py', 'scripts/local-console/index.html', 'packaging/start-console.cmd',
            'packaging/requirements-console.txt', 'packaging/README.md'}
COMMIT_ID = re.compile(r'[0-9a-f]{40}(?:[0-9a-f]{24})?')
BACKUP_ID = re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}')
CURRENT_DATA_SCHEMA = 1
DATA_SCHEMA_STATE = 'data-schema.json'


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
    manifest = {'version': 1, 'commit': commit, 'data_schema': CURRENT_DATA_SCHEMA,
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
            or type(manifest.get('data_schema')) is not int or manifest['data_schema'] < 1
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


def read_data_schema(root, active=None):
    root = Path(root)
    path = root / DATA_SCHEMA_STATE
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError('Installed data schema state is unreadable') from error
        if (not isinstance(state, dict) or set(state) != {'version'}
                or type(state['version']) is not int or state['version'] < 1):
            raise ValueError('Invalid installed data schema state')
        return state['version']
    active = read_active(root) if active is None else active
    if active.get('current') is not None:
        return check_release(root.resolve(), active['current'])[1]['data_schema']
    return None


def write_data_schema(root, version):
    if type(version) is not int or version < 1:
        raise ValueError('Invalid data schema version')
    root = Path(root)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'version': version}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(root / DATA_SCHEMA_STATE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _reparse(path):
    return path.is_symlink() or bool(
        getattr(path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def create_data_backup(root, current_commit, target_commit):
    """Create an immutable, self-verifying snapshot before a release switch."""
    root = Path(root).resolve()
    source = root / 'data'
    if not source.exists():
        return None
    if not source.is_dir() or _reparse(source):
        raise ValueError('Managed data directory is unsafe')
    backup_root = root / 'backups'
    if backup_root.exists() and (not backup_root.is_dir() or _reparse(backup_root)):
        raise ValueError('Backup directory is unsafe')
    backup_root.mkdir(parents=True, exist_ok=True)
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex
    final = backup_root / identifier
    with tempfile.TemporaryDirectory(prefix='.backup-', dir=backup_root) as temporary:
        stage = Path(temporary) / 'snapshot'
        target = stage / 'data'
        target.mkdir(parents=True)
        records = {}
        for directory, names, files in os.walk(source, followlinks=False):
            directory = Path(directory)
            relative_directory = directory.relative_to(source)
            for name in list(names):
                candidate = directory / name
                if _reparse(candidate):
                    raise ValueError(f'Linked data directory cannot be backed up: {candidate}')
                (target / relative_directory / name).mkdir(parents=True, exist_ok=True)
            for name in files:
                original = directory / name
                relative = (relative_directory / name).as_posix()
                if name == 'console.lock' or name.endswith(('.sqlite3-wal', '.sqlite3-shm')):
                    continue
                if not original.is_file() or _reparse(original):
                    raise ValueError(f'Linked or irregular data file cannot be backed up: {original}')
                copied = target.joinpath(*PurePosixPath(relative).parts)
                copied.parent.mkdir(parents=True, exist_ok=True)
                if name.endswith('.sqlite3'):
                    with closing(sqlite3.connect(original.as_uri() + '?mode=ro', uri=True)) as existing:
                        with closing(sqlite3.connect(copied)) as snapshot:
                            existing.backup(snapshot)
                            if snapshot.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                                raise ValueError(f'Backup database failed integrity check: {relative}')
                else:
                    before = hashlib.sha256(original.read_bytes()).hexdigest()
                    shutil.copy2(original, copied)
                    if hashlib.sha256(original.read_bytes()).hexdigest() != before:
                        raise ValueError(f'Data file changed during backup: {relative}')
                payload = copied.read_bytes()
                records[relative] = {'size': len(payload), 'sha256': digest(payload),
                                     'kind': 'sqlite' if name.endswith('.sqlite3') else 'file'}
        metadata = {
            'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'current_commit': current_commit, 'target_commit': target_commit,
            'data_schema': read_data_schema(root) or CURRENT_DATA_SCHEMA,
            'files': dict(sorted(records.items())),
        }
        (stage / 'backup-manifest.json').write_bytes(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode('utf-8') + b'\n')
        stage.rename(final)
    return final


def verify_data_backup(root, backup_id):
    root = Path(root).resolve()
    if not isinstance(backup_id, str) or BACKUP_ID.fullmatch(backup_id) is None:
        raise ValueError('Invalid backup identifier')
    backup = root / 'backups' / backup_id
    if not backup.is_dir() or _reparse(backup) or backup.resolve().parent != (root / 'backups').resolve():
        raise ValueError('Backup does not exist or is unsafe')
    manifest_path = backup / 'backup-manifest.json'
    if not manifest_path.is_file() or _reparse(manifest_path) or manifest_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Backup manifest is missing or unsafe')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Backup manifest is unreadable') from error
    records = manifest.get('files') if isinstance(manifest, dict) else None
    schema = manifest.get('data_schema', 1) if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or manifest.get('version') != 1 or not isinstance(records, dict)
            or type(schema) is not int or schema < 1
            or COMMIT_ID.fullmatch(str(manifest.get('current_commit', ''))) is None
            or COMMIT_ID.fullmatch(str(manifest.get('target_commit', ''))) is None):
        raise ValueError('Unsupported backup manifest')
    data = backup / 'data'
    if not data.is_dir() or _reparse(data):
        raise ValueError('Backup data directory is missing or unsafe')
    actual = set()
    for directory, names, files in os.walk(data, followlinks=False):
        directory = Path(directory)
        for name in names:
            if _reparse(directory / name):
                raise ValueError('Backup contains a linked directory')
        for name in files:
            candidate = directory / name
            if not candidate.is_file() or _reparse(candidate):
                raise ValueError('Backup contains an unsafe file')
            actual.add(candidate.relative_to(data).as_posix())
    if actual != set(records):
        raise ValueError('Backup contents disagree with manifest')
    for relative, record in records.items():
        path = PurePosixPath(relative)
        if (not path.parts or path.is_absolute() or '..' in path.parts or not isinstance(record, dict)
                or type(record.get('size')) is not int or record['size'] < 0
                or record.get('kind') not in {'file', 'sqlite'}):
            raise ValueError(f'Invalid backup record: {relative}')
        expected = record.get('sha256')
        candidate = data.joinpath(*path.parts)
        payload = candidate.read_bytes()
        if (not isinstance(expected, str) or len(expected) != 64
                or record['size'] != len(payload) or digest(payload) != expected):
            raise ValueError(f'Backup file hash mismatch: {relative}')
        if record['kind'] == 'sqlite':
            with closing(sqlite3.connect(candidate.as_uri() + '?mode=ro', uri=True)) as database:
                if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError(f'Backup database failed integrity check: {relative}')
    return backup, {**manifest, 'data_schema': schema}


def _verify_restored_copy(directory, manifest):
    expected = manifest['files']
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    if actual != set(expected):
        raise ValueError('Staged restore contents disagree with manifest')
    for relative, record in expected.items():
        candidate = directory.joinpath(*PurePosixPath(relative).parts)
        payload = candidate.read_bytes()
        if len(payload) != record['size'] or digest(payload) != record['sha256']:
            raise ValueError(f'Staged restore hash mismatch: {relative}')
        if record['kind'] == 'sqlite':
            with closing(sqlite3.connect(candidate.as_uri() + '?mode=ro', uri=True)) as database:
                if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError(f'Staged restore database is corrupt: {relative}')


def restore_data_backup(root, backup_id):
    """Restore a verified backup while retaining a safety snapshot of current data."""
    from scripts.local_console import InstanceLock

    root = Path(root).resolve()
    with InstanceLock(root / '.deployment'), ExitStack() as running:
        for directory in (root / '.running').iterdir() if (root / '.running').is_dir() else ():
            if not directory.is_dir() or directory.resolve() != directory:
                raise ValueError('Invalid managed instance lock directory')
            running.enter_context(InstanceLock(directory))
        # Probe direct/manual instances. Release these file handles before the
        # directory swap; the deployment and managed-instance locks stay held.
        probes = ExitStack()
        try:
            if (root / 'data').is_dir():
                probes.enter_context(InstanceLock(root / 'data'))
                for directory in (root / 'data/shops').glob('shop-*'):
                    if directory.is_dir() and directory.resolve() == directory:
                        probes.enter_context(InstanceLock(directory))
        finally:
            probes.close()
        backup, manifest = verify_data_backup(root, backup_id)
        active = read_active(root)
        installed_schema = read_data_schema(root, active) or CURRENT_DATA_SCHEMA
        if manifest['data_schema'] != installed_schema:
            raise ValueError('Backup data schema is incompatible with the installed release')
        current = active['current'] or '0' * 40
        safety = create_data_backup(root, current, current)
        with tempfile.TemporaryDirectory(prefix='.restore-', dir=root) as temporary:
            temporary = Path(temporary)
            staged = temporary / 'data-new'
            shutil.copytree(backup / 'data', staged)
            _verify_restored_copy(staged, manifest)
            old = temporary / 'data-old'
            data = root / 'data'
            replaced = False
            try:
                if data.exists():
                    data.rename(old)
                staged.rename(data)
                replaced = True
            except Exception:
                if not data.exists() and old.exists():
                    old.rename(data)
                raise
            if not replaced:
                raise RuntimeError('Data restore did not complete')
        return {'status': 'ok', 'backup': backup_id,
                'safety_backup': safety.name if safety is not None else None,
                'files': len(manifest['files'])}


def check_release(root, commit):
    release = root / 'releases' / commit
    if release.resolve().parent != root / 'releases' or release.is_symlink():
        raise ValueError('Installed release is outside its version directory')
    manifest = json.loads((release / MANIFEST).read_text(encoding='utf-8'))
    files = manifest.get('files', {})
    if (manifest.get('commit') != commit or manifest.get('version') != 1
            or type(manifest.get('data_schema')) is not int or manifest['data_schema'] < 1
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
    return {**{key: value for key, value in os.environ.items()
               if key.upper() not in {'PYTHONPATH', 'PYTHONHOME', 'SHUZIREN_MANAGED_SHOP_ID',
                                      'SHUZIREN_MANAGED_ACCESS_ROLE', 'SHUZIREN_MANAGED_ACCOUNT_ID'}},
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
    with InstanceLock(root / '.deployment'), ExitStack() as instances:
        instances.enter_context(InstanceLock(root / 'data'))
        for directory in (root / '.running').iterdir() if (root / '.running').is_dir() else ():
            if not directory.is_dir() or directory.resolve() != directory:
                raise ValueError('Invalid managed instance lock directory')
            instances.enter_context(InstanceLock(directory))
        for directory in (root / 'data' / 'shops').glob('shop-*'):
            if directory.is_dir() and directory.resolve() == directory:
                instances.enter_context(InstanceLock(directory))
        media = configured_media(root / 'data') if with_media else None
        active = read_active(root)
        installed_schema = read_data_schema(root, active)
        if archive is None:
            commit = active['previous']
            if commit is None:
                raise ValueError('No previous release is available')
        else:
            with ZipFile(archive) as package:
                manifest = read_package(package)
            commit = manifest['commit']
            release = root / 'releases' / commit
            if not release.exists():
                install(archive, release)
            if check_release(root, commit)[1] != manifest:
                raise ValueError('This commit already has a different installed manifest')
        if commit != active['current']:
            release, release_manifest = check_release(root, commit)
            candidate_schema = release_manifest['data_schema']
            if installed_schema is None:
                if candidate_schema != CURRENT_DATA_SCHEMA:
                    raise ValueError('Fresh installation requires the current supported data schema')
            elif candidate_schema != installed_schema:
                raise ValueError('No data migration path exists between installed and candidate schemas')
            check_startup(release, root, media)
            if active['current'] is not None:
                create_data_backup(root, active['current'], commit)
            active = {'current': commit, 'previous': active['current']}
            if installed_schema is None:
                write_data_schema(root, candidate_schema)
            write_active(root, active)
        return active


def run_release(root, port, with_media=False, shop_id=None, access_role='admin', account_id='local'):
    from scripts.local_console import InstanceLock
    from scripts.local_console_config import shop_data_directory

    if access_role not in ('viewer', 'operator', 'admin'):
        raise ValueError('Invalid managed access role')
    if not isinstance(account_id, str) or re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}', account_id) is None:
        raise ValueError('Invalid managed account id')
    root = root.resolve()
    with ExitStack() as instance:
        with InstanceLock(root / '.deployment'):
            commit = read_active(root)['current']
            if commit is None:
                raise ValueError('Install a release first')
            release, manifest = check_release(root, commit)
            installed_schema = read_data_schema(root, {'current': commit, 'previous': None})
            if manifest['data_schema'] != installed_schema:
                raise ValueError('Installed release cannot open the current user-data schema')
            data = root / 'data'
            if shop_id is not None:
                data = shop_data_directory(data, shop_id)
                if not data.is_relative_to(root):
                    raise ValueError('Shop data directory must be inside the managed installation')
            lease = root / '.running' / (data.name if shop_id is not None else 'default')
            if lease.resolve() != lease:
                raise ValueError('Invalid managed instance lock directory')
            instance.enter_context(InstanceLock(lease))
            python = configured_media(data)[1] if with_media else None
        environment = console_environment()
        if shop_id is not None:
            environment['SHUZIREN_MANAGED_SHOP_ID'] = shop_id
        environment['SHUZIREN_MANAGED_ACCESS_ROLE'] = access_role
        environment['SHUZIREN_MANAGED_ACCOUNT_ID'] = account_id
        return subprocess.call(console_command(data, port, python), cwd=release, env=environment)


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
            command.add_argument('--shop-id', help='使用独立的店铺数据目录')
            command.add_argument('--access-role', choices=('viewer', 'operator', 'admin'), default='admin',
                                 help='当前本机入口的访问角色')
            command.add_argument('--account-id', default='local', help='写入本店权限审计的账号编号')
    migration = commands.add_parser('migrate-data')
    migration.add_argument('--root', type=Path, required=True)
    migration.add_argument('--source', type=Path, required=True)
    migration.add_argument('--shop-id', help='将源数据迁移到独立的店铺目录')
    legacy = commands.add_parser('migrate-v122-assets')
    legacy.add_argument('--root', type=Path, required=True)
    legacy.add_argument('--runtime', type=Path, required=True)
    legacy.add_argument('--voice', type=Path, action='append', default=[])
    legacy.add_argument('--avatar', type=Path, action='append', default=[])
    legacy.add_argument('--products', type=Path)
    legacy.add_argument('--shop-id', help='将旧素材和商品迁移到独立的店铺目录')
    legacy_products = commands.add_parser('migrate-v122-products')
    legacy_products.add_argument('--root', type=Path, required=True)
    legacy_products.add_argument('--source', type=Path, required=True)
    legacy_products.add_argument('--shop-id', help='将旧商品与话术迁移到独立的店铺目录')
    restore = commands.add_parser('restore-data')
    restore.add_argument('--root', type=Path, required=True)
    restore.add_argument('--backup', required=True, help='backups 目录中的备份编号')
    args = parser.parse_args()
    if args.command == 'restore-data':
        print(json.dumps(restore_data_backup(args.root, args.backup), ensure_ascii=False))
        return 0
    if args.command == 'migrate-v122-products':
        from scripts.console_data_migration import migrate_v122_products
        print(json.dumps(migrate_v122_products(args.root, args.source, args.shop_id), ensure_ascii=False))
        return 0
    if args.command == 'migrate-v122-assets':
        from scripts.console_data_migration import migrate_v122_assets
        result = migrate_v122_assets(args.root, args.runtime, args.voice, args.avatar, args.products, args.shop_id)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == 'migrate-data':
        from scripts.console_data_migration import migrate_data
        print(json.dumps(migrate_data(args.source, args.root, args.shop_id), ensure_ascii=False))
        return 0
    if args.command == 'run':
        return run_release(args.root, args.port, args.with_media, args.shop_id, args.access_role, args.account_id)
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
