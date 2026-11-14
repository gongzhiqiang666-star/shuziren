"""Owned lifecycle for X11 held-product LTX motion videos."""

import hashlib
import json
import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from recovered.audio_duration import _find_ffprobe, get_audio_duration
from recovered.runninghub_ltx import (
    DEFAULT_FPS,
    DEFAULT_PROMPT,
    LTX_WEBAPP_ID,
    default_ltx_instance,
    generate_ltx_video,
    resolve_ltx_long_edge,
)


class HoldProductMotionError(ValueError):
    pass


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _regular_file(value, label, extensions, maximum):
    source = Path(value).expanduser()
    if source.is_symlink():
        raise HoldProductMotionError(f"{label}无效")
    path = source.resolve()
    if not path.is_file() or path.suffix.lower() not in extensions:
        raise HoldProductMotionError(f"{label}无效")
    size = path.stat().st_size
    if not 0 < size <= maximum:
        raise HoldProductMotionError(f"{label}大小无效")
    return path


def _probe_motion_video(path, ffprobe=None):
    probe = str(ffprobe) if ffprobe else _find_ffprobe()
    if not probe:
        raise HoldProductMotionError("未找到 FFprobe，无法验证动作视频")
    try:
        result = subprocess.run([
            probe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=True)
        value = json.loads(result.stdout)
        video = next(item for item in value.get("streams", []) if item.get("codec_type") == "video")
        duration = float(value.get("format", {}).get("duration") or video.get("duration") or 0)
        width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    except (subprocess.SubprocessError, json.JSONDecodeError, StopIteration, TypeError, ValueError) as error:
        raise HoldProductMotionError("手持商品动作视频无法完整解析") from error
    if duration <= 0 or width <= 0 or height <= 0:
        raise HoldProductMotionError("手持商品动作视频缺少有效画面或时长")
    return {"duration_s": duration, "width": width, "height": height,
            "codec": str(video.get("codec_name") or "")}


class HoldProductMotionTasks:
    def __init__(self, data_directory, ffprobe=None):
        self.root = (Path(data_directory) / "hold-product-motion-tasks").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "task.json"
        self.lock = threading.RLock()
        self.thread = None
        self.cancel_event = None
        self.task = None
        candidate = Path(ffprobe).resolve() if ffprobe else None
        self.ffprobe = candidate if candidate and candidate.is_file() else None
        if self.path.is_file():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise HoldProductMotionError("手持商品动作任务记录损坏") from error
            if not isinstance(value, dict) or value.get("status") not in {
                    "running", "succeeded", "failed", "cancelled", "interrupted"}:
                raise HoldProductMotionError("手持商品动作任务记录损坏")
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

    def plan(self, *, image, audio, action_prompt=DEFAULT_PROMPT, resolution="480p",
             fps=DEFAULT_FPS, low_cost=False):
        image_path = _regular_file(image, "手持商品图", {".png", ".jpg", ".jpeg", ".webp"}, 100 << 20)
        audio_path = _regular_file(audio, "动作音频", {".wav", ".mp3", ".m4a", ".aac", ".flac"}, 500 << 20)
        duration = float(get_audio_duration(str(audio_path)))
        if not 0 < duration <= 3600:
            raise HoldProductMotionError("动作音频时长无效")
        edge = resolve_ltx_long_edge(resolution)
        rate = float(fps)
        if not 1 <= rate <= 60:
            raise HoldProductMotionError("LTX 帧率无效")
        prompt = str(action_prompt or DEFAULT_PROMPT).strip()
        if not prompt or len(prompt) > 4000:
            raise HoldProductMotionError("动作提示词无效")
        return {
            "provider": "runninghub", "engine": "ltx", "webapp_id": LTX_WEBAPP_ID,
            "image": {"path": str(image_path), "sha256": _sha256(image_path)},
            "audio": {"path": str(audio_path), "sha256": _sha256(audio_path), "duration_s": duration},
            "action_prompt": prompt, "max_res": edge, "fps": rate,
            "instance_type": default_ltx_instance(edge, bool(low_cost)), "low_cost": bool(low_cost),
        }

    def start(self, *, api_key, image, audio, action_prompt=DEFAULT_PROMPT,
              resolution="480p", fps=DEFAULT_FPS, low_cost=False):
        if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096:
            raise HoldProductMotionError("RunningHub API Key 无效")
        if self.ffprobe is None and not _find_ffprobe():
            raise HoldProductMotionError("未找到 FFprobe，不能启动动作视频任务")
        with self.lock:
            if self.task and self.task["status"] == "running":
                raise HoldProductMotionError("已有手持商品动作任务运行中")
            plan = self.plan(image=image, audio=audio, action_prompt=action_prompt,
                             resolution=resolution, fps=fps, low_cost=low_cost)
            previous = self.task
            task_id = uuid.uuid4().hex
            directory = self.root / task_id
            directory.mkdir()
            try:
                owned_image = directory / ("held-product" + Path(plan["image"]["path"]).suffix.lower())
                owned_audio = directory / ("speech" + Path(plan["audio"]["path"]).suffix.lower())
                shutil.copyfile(plan["image"]["path"], owned_image)
                shutil.copyfile(plan["audio"]["path"], owned_audio)
                if (_sha256(owned_image) != plan["image"]["sha256"]
                        or _sha256(owned_audio) != plan["audio"]["sha256"]):
                    raise HoldProductMotionError("手持商品动作输入在任务启动前发生变化")
                output = directory / "held-product-motion.mp4"
                self.task = {
                    "id": task_id, "status": "running", "provider": plan["provider"],
                    "engine": plan["engine"], "webapp_id": plan["webapp_id"],
                    "action_prompt": plan["action_prompt"], "max_res": plan["max_res"],
                    "fps": plan["fps"], "instance_type": plan["instance_type"],
                    "input_sha256": [plan["image"]["sha256"], plan["audio"]["sha256"]],
                    "audio_duration_s": plan["audio"]["duration_s"], "output": None,
                    "output_sha256": None, "provider_task_id": None, "error": None,
                }
                self._save()
                self.cancel_event = threading.Event()
                self.thread = threading.Thread(
                    target=self._run,
                    args=(task_id, api_key, owned_image, owned_audio, output, self.cancel_event,
                          bool(low_cost)), daemon=True)
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

    def _run(self, task_id, api_key, image, audio, output, cancel_event, low_cost):
        status, error, result = "succeeded", None, None
        try:
            result = generate_ltx_video(
                api_key=api_key, image_path=image, audio_path=audio, dest=output,
                action_prompt=self.task["action_prompt"], audio_duration=self.task["audio_duration_s"],
                max_res=self.task["max_res"], fps=self.task["fps"],
                instance_type=self.task["instance_type"], low_cost=low_cost,
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
            path = Path(result["video_path"]).resolve() if result else None
            valid = path is not None and path == output.resolve() and path.is_file() and path.stat().st_size > 0
            if status == "succeeded" and not valid:
                status, error, result = "failed", "提供者未返回受管手持商品动作视频", None
            media = None
            if status == "succeeded":
                try:
                    media = _probe_motion_video(path, self.ffprobe)
                except HoldProductMotionError as exc:
                    status, error, result = "failed", str(exc), None
            self.task.update(
                status=status, error=error, output=str(path) if result else None,
                output_sha256=_sha256(path) if result else None,
                provider_task_id=result.get("task_id") if result else None,
                media=media if result else None)
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
                raise HoldProductMotionError("手持商品动作任务不存在")
            if self.task["status"] == "running":
                self.cancel_event.set()
            return self.state()

    def output(self, task_id):
        with self.lock:
            state = self.state()
            if not state or state.get("id") != task_id or state["status"] != "succeeded":
                raise HoldProductMotionError("手持商品动作视频不存在或尚未完成")
            path = Path(state["output"]).resolve()
            if (path.parent != (self.root / task_id).resolve() or path.name != "held-product-motion.mp4"
                    or not path.is_file() or _sha256(path) != state["output_sha256"]):
                raise HoldProductMotionError("手持商品动作视频已变化")
            return path

    def close(self):
        with self.lock:
            event, thread = self.cancel_event, self.thread
            if event is not None:
                event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
