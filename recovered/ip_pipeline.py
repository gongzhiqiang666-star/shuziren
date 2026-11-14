"""Checkpoint and rollback helpers for the IP-agent media pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock, RLock


PIPELINE_VERSION = 1
STEP_OUTPUT_FIELDS = {
    "audio": ("audio_path",),
    "video": ("video_path",),
    "subtitles": ("subtitle_path", "subtitle_video_path"),
    "finishing": ("final_video_path",),
    "publish_meta": (),
}
_locks_guard = Lock()
_project_locks = {}


class ProjectPipelineLock:
    """Serialize one project across threads and application processes."""

    def __init__(self, project_id, thread_lock):
        digest = hashlib.sha256(str(project_id).encode("utf-8")).hexdigest()
        root = Path(tempfile.gettempdir()) / "shuziren-ip-pipeline-locks"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{digest}.lock"
        self.thread_lock = thread_lock
        self.stream = None

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            self.stream = self.path.open("a+b")
            if self.stream.tell() == 0:
                self.stream.write(b"\0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX)
            return self
        except Exception:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            self.thread_lock.release()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.stream is not None:
                self.stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
                self.stream.close()
                self.stream = None
        finally:
            self.thread_lock.release()


def project_pipeline_lock(project_id):
    key = str(project_id)
    with _locks_guard:
        thread_lock = _project_locks.setdefault(key, RLock())
    return ProjectPipelineLock(key, thread_lock)


def pipeline_fingerprint(project_id, data, project):
    effective_script = (data.get("text") or data.get("script") or
                        project.get("rewritten_script") or project.get("original_script"))
    baseline = {
        "version": PIPELINE_VERSION,
        "project_id": str(project_id),
        "data": data,
        "source": {"name": project.get("name"), "script": effective_script,
                   "benchmark_url": project.get("benchmark_url")},
    }
    encoded = json.dumps(baseline, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def completed_step_ready(step, project):
    fields = STEP_OUTPUT_FIELDS[step]
    if not fields:
        return bool(project.get("publish_title"))
    return all(project.get(field) and Path(project[field]).is_file() and Path(project[field]).stat().st_size > 0
               for field in fields)


def result_summary(result):
    return {key: value for key, value in result.items() if key != "project"}


class StepFileCheckpoint:
    """Restore known project outputs when one pipeline step fails."""

    def __init__(self, project, step):
        self.paths = []
        targets = [(field, Path(project[field])) for field in STEP_OUTPUT_FIELDS[step] if project.get(field)]
        self.root = ((targets[0][1].parent / f".ip-{step}-rollback") if targets else
                     Path(tempfile.mkdtemp(prefix=f".ip-{step}-rollback-")))
        if targets and self.root.exists():
            errors = self._restore_manifest(self.root, {target.resolve() for _field, target in targets})
            if errors:
                raise OSError("上一次未完成步骤回滚失败: " + "; ".join(errors))
            shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)
        manifest = []
        for index, (field, target) in enumerate(targets):
            value = project.get(field)
            backup = self.root / str(index)
            existed = target.is_file()
            if existed:
                shutil.copy2(target, backup)
            self.paths.append((target, backup, existed))
            manifest.append({"field": field, "target": str(target.resolve()),
                             "backup": backup.name, "existed": existed})
        if targets:
            temporary = self.root / "manifest.json.tmp"
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.root / "manifest.json")

    @staticmethod
    def _restore_manifest(root, expected_targets):
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            return []
        errors = []
        try:
            entries = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return [f"事务清单无法读取: {error}"]
        for entry in reversed(entries):
            try:
                target = Path(entry["target"]).resolve()
                if target not in expected_targets:
                    raise ValueError(f"事务目标不属于当前项目: {target}")
                backup_name = str(entry["backup"])
                if Path(backup_name).name != backup_name:
                    raise ValueError("事务备份路径无效")
                backup = root / backup_name
                if entry["existed"]:
                    if not backup.is_file():
                        raise FileNotFoundError(f"缺少备份 {backup}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
                else:
                    target.unlink(missing_ok=True)
            except (KeyError, OSError, TypeError, ValueError) as error:
                errors.append(str(error))
        return errors

    def rollback(self):
        errors = []
        for target, backup, existed in reversed(self.paths):
            try:
                if existed:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
                else:
                    target.unlink(missing_ok=True)
            except OSError as error:
                errors.append(f"{target}: {error}")
        self.close()
        return errors

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)
