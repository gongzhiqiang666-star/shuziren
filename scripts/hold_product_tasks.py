"""Owned task lifecycle for the X11 held-product cloud candidate."""

import hashlib
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

from recovered.runninghub_hold import generate_hold_image, request_plan


class HoldProductError(ValueError):
    pass


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class HoldProductTasks:
    def __init__(self, data_directory):
        self.root = (Path(data_directory) / "hold-product-tasks").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "task.json"
        self.lock = threading.RLock()
        self.thread = None
        self.cancel_event = None
        self.task = None
        if self.path.is_file():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise HoldProductError("手持商品任务记录损坏") from error
            if not isinstance(value, dict) or value.get("status") not in {
                    "running", "succeeded", "failed", "cancelled", "interrupted"}:
                raise HoldProductError("手持商品任务记录损坏")
            self.task = value
            if value["status"] == "running":
                self.task.update(status="interrupted", error="服务退出时任务中断")
                self._save()
                self._remove_directory(str(value.get("id") or ""))

    def _remove_directory(self, task_id):
        directory = (self.root / task_id).resolve()
        if task_id and directory.parent == self.root:
            shutil.rmtree(directory, ignore_errors=True)

    def _save(self):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(self.task, ensure_ascii=False, separators=(",", ":")))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def state(self):
        with self.lock:
            return json.loads(json.dumps(self.task)) if self.task else None

    def plan(self, *, avatar, product, product_name="", prompt=""):
        return request_plan(avatar=avatar, product=product, product_name=product_name, prompt=prompt)

    def start(self, *, api_key, avatar, product, product_name="", prompt=""):
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096:
            raise HoldProductError("RunningHub API Key 无效")
        with self.lock:
            if self.task and self.task["status"] == "running":
                raise HoldProductError("已有手持商品任务运行中")
            plan = self.plan(avatar=avatar, product=product, product_name=product_name, prompt=prompt)
            previous = self.task
            task_id = uuid.uuid4().hex
            directory = self.root / task_id
            directory.mkdir()
            try:
                owned = []
                for item in plan["uploads"]:
                    source = Path(item["path"])
                    target = directory / (item["role"] + source.suffix.lower())
                    shutil.copyfile(source, target)
                    owned.append(str(target))
                output = directory / "held-product.png"
                self.task = {
                    "id": task_id, "status": "running", "provider": plan["provider"],
                    "engine": plan["engine"], "webapp_id": plan["webapp_id"],
                    "product_name": str(product_name).strip(), "prompt": plan["prompt"],
                    "input_sha256": [item["sha256"] for item in plan["uploads"]],
                    "output": None, "output_sha256": None, "provider_task_id": None, "error": None,
                }
                self._save()
                self.cancel_event = threading.Event()
                self.thread = threading.Thread(
                    target=self._run,
                    args=(task_id, api_key, owned[0], owned[1], output, self.cancel_event), daemon=True)
                try:
                    self.thread.start()
                except BaseException:
                    self.task = previous
                    if previous is None:
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

    def _run(self, task_id, api_key, avatar, product, output, cancel_event):
        status, error, result = "succeeded", None, None
        try:
            result = generate_hold_image(
                api_key=api_key, avatar=avatar, product=product, dest=output,
                product_name=self.task["product_name"], prompt=self.task["prompt"],
                cancel_check=cancel_event.is_set)
        except InterruptedError as exc:
            status, error = "cancelled", str(exc)
        except BaseException as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            api_key = None
        with self.lock:
            if not self.task or self.task.get("id") != task_id:
                return
            path = Path(result["image_path"]).resolve() if result else None
            valid = path is not None and path == output.resolve() and path.is_file()
            if status == "succeeded" and not valid:
                status, error, result = "failed", "提供者未返回受管手持商品图", None
            self.task.update(
                status=status, error=error, output=str(path) if result else None,
                output_sha256=_sha256(path) if result else None,
                provider_task_id=result.get("task_id") if result else None)
            self._save()
            if status != "succeeded":
                self._remove_directory(task_id)
            else:
                for item in output.parent.iterdir():
                    if item != output and item.is_file():
                        item.unlink(missing_ok=True)

    def cancel(self, task_id):
        with self.lock:
            if not self.task or self.task.get("id") != task_id:
                raise HoldProductError("手持商品任务不存在")
            if self.task["status"] == "running":
                self.cancel_event.set()
            return self.state()

    def output(self, task_id):
        with self.lock:
            state = self.state()
            if not state or state.get("id") != task_id or state["status"] != "succeeded":
                raise HoldProductError("手持商品图不存在或尚未完成")
            path = Path(state["output"]).resolve()
            if (path.parent != (self.root / task_id).resolve() or path.name != "held-product.png"
                    or not path.is_file() or _sha256(path) != state["output_sha256"]):
                raise HoldProductError("手持商品图已变化")
            return path

    def close(self):
        with self.lock:
            event, thread = self.cancel_event, self.thread
            if event is not None:
                event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
