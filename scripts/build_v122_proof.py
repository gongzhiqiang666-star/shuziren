#!/usr/bin/env python3
"""Create a non-overwriting offline v122 first-proof directory."""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from v122_package_policy import POLICY, REQUIRED_RUNTIME_FILES, derived_reason, transport_metadata
else:
    from .v122_package_policy import POLICY, REQUIRED_RUNTIME_FILES, derived_reason, transport_metadata


class BuildError(RuntimeError):
    pass


def _files(root):
    root = Path(root).resolve()
    for directory, dirnames, filenames in os.walk(str(root), followlinks=False):
        current = Path(directory)
        for name in list(dirnames) + list(filenames):
            if (current / name).is_symlink():
                raise BuildError("symbolic links are not allowed")
        for name in filenames:
            path = current / name
            if path.is_file():
                yield path, path.relative_to(root).as_posix()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_package(runtime_source, proof_source, destination, required=()):
    runtime_source = Path(runtime_source).resolve(); proof_source = Path(proof_source).resolve()
    destination = Path(destination).resolve()
    if not runtime_source.is_dir() or not proof_source.is_dir():
        raise BuildError("source directory is missing")
    if destination.exists() and any(destination.iterdir()):
        raise BuildError("destination must be new or empty")
    for relative in required:
        candidate = runtime_source / relative
        if not candidate.is_file():
            raise BuildError("required runtime file is missing: " + relative)
    runtime_files = list(_files(runtime_source)); proof_files = list(_files(proof_source))
    if any(destination == source or source in destination.parents or destination in source.parents
           for source in (runtime_source, proof_source)):
        raise BuildError("destination cannot overlap a source")
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    omitted = {}
    for prefix, source_root, entries in (("runtime/yunchuang_v122", runtime_source, runtime_files),
                                         ("proof", proof_source, proof_files)):
        for source, relative in entries:
            packaged_relative = (Path(prefix) / relative).as_posix()
            reason = "macos-transport-metadata" if transport_metadata(packaged_relative) else derived_reason(packaged_relative)
            if reason:
                omitted[reason] = omitted.get(reason, 0) + 1
                continue
            target = destination / prefix / relative; target.parent.mkdir(parents=True, exist_ok=True)
            before = source.stat(); shutil.copy2(str(source), str(target)); after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise BuildError("source changed during copy")
            records.append({"path": (Path(prefix) / relative).as_posix(), "bytes": target.stat().st_size,
                            "sha256": _sha256(target)})
    records.sort(key=lambda item: item["path"])
    if not records:
        raise BuildError("package has no immutable files")
    manifest = {"format": 2, "runtime_policy": POLICY, "omitted_generated_files": omitted, "files": records}
    manifest_path = destination / "proof/manifests/package.json"; manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _stage_tools(repository, staging):
    repository = Path(repository).resolve(); staging = Path(staging)
    (staging / "scripts").mkdir(parents=True); (staging / "web").mkdir(); (staging / "windows").mkdir()
    for name in ("v122_proof.py", "v122_proof_server.py", "v122_adapter.py", "v122_orchestrator.py", "v122_runtime_bridge.py", "verify_v122_package.py", "v122_package_policy.py"):
        shutil.copy2(repository / "scripts" / name, staging / "scripts" / name)
    shutil.copytree(repository / "scripts/v122-proof/web", staging / "web", dirs_exist_ok=True)
    windows = repository / "scripts/v122-proof/windows"
    for name in ("start-server.ps1", "stop-owned.ps1", "preflight.ps1"):
        shutil.copy2(windows / name, staging / "windows" / name)
    shutil.copy2(repository / "config/v122-proof.example.json", staging / "config.json")
    return windows


def build_release(repository, runtime_source, destination):
    repository = Path(repository).resolve(); destination = Path(destination).resolve()
    with tempfile.TemporaryDirectory(prefix="v122-proof-") as raw:
        staging = Path(raw)
        windows = _stage_tools(repository, staging)
        required = REQUIRED_RUNTIME_FILES
        manifest = build_package(runtime_source, staging, destination, required)
        for name in ("00_开始验证.cmd", "01_环境检查.cmd", "99_停止验证.cmd"):
            target = destination / name; shutil.copy2(windows / name, target)
            manifest["files"].append({"path": name, "bytes": target.stat().st_size, "sha256": _sha256(target)})
        manifest["files"].sort(key=lambda item: item["path"])
        (destination / "proof/manifests/package.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest


def refresh_release_tools(repository, destination):
    repository = Path(repository).resolve(); destination = Path(destination).resolve()
    manifest_path = destination / "proof/manifests/package.json"
    if not manifest_path.is_file() or not (destination / "runtime/yunchuang_v122").is_dir():
        raise BuildError("destination is not a built v122 proof package")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime_records = [item for item in manifest.get("files", []) if str(item.get("path", "")).startswith("runtime/")]
    with tempfile.TemporaryDirectory(prefix="v122-proof-refresh-") as raw:
        staging = Path(raw); windows = _stage_tools(repository, staging); proof_records = []
        for source, relative in _files(staging):
            target = destination / "proof" / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
            proof_records.append({"path": (Path("proof") / relative).as_posix(), "bytes": target.stat().st_size, "sha256": _sha256(target)})
        for name in ("00_开始验证.cmd", "01_环境检查.cmd", "99_停止验证.cmd"):
            target = destination / name; shutil.copy2(windows / name, target)
            proof_records.append({"path": name, "bytes": target.stat().st_size, "sha256": _sha256(target)})
    # Preserve the archive's original scope. Tool refresh is not runtime rebaselining.
    result = {**manifest, "files": sorted(runtime_records + proof_records, key=lambda item: item["path"])}
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--runtime-source", type=Path)
    parser.add_argument("--repository", default=Path(__file__).resolve().parents[1], type=Path); parser.add_argument("--destination", type=Path)
    parser.add_argument("--refresh-existing", type=Path)
    args = parser.parse_args(argv)
    if args.refresh_existing:
        manifest = refresh_release_tools(args.repository, args.refresh_existing)
    else:
        if not args.runtime_source or not args.destination: parser.error("--runtime-source and --destination are required for a full build")
        manifest = build_release(args.repository, args.runtime_source, args.destination)
    print("verified files: %d" % len(manifest["files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
