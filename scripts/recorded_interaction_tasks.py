"""Owned background task lifecycle for the X11 recorded-interaction candidate."""

import hashlib
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

from scripts.recorded_interaction import render_replacements


class RecordedInteractionError(ValueError):
    pass


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class RecordedInteractionTasks:
    def __init__(self, data_directory, ffmpeg):
        self.root = (Path(data_directory) / "recorded-interactions").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = Path(ffmpeg).resolve()
        if not self.ffmpeg.is_file():
            raise RecordedInteractionError("缺少 FFmpeg")
        self.path = self.root / "task.json"
        self.lock = threading.RLock()
        self.thread = None
        self.cancel_event = None
        self.task = None
        if self.path.is_file():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise RecordedInteractionError("录播互动任务记录损坏") from error
            if not isinstance(value, dict) or value.get("status") not in {
                    "running", "succeeded", "failed", "cancelled", "interrupted"}:
                raise RecordedInteractionError("录播互动任务记录损坏")
            self.task = value
            if value["status"] == "running":
                self.task.update(status="interrupted", error="服务退出时任务中断")
                self._save()
                task_id = str(value.get("id") or "")
                stale_directory = (self.root / task_id).resolve()
                if task_id and stale_directory.parent == self.root:
                    shutil.rmtree(stale_directory, ignore_errors=True)

    def _save(self):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(self.task, ensure_ascii=False, separators=(",", ":")))
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    @staticmethod
    def _source(path, *, maximum, label):
        supplied = Path(str(path or ""))
        if supplied.is_symlink():
            raise RecordedInteractionError(f"{label}不是普通文件")
        source = supplied.expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0 or source.stat().st_size > maximum:
            raise RecordedInteractionError(f"{label}不存在、为空或过大")
        return source

    def state(self):
        with self.lock:
            return json.loads(json.dumps(self.task)) if self.task else None

    def start(self, source_video, replacements):
        if not isinstance(replacements, list) or not replacements or len(replacements) > 100:
            raise RecordedInteractionError("替换区间须为 1 至 100 项")
        with self.lock:
            if self.task and self.task["status"] == "running":
                raise RecordedInteractionError("已有录播互动任务运行中")
            previous_task = self.task
            source = self._source(source_video, maximum=2 * 1024**3, label="源视频")
            task_id = uuid.uuid4().hex
            directory = self.root / task_id
            directory.mkdir()
            try:
                owned_source = directory / ("source" + (source.suffix.lower() or ".mp4"))
                shutil.copyfile(source, owned_source)
                owned_plan = []
                for index, item in enumerate(replacements):
                    if not isinstance(item, dict) or set(item) != {"start_ms", "end_ms", "reply_audio", "source_id"}:
                        raise RecordedInteractionError("替换区间字段无效")
                    reply = self._source(item["reply_audio"], maximum=100 * 1024**2, label="回复音频")
                    if reply.suffix.lower() != ".wav":
                        raise RecordedInteractionError("回复音频当前仅支持 WAV")
                    owned_reply = directory / f"reply-{index:03d}.wav"
                    shutil.copyfile(reply, owned_reply)
                    owned_plan.append({**item, "reply_audio": str(owned_reply)})
                output = directory / "result.mp4"
                self.task = {"id": task_id, "status": "running", "source_sha256": _sha256(owned_source),
                             "replacement_count": len(owned_plan), "output": None, "output_sha256": None,
                             "error": None}
                self._save()
                self.cancel_event = threading.Event()
                self.thread = threading.Thread(target=self._run,
                    args=(task_id, owned_source, owned_plan, output, self.cancel_event), daemon=True)
                try:
                    self.thread.start()
                except BaseException:
                    self.task = previous_task
                    if self.task is None:
                        self.path.unlink(missing_ok=True)
                    else:
                        self._save()
                    self.thread = None
                    self.cancel_event = None
                    raise
                return self.state()
            except BaseException:
                shutil.rmtree(directory, ignore_errors=True)
                raise

    def _run(self, task_id, source, replacements, output, cancel_event):
        status, error, result = "succeeded", None, None
        try:
            result = render_replacements(source, replacements, output, ffmpeg=self.ffmpeg,
                                         cancel_check=cancel_event.is_set)
        except InterruptedError as exc:
            status, error = "cancelled", str(exc)
        except BaseException as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        with self.lock:
            if not self.task or self.task.get("id") != task_id:
                return
            self.task.update(status=status, error=error,
                             output=result["output"] if result else None,
                             output_sha256=result["sha256"] if result else None)
            self._save()
            if status != "succeeded":
                shutil.rmtree(output.parent, ignore_errors=True)
            else:
                for path in output.parent.iterdir():
                    if path != output and path.is_file():
                        path.unlink(missing_ok=True)

    def cancel(self, task_id):
        with self.lock:
            if not self.task or self.task.get("id") != task_id:
                raise RecordedInteractionError("录播互动任务不存在")
            if self.task["status"] != "running":
                return self.state()
            self.cancel_event.set()
            return self.state()

    def output(self, task_id):
        with self.lock:
            task = self.state()
            if not task or task.get("id") != task_id or task["status"] != "succeeded":
                raise RecordedInteractionError("录播互动成片不存在或尚未完成")
            path = Path(task["output"]).resolve()
            expected_parent = (self.root / task_id).resolve()
            if path.parent != expected_parent or path.name != "result.mp4" or _sha256(path) != task["output_sha256"]:
                raise RecordedInteractionError("录播互动成片已变化")
            return path

    def close(self):
        with self.lock:
            event, thread = self.cancel_event, self.thread
            if event is not None:
                event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
