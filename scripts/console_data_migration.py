"""Move persistent console data into a fresh managed installation."""
from contextlib import closing, contextmanager
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
from scripts.media_runtime import checked_path as runtime_file, inspect_runtime
from scripts.product_store import ProductStore, index_value
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


@contextmanager
def new_managed_data(root):
    from scripts.local_console import InstanceLock

    with InstanceLock(root / '.deployment'):
        target = root / 'data'
        if target.exists() or target.is_symlink():
            raise FileExistsError('Managed data directory already exists')
        with tempfile.TemporaryDirectory(prefix='.migration-', dir=root) as temporary:
            snapshot = Path(temporary) / 'data'
            snapshot.mkdir()
            yield snapshot
            snapshot.rename(target)


def migrate_data(source, root):
    from scripts.local_console import InstanceLock

    source = source.resolve(strict=True)
    root = root.resolve()
    target = root / 'data'
    if not source.is_dir() or source.is_relative_to(root) or root.is_relative_to(source):
        raise ValueError('Source and managed installation must be separate directories')
    with InstanceLock(source):
        with new_managed_data(root) as snapshot:
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
    return {'status': 'ok', 'data_directory': str(target), 'data_sets': present}


def migrate_v122_assets(root, runtime, voices, avatars, products=None):
    root = root.resolve()
    runtime = runtime.resolve(strict=True)
    if not voices and not avatars:
        raise ValueError('Select at least one legacy voice or avatar directory')
    if not inspect_runtime(runtime)['ready']:
        raise ValueError('Independent media runtime is incomplete')
    ffmpeg = runtime_file(runtime, '_internal/env/ffmpeg/bin/ffmpeg.exe')
    imported = {'voices': [], 'avatars': []}
    with new_managed_data(root) as snapshot:
        for kind, sources in (('voices', voices), ('avatars', avatars)):
            if not sources:
                continue
            store = VoiceStore(snapshot) if kind == 'voices' else AvatarStore(snapshot)
            for source in sources:
                source = source.resolve(strict=True)
                if not source.is_dir() or root.is_relative_to(source) or source.is_relative_to(root):
                    raise ValueError('Legacy assets and managed installation must be separate directories')
                if kind == 'voices':
                    audio = checked_path(source, 'ref_audio.wav')
                    text = checked_path(source, 'ref_text.txt').read_text(encoding='utf-8-sig')
                    record = store.import_audio(str(audio), text, source.name, ffmpeg)
                else:
                    record = store.import_prepared(source, source.name)
                imported[kind].append({'legacy_id': source.name, 'id': record['id']})
            if len(imported[kind]) == 1:
                store.select(imported[kind][0]['id'])
        if products is not None:
            imported['products'] = import_v122_products(snapshot, products)
        config = ConfigStore(snapshot)
        config.save({**config.load(), 'runtime_root': str(runtime)})
    return {'status': 'ok', 'data_directory': str(root / 'data'), **imported}


def import_v122_products(snapshot, source):
    source = source.resolve(strict=True)
    payload = json.loads(source.read_text(encoding='utf-8-sig'))
    products = payload.get('product_scripts') if isinstance(payload, dict) else None
    if not isinstance(products, list) or not products:
        raise ValueError('Legacy live configuration needs a nonempty product_scripts list')
    selected = index_value(payload.get('current_product_index', -1))
    imported = []
    store = ProductStore(snapshot)
    for position, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError('Invalid legacy product record')
        number = product.get('product_index', position)
        numeric = index_value(number)
        title = product.get('itemName') or product.get('item_name') or product.get('title') or f'商品 {number}'
        content = product.get('content') or title
        scripts = product.get('scripts') or product.get('script') or []
        if isinstance(scripts, str):
            scripts = [scripts]
        if not isinstance(scripts, list):
            raise ValueError('Invalid legacy script list')
        texts, roles = [], []
        for item in scripts:
            body = item.get('content', item.get('text')) if isinstance(item, dict) else item
            role = item.get('type', 'host') if isinstance(item, dict) else 'host'
            if not isinstance(body, str) or not isinstance(role, str):
                raise ValueError('Invalid legacy script record')
            if body.strip():
                texts.append(body)
                roles.append(role)
        legacy = {key: product[key] for key in ('itemName', 'item_name', 'item_id', 'itemId', 'keywords')
                  if key in product}
        legacy['script_roles'] = roles
        saved = store.save(title=title, content=content, product_index=number, extra={'v122': legacy})
        script_ids = [store.add_script(saved, body) for body in texts]
        if selected != -1 and numeric == selected:
            store.select(saved['id'])
        imported.append({'legacy_index': number, 'product_id': saved['id'], 'script_ids': script_ids})
    if selected != -1 and store.selected() is None:
        raise ValueError('Legacy current product does not exist in the supplied configuration')
    return imported


def migrate_v122_products(root, source):
    root = root.resolve()
    with new_managed_data(root) as snapshot:
        imported = import_v122_products(snapshot, source)
    return {'status': 'ok', 'data_directory': str(root / 'data'), 'products': imported}
