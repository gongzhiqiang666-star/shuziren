"""Checkpoint and rollback helpers for the IP-agent media pipeline."""

from __future__ import annotations

import hashlib
import json
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


def project_pipeline_lock(project_id):
    key = str(project_id)
    with _locks_guard:
        return _project_locks.setdefault(key, RLock())


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
        self.root = Path(tempfile.mkdtemp(prefix=f".ip-{step}-rollback-"))
        for index, field in enumerate(STEP_OUTPUT_FIELDS[step]):
            value = project.get(field)
            if not value:
                continue
            target = Path(value)
            backup = self.root / str(index)
            existed = target.is_file()
            if existed:
                shutil.copy2(target, backup)
            self.paths.append((target, backup, existed))

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
