import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.console_package import MANIFEST, REQUIRED, digest, install
from scripts.console_data_migration import migrate_data, migrate_v122_products
from scripts.local_console import InstanceLock
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore


class ConsolePackageTests(unittest.TestCase):
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
