from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid
import wave
from zipfile import ZipFile

from scripts.console_package import MANIFEST, REQUIRED, digest, install, run_release, switch_release
from scripts.console_data_migration import migrate_data, migrate_v122_products
from scripts.avatar_store import AvatarStore
from scripts.local_console import InstanceLock
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore, playback_segments
from scripts.voice_store import VoiceStore, fingerprint


class ConsolePackageTests(unittest.TestCase):
    def test_release_switch_respects_shop_process_lock_without_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            shop = root / 'data' / 'shops' / 'shop-pilot'
            active = {'current': 'release', 'previous': 'release'}
            with patch('scripts.console_package.read_active', return_value=active):
                with InstanceLock(shop), self.assertRaises(OSError):
                    switch_release(root)
                self.assertEqual(switch_release(root), active)

    def test_managed_shops_can_run_together_while_release_switch_is_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            active = {'current': 'release', 'previous': 'release'}

            def first_running(*args, **kwargs):
                with self.assertRaises(OSError):
                    switch_release(root)
                with self.assertRaises(OSError):
                    run_release(root, 0, shop_id='first')
                self.assertEqual(run_release(root, 0, shop_id='second'), 0)
                return 0

            with (patch('scripts.console_package.read_active', return_value=active),
                  patch('scripts.console_package.check_release', return_value=(root, {})),
                  patch('scripts.console_package.subprocess.call') as launch):
                launch.side_effect = lambda *args, **kwargs: first_running() if launch.call_count == 1 else 0
                self.assertEqual(run_release(root, 0, shop_id='first'), 0)
                self.assertEqual(launch.call_count, 2)
                self.assertEqual(switch_release(root), active)

    def test_managed_release_rejects_shop_directory_outside_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / 'install'
            outside = parent / 'outside' / 'shops' / 'shop-pilot'
            with (patch('scripts.console_package.read_active', return_value={'current': 'release'}),
                  patch('scripts.console_package.check_release', return_value=(root, {})),
                  patch('scripts.local_console_config.shop_data_directory', return_value=outside),
                  patch('scripts.console_package.subprocess.call') as launch):
                with self.assertRaisesRegex(ValueError, 'inside the managed installation'):
                    run_release(root, 0, shop_id='pilot')
                launch.assert_not_called()

    def test_shop_migration_preserves_prepared_avatar(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest('OpenCV is required for the prepared avatar fixture')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = root / 'prepared'
            (prepared / 'frames').mkdir(parents=True)
            (prepared / 'positions').mkdir()
            frame = prepared / 'frames/000000.jpg'
            self.assertTrue(cv2.imwrite(str(frame), np.zeros((32, 24, 3), np.uint8)))
            (prepared / 'positions/000000.txt').write_text(
                'fps: 25\nwidth: 24\nheight: 32\nis_no_face: False\nbounding_box: [2, 20, 3, 22]\n',
                encoding='utf-8')
            source = root / 'source'
            original = AvatarStore(source)
            avatar = original.import_prepared(prepared, '测试形象')
            original.select(avatar['id'])
            migrated = migrate_data(source, root / 'install', 'pilot')
            shop = AvatarStore(migrated['data_directory'])
            self.assertEqual(shop.selected_id(), avatar['id'])
            self.assertEqual(shop.get(avatar['id']), original.get(avatar['id']))
            target = shop.root / avatar['id']
            for relative in ('frames/000000.jpg', 'positions/000000.txt'):
                self.assertEqual((target / relative).read_bytes(),
                                 (original.root / avatar['id'] / relative).read_bytes())

    def test_legacy_product_payload_preserves_selection_and_scripts_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'v122.json'
            products = [
                {'product_index': '007', 'itemName': '测试杯', 'content': '示例资料',
                 'scripts': [{'text': '主讲', 'type': 'host'}, {'content': '助播', 'type': 'assistant'}]},
                {'item_name': '测试布', 'script': '单条话术'},
            ]
            payload = {'product_scripts': products, 'current_product_index': 7}
            source.write_text(json.dumps(payload), encoding='utf-8')
            imported = migrate_v122_products(root / 'install', source)['products']
            store = ProductStore(root / 'install/data')
            identifier = imported[0]['product_id']
            self.assertEqual(store.selected(), identifier)
            self.assertEqual(imported[0]['legacy_index'], '007')
            self.assertEqual([row['text'] for row in store.scripts(identifier)], ['主讲', '助播'])
            self.assertEqual(store.get(identifier)['extra']['v122']['script_roles'], ['host', 'assistant'])
            host, assistant = store.scripts(identifier)
            self.assertEqual(playback_segments(host)[0]['type'], 'host')
            self.assertEqual(playback_segments(assistant)[0]['type'], 'assistant')
            new_script = store.add_script(store.get(identifier), '独立新稿')
            scripts = {row['id']: row for row in store.scripts(identifier)}
            self.assertEqual(playback_segments(scripts[assistant['id']])[0]['type'], 'assistant')
            self.assertEqual(playback_segments(scripts[new_script])[0]['type'], 'host')
            products[1]['product_index'] = 3
            source.write_text(json.dumps({**payload, 'enable_multi_product': True, 'current_product_index': 1}),
                              encoding='utf-8')
            rotation = migrate_v122_products(root / 'rotation', source)['products']
            rotated = ProductStore(root / 'rotation/data')
            self.assertEqual([item['product_index'] for item in rotated.list()], ['007', 3])
            self.assertEqual(rotated.selected(), rotation[1]['product_id'])
            source.write_text(json.dumps({'products': [products[1]], 'current_product_index': 3}),
                              encoding='utf-8')
            alternate = migrate_v122_products(root / 'alternate', source)['products'][0]
            alternate_store = ProductStore(root / 'alternate/data')
            self.assertEqual(alternate_store.selected(), alternate['product_id'])
            self.assertEqual([row['text'] for row in alternate_store.scripts(alternate['product_id'])],
                             ['单条话术'])
            source.write_text(json.dumps({
                **payload, 'live_type': 'face_hand_live', 'products': [products[1]],
                'current_product_index': 3,
            }), encoding='utf-8')
            face_hand = migrate_v122_products(root / 'face-hand', source)['products']
            self.assertEqual([item['legacy_index'] for item in face_hand], [3])
            products[1]['product_index'] = 7
            source.write_text(json.dumps(payload), encoding='utf-8')
            with self.assertRaises(ValueError):
                migrate_v122_products(root / 'invalid', source)
            self.assertFalse((root / 'invalid/data').exists())

    def test_migration_snapshots_data_and_rejects_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, managed = root / 'source', root / 'managed'
            config = {'version': 1, 'port': 5218, 'runtime_root': ''}
            ConfigStore(source).save(config)
            products = ProductStore(source)
            product = products.save(title='测试商品', content='迁移验证', product_index=1)
            products.select(product['id'])
            script = products.add_script(product, '原有话术')
            products.select_script(product['id'], script)
            voices = VoiceStore(source)
            voice_id = str(uuid.uuid4())
            voice_directory = voices.root / voice_id
            voice_directory.mkdir()
            audio = voice_directory / 'ref_audio.wav'
            transcript = voice_directory / 'ref_text.txt'
            transcript.write_text('迁移测试音色', encoding='utf-8')
            with wave.open(str(audio), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(24000)
                stream.writeframes(bytes(48000))
            with closing(sqlite3.connect(voices.path)) as db, db:
                db.execute('INSERT INTO voices VALUES (?, ?, ?, ?, ?, ?)',
                           (voice_id, '测试音色', '迁移测试音色', fingerprint(audio), fingerprint(transcript), 1))
            voices.select(voice_id)
            (source / 'console.log').write_text('excluded', encoding='utf-8')

            with InstanceLock(source), self.assertRaises(OSError):
                migrate_data(source, managed)
            self.assertFalse((managed / 'data').exists())
            migrate_data(source, managed)
            target = managed / 'data'
            self.assertEqual(ConfigStore(target).load(), config)
            self.assertEqual(ProductStore(target).selected(), product['id'])
            self.assertEqual(ProductStore(target).selected_script(product['id']), products.selected_script(product['id']))
            self.assertFalse((target / 'console.log').exists())
            with self.assertRaises(FileExistsError):
                migrate_data(source, managed)
            shop_result = migrate_data(source, managed, 'pilot')
            shop = managed / 'data/shops/shop-pilot'
            self.assertEqual(Path(shop_result['data_directory']), shop)
            self.assertEqual(ProductStore(shop).selected_script(product['id']), script)
            self.assertEqual(ConfigStore(shop).load(), config)
            migrated_voices = VoiceStore(shop)
            self.assertEqual(migrated_voices.selected(), voice_id)
            self.assertEqual(migrated_voices.get(voice_id), voices.get(voice_id))
            self.assertEqual(migrated_voices.audio_path(voice_id).read_bytes(), audio.read_bytes())
            self.assertEqual(ProductStore(target).selected(), product['id'])
            with self.assertRaises(FileExistsError):
                migrate_data(source, managed, 'pilot')
            sibling = Path(migrate_data(source, managed, 'second')['data_directory'])
            pilot_products = ProductStore(shop)
            current = pilot_products.get(product['id'])
            pilot_products.save(title='Pilot edit', content=current['content'],
                                product_index=current['product_index'], product_id=current['id'],
                                version=current['version'])
            self.assertEqual(ProductStore(sibling).get(product['id']), current)
            self.assertEqual(ProductStore(target).get(product['id']), current)
            self.assertEqual(products.get(product['id']), current)

    def test_install_validates_hash_and_never_overwrites_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'source.zip'
            files = dict.fromkeys(REQUIRED, b'fixture')
            manifest = {'version': 1, 'commit': 'a' * 40, 'files': {name: digest(data) for name, data in files.items()}}
            with ZipFile(package, 'w') as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
                archive.writestr(MANIFEST, json.dumps(manifest))
            destination = root / 'new'
            install(package, destination)
            self.assertEqual((destination / 'packaging/start-console.cmd').read_bytes(), b'fixture')
            with self.assertRaises(FileExistsError):
                install(package, destination)
            bad = root / 'bad.zip'
            with ZipFile(bad, 'w') as archive:
                for name in files:
                    archive.writestr(name, b'tampered')
                archive.writestr(MANIFEST, json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                install(bad, root / 'bad-destination')
            self.assertFalse((root / 'bad-destination').exists())

    def test_rejects_unlisted_and_unsafe_windows_paths(self):
        from scripts.console_package import allowed
        for path in ('logs/result.json', 'scripts/../outside.py', 'scripts/aux.txt',
                     'scripts/file.py:stream', 'scripts/model.pyd', 'scripts/v122-proof/windows/run.cmd'):
            with self.subTest(path=path):
                self.assertFalse(allowed(path))
