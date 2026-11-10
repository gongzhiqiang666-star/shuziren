#!/usr/bin/env python3
"""Verify an archive exactly, or explicitly verify immutable v122 runtime inputs."""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path, PurePosixPath

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from v122_package_policy import POLICY, REQUIRED_RUNTIME_FILES, RUNTIME_PREFIX, derived_reason
else:
    from .v122_package_policy import POLICY, REQUIRED_RUNTIME_FILES, RUNTIME_PREFIX, derived_reason


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _records(manifest):
    if not isinstance(manifest, dict) or type(manifest.get("format")) is not int or manifest["format"] not in (1, 2):
        raise ValueError("unsupported manifest format")
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("manifest must contain a nonempty file list")
    if manifest["format"] == 2 and manifest.get("runtime_policy") != POLICY:
        raise ValueError("unknown runtime policy")
    seen = set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("invalid file record")
        relative = item.get("path")
        if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
            raise ValueError("invalid manifest path")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative or relative == ".":
            raise ValueError("noncanonical manifest path: " + relative)
        if relative.casefold() in seen:
            raise ValueError("duplicate manifest path: " + relative)
        seen.add(relative.casefold())
        if type(item.get("bytes")) is not int or item["bytes"] < 0:
            raise ValueError("invalid file size: " + relative)
        if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("invalid SHA256: " + relative)
        if manifest["format"] == 2 and derived_reason(relative):
            raise ValueError("format 2 lists derived data as immutable: " + relative)
    return records


def verify(root, profile="archive", progress=None):
    if profile not in {"archive", "runtime"}:
        raise ValueError("profile must be archive or runtime")
    root = Path(root).resolve()
    manifest_path = root / "proof/manifests/package.json"
    result = {"status": "failed", "profile": profile, "checked": 0, "missing": [], "changed": [],
              "errors": [], "derived_data": [], "policy": POLICY if profile == "runtime" else None,
              "root": str(root), "started_at_unix": time.time()}
    try:
        encoded = manifest_path.read_bytes()
        result["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
        manifest = json.loads(encoded)
        records = _records(manifest)
    except (OSError, ValueError) as error:
        result["errors"].append(str(error))
        if not manifest_path.is_file():
            result["missing"].append("proof/manifests/package.json")
        return result
    result["manifest_format"] = manifest["format"]
    if profile == "runtime":
        listed = {item["path"] for item in records}
        for required in REQUIRED_RUNTIME_FILES:
            if RUNTIME_PREFIX + required not in listed:
                result["errors"].append("required runtime record absent: " + required)
    result["total_records"] = len(records)
    for index, item in enumerate(records, 1):
        relative = item["path"]
        candidate = root.joinpath(*PurePosixPath(relative).parts)
        try:
            resolved = candidate.resolve()
            resolved.relative_to(root)
            # Validate paths before classifying derived data.
            if candidate.is_symlink():
                raise ValueError("symbolic file is not allowed")
            reason = derived_reason(relative) if profile == "runtime" else None
            if reason:
                result["derived_data"].append({"path": relative, "reason": reason,
                                               "present": candidate.is_file(), "hash_verified": False})
                continue
            if not candidate.is_file():
                result["missing"].append(relative)
                continue
            result["checked"] += 1
            if candidate.stat().st_size != item["bytes"] or _sha256(candidate) != item["sha256"]:
                result["changed"].append(relative)
        except (OSError, ValueError) as error:
            result["errors"].append(relative + ": " + str(error))
        finally:
            if progress and (index % 1000 == 0 or index == len(records)):
                progress(index, len(records), result["checked"])
    result["missing"].sort()
    result["changed"].sort()
    result["status"] = "failed" if any(result[k] for k in ("missing", "changed", "errors")) else "passed"
    result["finished_at_unix"] = time.time()
    result["scope"] = ("exact manifest archive" if profile == "archive" else
                       "immutable runtime inputs only; generated data unverified; inference/prewarm required separately")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile", choices=("archive", "runtime"), default="archive")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args(argv)
    def progress(index, total, checked):
        print(f"CHECKED_RECORDS {index}/{total}; immutable_files_checked={checked}", flush=True)
    result = verify(args.root, args.profile, progress if args.progress else None)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "derived_data"}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
