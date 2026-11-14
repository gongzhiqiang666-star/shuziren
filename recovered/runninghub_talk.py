"""Recovered RunningHub AI-App client for InfiniteTalk talking videos."""

from __future__ import annotations

import time
import os
from pathlib import Path
from urllib.parse import urlparse
import uuid

import requests

try:
    from .audio_duration import get_audio_duration
except ImportError:  # also supports loading the recovered module directly
    from audio_duration import get_audio_duration


RH_BASE = "https://www.runninghub.cn"
# The packaged build supplies this as the default AI-App workflow.  It may be
# overridden because RunningHub workflow IDs can be copied/replaced by users.
DIGITAL_HUMAN_WEBAPP_ID = "1937084629518794754"
RETRY_DELAYS = (1, 2, 3)
MAX_DOWNLOAD_BYTES = 2 * 1024**3


def _as_path(path):
    return Path(path).expanduser().resolve()


def _body(response):
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("RunningHub 返回了无效 JSON")
    return value


def _data(body):
    value = body.get("data", body)
    return value if isinstance(value, dict) else {}


def _message(body):
    return str(body.get("msg") or body.get("message") or body.get("error") or "Unknown")


def _check(body):
    code = body.get("code")
    if code in (None, 0, 200, "0", "200", "SUCCESS") and body.get("success") is not False:
        return
    if code == "TASK_QUEUE_MAXED":
        raise RuntimeError("RunningHub 任务队列已满，请稍后重试")
    raise RuntimeError(f"RunningHub 请求失败: {code or 'UNKNOWN'} {_message(body)}")


def upload_file(*, api_key: str, file_path) -> str:
    path = _as_path(file_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if not str(api_key).strip():
        raise ValueError("RunningHub API Key 不能为空")
    with path.open("rb") as handle:
        body = _body(requests.post(
            RH_BASE + "/task/openapi/upload",
            data={"apiKey": api_key}, files={"file": (path.name, handle)}, timeout=300,
        ))
    _check(body)
    data = _data(body)
    remote = data.get("fileName") or body.get("fileName") or data.get("url")
    if not remote:
        raise RuntimeError("RunningHub 上传成功但未返回 fileName")
    return str(remote)


def create_talk_task(*, api_key: str, image_remote: str, audio_remote: str,
                     audio_duration: float, webapp_id: str = DIGITAL_HUMAN_WEBAPP_ID) -> str:
    nodes = [
        {"nodeId": "1", "fieldName": "image", "fieldValue": image_remote},
        {"nodeId": "2", "fieldName": "audio", "fieldValue": audio_remote},
        {"nodeId": "3", "fieldName": "duration", "fieldValue": round(float(audio_duration), 3)},
    ]
    body = _body(requests.post(
        RH_BASE + "/task/openapi/ai-app/run",
        json={"webappId": webapp_id, "apiKey": api_key, "nodeInfoList": nodes}, timeout=60,
    ))
    _check(body)
    data = _data(body)
    task_id = data.get("taskId") or body.get("taskId")
    if not task_id:
        raise RuntimeError("RunningHub 未返回 taskId")
    return str(task_id)


def query_talk_task(*, api_key: str, task_id: str):
    body = _body(requests.post(
        RH_BASE + "/task/openapi/outputs",
        json={"apiKey": api_key, "taskId": task_id}, timeout=60,
    ))
    _check(body)
    data = _data(body)
    raw = str(data.get("status") or body.get("status") or "").upper()
    outputs = data.get("outputs") or data.get("results") or data.get("output") or []
    if isinstance(outputs, dict):
        outputs = [outputs]
    urls = []
    for item in outputs:
        url = item if isinstance(item, str) else item.get("fileUrl") or item.get("url")
        if url:
            urls.append(url)
    direct = data.get("fileUrl") or body.get("fileUrl")
    if direct:
        urls.insert(0, direct)
    failed = raw in {"FAILED", "FAIL", "ERROR", "CANCELLED"}
    # A completed status without an output URL is not downloadable success yet.
    success = bool(urls)
    status = "failed" if failed else "success" if success else "running" if raw in {"RUNNING", "PROCESSING"} else "queued"
    return {
        "task_id": str(task_id), "status": status,
        "video_url": urls[0] if urls else "",
        "task_cost_time": data.get("taskCostTime") or body.get("taskCostTime"),
        "fail_reason": data.get("failedReason") or data.get("failReason") or _message(body) if failed else "",
        "raw": body,
    }


def download_file(url: str, dest, timeout: int = 300) -> Path:
    parsed = urlparse(str(url))
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("RunningHub 输出必须使用 HTTPS 下载地址")
    target = _as_path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.partial")
    total = 0
    try:
        with requests.get(url, timeout=timeout, stream=True) as response:
            response.raise_for_status()
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("RunningHub 输出超过允许大小")
            with temporary.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError("RunningHub 输出超过允许大小")
                    output.write(chunk)
                output.flush(); os.fsync(output.fileno())
        if total < 12:
            raise RuntimeError("RunningHub 输出为空或过短")
        if b"ftyp" not in temporary.read_bytes()[:32]:
            raise RuntimeError("RunningHub 输出不是有效 MP4 容器")
        os.replace(temporary, target)
        return target
    finally:
        temporary.unlink(missing_ok=True)


def generate_talk_video(*, api_key: str, image_path, audio_path, dest,
                        audio_duration: float | None = None, poll_interval: int = 10,
                        poll_timeout: int = 2400):
    if not 0 <= poll_interval <= 300 or not 1 <= poll_timeout <= 86400:
        raise ValueError("轮询间隔或超时无效")
    image_remote = upload_file(api_key=api_key, file_path=image_path)
    audio_remote = upload_file(api_key=api_key, file_path=audio_path)
    duration = float(audio_duration) if audio_duration is not None else get_audio_duration(str(audio_path))
    task_id = create_talk_task(api_key=api_key, image_remote=image_remote,
                               audio_remote=audio_remote, audio_duration=duration)
    deadline = time.monotonic() + poll_timeout
    last = None
    while time.monotonic() < deadline:
        last = query_talk_task(api_key=api_key, task_id=task_id)
        if last["status"] == "success":
            path = download_file(last["video_url"], dest)
            return {**last, "video_path": str(path)}
        if last["status"] == "failed":
            raise RuntimeError(f"RunningHub InfiniteTalk 失败: {last['fail_reason']}")
        time.sleep(poll_interval)
    raise TimeoutError(f"RunningHub InfiniteTalk taskId={task_id} 超时，最后状态={last}")
