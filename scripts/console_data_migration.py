"""Move persistent console data into a fresh managed installation."""
from contextlib import closing
import json
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid

from scripts.avatar_store import AvatarStore, digest
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore
from scripts.voice_store import VoiceStore


def checked_path(root, relative):
    path = root / relative
    if not path.is_relative_to(root) or '..' in path.relative_to(root).parts:
        raise ValueError('Data path escapes its directory')
    for component in (path, *path.parents):
        if component == root:
            break
        info = component.lstat()
        if component.is_symlink() or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Linked data files are unsupported')
    return path


def copy_file(source, target, relative):
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(checked_path(source, relative), destination)


def copy_database(source, target, relative):
    original = checked_path(source, relative)
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(original.as_uri() + '?mode=ro', uri=True)) as existing:
        with closing(sqlite3.connect(destination)) as copied:
            existing.backup(copied)
            if copied.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError(f'Corrupt database: {relative}')
            if copied.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError(f'Broken data reference: {relative}')


def copy_media(source, target, store, kind):
    for record in store.list():
        identifier = record['id']
        if str(uuid.UUID(identifier)) != identifier:
            raise ValueError('Invalid media identifier')
        directory = Path(kind) / identifier
        if kind == 'avatars':
            relative = directory / 'manifest.json'
            copy_file(source, target, relative)
            if digest(target / relative) != record['manifest_sha256']:
                raise ValueError('Avatar manifest hash mismatch')
            manifest = json.loads((target / relative).read_text(encoding='utf-8'))
            names = manifest['files']
            if not isinstance(names, dict) or 'sample.jpg' not in names or any(
                    name not in {'sample.jpg', 'normalized_video.mp4', 'model_info.yaml'}
                    and not re.fullmatch(r'frames/[0-9]{6}\.jpg|positions/[0-9]{6}\.txt', name)
                    for name in names):
                raise ValueError('Invalid avatar manifest paths')
        else:
            names = ['ref_audio.wav', 'ref_text.txt']
        for name in names:
            copy_file(source, target, directory / name)
        store.get(identifier)


def migrate_data(source, root):
    from scripts.local_console import InstanceLock

    source = source.resolve(strict=True)
    root = root.resolve()
    target = root / 'data'
    if not source.is_dir() or source.is_relative_to(root) or root.is_relative_to(source):
        raise ValueError('Source and managed installation must be separate directories')
    with InstanceLock(root / '.deployment'), InstanceLock(source):
        if target.exists() or target.is_symlink():
            raise FileExistsError('Managed data directory already exists')
        with tempfile.TemporaryDirectory(prefix='.migration-', dir=root) as temporary:
            snapshot = Path(temporary) / 'data'
            snapshot.mkdir()
            paths = ('console.json', 'products.sqlite3', 'voices/voices.sqlite3', 'avatars/avatars.sqlite3')
            present = [name for name in paths if (source / name).exists() or (source / name).is_symlink()]
            if not present:
                raise ValueError('No console data found in source directory')
            for name in present:
                if name == 'console.json':
                    copy_file(source, snapshot, name)
                    ConfigStore(snapshot).load()
                else:
                    copy_database(source, snapshot, name)
            if 'products.sqlite3' in present:
                ProductStore(snapshot)
            if 'voices/voices.sqlite3' in present:
                copy_media(source, snapshot, VoiceStore(snapshot), 'voices')
            if 'avatars/avatars.sqlite3' in present:
                copy_media(source, snapshot, AvatarStore(snapshot), 'avatars')
            snapshot.rename(target)
    return {'status': 'ok', 'data_directory': str(target), 'data_sets': present}
