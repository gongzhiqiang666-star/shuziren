#!/usr/bin/env python3
"""Verify the offline package against its generated manifest."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def verify(root):
    root = Path(root).resolve(); manifest_path = root / "proof/manifests/package.json"
    try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "failed", "checked": 0, "missing": ["proof/manifests/package.json"], "changed": []}
    missing, changed, checked = [], [], 0
    for item in manifest.get("files", []):
        relative = str(item.get("path", "")); pure = PurePosixPath(relative)
        if not relative or pure.is_absolute() or ".." in pure.parts:
            changed.append(relative or "<empty>"); continue
        candidate = (root / Path(*pure.parts)).resolve()
        try: candidate.relative_to(root)
        except ValueError: changed.append(relative); continue
        if not candidate.is_file(): missing.append(relative); continue
        checked += 1
        if candidate.stat().st_size != item.get("bytes") or _sha256(candidate) != item.get("sha256"):
            changed.append(relative)
    return {"status": "passed" if not missing and not changed else "failed", "checked": checked,
            "missing": sorted(missing), "changed": sorted(changed)}


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path); args = parser.parse_args(argv); result = verify(args.root)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(encoded, encoding="utf-8")
    print(encoded); return 0 if result["status"] == "passed" else 1


if __name__ == "__main__": raise SystemExit(main())
