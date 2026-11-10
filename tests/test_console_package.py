import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts.console_package import MANIFEST, REQUIRED, digest, install


class ConsolePackageTests(unittest.TestCase):
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
