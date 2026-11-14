"""Build and verify the integrity manifest for approved bundled installers."""
import argparse
import hashlib
import json
from pathlib import Path
import stat


MANIFEST_NAME = "installer-manifest.json"
APPROVED_INSTALLERS = (
    "MicrosoftEdgeWebview2Setup.exe",
    "VBCABLE_Driver_Pack45/VBCABLE_Setup_x64.exe",
    "windowsdesktop-runtime-8.0.17-win-x64.exe",
    "windowsdesktop-runtime-9.0.6-win-x64.exe",
)
MAX_INSTALLER_SIZE = 1024 * 1024 * 1024


def _reparse(path):
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _approved_files(plugin_root):
    supplied_root = Path(plugin_root)
    if not supplied_root.is_dir() or _reparse(supplied_root):
        raise ValueError("plugin root must be a regular directory")
    root = supplied_root.resolve(strict=True)
    unexpected = []
    for candidate in root.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() == ".exe":
            relative = candidate.relative_to(root).as_posix()
            if relative not in APPROVED_INSTALLERS:
                unexpected.append(relative)
    if unexpected:
        raise ValueError("unexpected executable in plugin root: " + ", ".join(sorted(unexpected)))
    files = {}
    for relative in APPROVED_INSTALLERS:
        candidate = root / Path(relative)
        if not candidate.is_file():
            continue
        expected_parent = root / Path(relative).parent
        parents = [expected_parent]
        while parents[-1] != root:
            parents.append(parents[-1].parent)
        if (_reparse(candidate) or any(_reparse(parent) for parent in parents[:-1])
                or not candidate.resolve(strict=True).is_relative_to(root)):
            raise ValueError(f"installer escapes plugin root: {relative}")
        size = candidate.stat().st_size
        if size < 1 or size > MAX_INSTALLER_SIZE:
            raise ValueError(f"installer size is outside policy: {relative}")
        files[relative] = {"size": size, "sha256": _digest(candidate)}
    if not files:
        raise ValueError("no approved installers found")
    return root, files


def build(plugin_root):
    root, files = _approved_files(plugin_root)
    manifest = {"version": 1, "algorithm": "sha256", "files": files}
    destination = root / MANIFEST_NAME
    temporary = root / (MANIFEST_NAME + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            import os
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def verify(plugin_root):
    root, actual = _approved_files(plugin_root)
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file() or _reparse(manifest_path):
        raise ValueError("installer manifest is missing or unsafe")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("installer manifest is unreadable") from error
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("algorithm") != "sha256":
        raise ValueError("unsupported installer manifest")
    if manifest.get("files") != actual:
        raise ValueError("installer manifest does not match bundled files")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--plugin-root", required=True, type=Path)
    args = parser.parse_args()
    manifest = build(args.plugin_root) if args.command == "build" else verify(args.plugin_root)
    print(json.dumps({"verified": True, "files": len(manifest["files"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
