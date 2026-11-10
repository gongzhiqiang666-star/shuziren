"""Filesystem-only tests of original-runtime discovery and native inventory filtering."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recovered.verify_recovery import binary_strings, first_party_extensions, resolve_runtime_internal


class RuntimePathsTests(unittest.TestCase):
    def test_binary_strings_keep_signatures_and_split_binary_noise(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "symbols.pyd"
            path.write_bytes(b"\x00abc\x00Class.method\x00call(x, y=1)\xffmore\nlast\tvalue")
            self.assertEqual(binary_strings(path).splitlines(),
                             ["Class.method", "call(x, y=1)", "more", "last\tvalue"])

    def test_distribution_and_internal_resolve_to_same_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            internal = root / "_internal"
            internal.mkdir()
            (internal / "main.cp310-win_amd64.pyd").touch()
            self.assertEqual(resolve_runtime_internal(root), internal.resolve())
            self.assertEqual(resolve_runtime_internal(internal), internal.resolve())

    def test_missing_runtime_fails_instead_of_falling_back(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Original v122 runtime is missing"):
                resolve_runtime_internal(directory)

    def test_inventory_excludes_environments_and_resource_forks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = ["main.cp310-win_amd64.pyd", "bin/core/infer_api.pyd",
                     "._main.cp310-win_amd64.pyd", "bin/._fork/nested.pyd",
                     "env/third_party.pyd", "env_50/third_party.pyd",
                     "tools/downloader/env/third_party.pyd",
                     "tools/DLLs/library.pyd", "tools/site-packages/package.pyd",
                     "ENV/upper.pyd", "tools/plain.py"]
            for name in files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            actual = {p.relative_to(root).as_posix() for p in first_party_extensions(root)}
            self.assertEqual(actual, {"main.cp310-win_amd64.pyd", "bin/core/infer_api.pyd"})


if __name__ == "__main__":
    unittest.main()
