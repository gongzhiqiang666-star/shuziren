"""Recovered RunningHub Seedream v5-pro text-to-image client."""

from __future__ import annotations

import time
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import requests


RH_BASE = "https://www.runninghub.cn/openapi/v2"
RH_TEXT2IMG = RH_BASE + "/seedream-v5-pro/text-to-image"
DEFAULT_MODEL = "seedream-v5-pro"
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def _as_path(path): return Path(path).expanduser().resolve()
def _headers(api_key): return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _explain_rh_error(body):
    code = body.get("code") or body.get("errorCode") or "UNKNOWN"
    message = body.get("message") or body.get("msg") or body.get("error") or "RunningHub request failed"
    if code == "APIKEY_USER_NOT_FOUND": message = "RunningHub API Key 无效或用户不存在"
    return f"{code}: {message}"


def _raise_if_rh_failed(body):
    code = body.get("code")
    if code not in (None, 0, 200, "0", "200", "SUCCESS") or body.get("success") is False:
        raise RuntimeError(_explain_rh_error(body))


def _size_for_aspect(aspect_ratio):
    return {"9:16": (1440, 2560), "16:9": (2560, 1440), "1:1": (2048, 2048),
            "3:4": (1536, 2048), "4:3": (2048, 1536)}.get(str(aspect_ratio), (1440, 2560))


def _request(method, url, **kwargs):
    try: response = requests.request(method, url, **kwargs); response.raise_for_status(); return response
    except requests.RequestException as error: raise RuntimeError(f"RunningHub 请求失败: {error}") from error


def _result_urls(body):
    data = body.get("data") or body.get("result") or body
    results = data.get("results") or data.get("outputs") or data.get("images") or [] if isinstance(data, dict) else []
    if isinstance(results, dict): results = [results]
    urls = []
    for item in results:
        url = item if isinstance(item, str) else item.get("fileUrl") or item.get("file_url") or item.get("url") or item.get("download_url")
        if url: urls.append(url)
    for key in ("fileUrl", "file_url", "download_url", "url"):
        if isinstance(data, dict) and data.get(key): urls.append(data[key])
    return list(dict.fromkeys(urls))


def submit_text_to_image(*, api_key, prompt, aspect_ratio="9:16", resolution="2k", quality="low"):
    if not str(api_key).strip(): raise ValueError("RunningHub API Key 不能为空")
    width, height = _size_for_aspect(aspect_ratio)
    response = _request("POST", RH_TEXT2IMG, headers=_headers(api_key),
                        json={"prompt": prompt, "width": width, "height": height,
                              "resolution": resolution, "quality": quality, "outputFormat": "png"}, timeout=60)
    body = response.json(); _raise_if_rh_failed(body)
    data = body.get("data") or body
    task_id = data.get("taskId") or data.get("task_id")
    if not task_id: raise RuntimeError("RunningHub 未返回 taskId")
    return str(task_id)


def _poll_task_url_cancellable(*, api_key, task_id, poll_interval=5, poll_timeout=900,
                               cancel_check=None):
    deadline = time.monotonic() + poll_timeout
    url = RH_BASE + f"/task/{task_id}"
    while time.monotonic() < deadline:
        if cancel_check and cancel_check(): raise InterruptedError("图片生成已取消")
        body = _request("GET", url, headers=_headers(api_key), timeout=60).json(); _raise_if_rh_failed(body)
        data = body.get("data") or body; status = str(data.get("status") or "").upper()
        urls = _result_urls(body)
        if urls: return urls[0]
        if status in {"FAILED", "ERROR", "CANCELLED"}: raise RuntimeError(_explain_rh_error(body))
        if cancel_check and cancel_check(): raise InterruptedError("图片生成已取消")
        time.sleep(poll_interval)
    raise TimeoutError(f"RunningHub taskId={task_id} 超时")


def poll_task_url(*, api_key, task_id, poll_interval=5, poll_timeout=900):
    return _poll_task_url_cancellable(api_key=api_key, task_id=task_id,
                                      poll_interval=poll_interval, poll_timeout=poll_timeout)


def download_image(url, dest, timeout=300):
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("RunningHub 图片下载地址必须是 HTTPS")
    target = Path(dest); target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_name(f".{target.name}.{uuid4().hex}.pending")
    response = None
    try:
        response = _request("GET", url, timeout=timeout, stream=True)
        declared = int(response.headers.get("Content-Length") or 0)
        if declared < 0 or declared > MAX_DOWNLOAD_BYTES:
            raise ValueError("RunningHub 图片超过 100 MiB 限制")
        total = 0
        with pending.open("xb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("RunningHub 图片超过 100 MiB 限制")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if total == 0:
            raise ValueError("RunningHub 返回了空图片")
        from PIL import Image
        with Image.open(pending) as image:
            image.verify()
        with Image.open(pending) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or image.width <= 0 or image.height <= 0:
                raise ValueError("RunningHub 返回的图片格式无效")
            image.load()
        pending.replace(target)
        return target
    finally:
        if response is not None:
            close = getattr(response, "close", None)
            if callable(close): close()
        pending.unlink(missing_ok=True)


def _generate_and_download_cancellable(*, api_key, prompt, dest, aspect_ratio="9:16", resolution="2k",
                                       quality="low", poll_interval=5, poll_timeout=900,
                                       cancel_check=None):
    if cancel_check and cancel_check(): raise InterruptedError("图片生成已取消")
    task_id = submit_text_to_image(api_key=api_key, prompt=prompt, aspect_ratio=aspect_ratio,
                                   resolution=resolution, quality=quality)
    url = _poll_task_url_cancellable(api_key=api_key, task_id=task_id, poll_interval=poll_interval,
                                     poll_timeout=poll_timeout, cancel_check=cancel_check)
    if cancel_check and cancel_check(): raise InterruptedError("图片生成已取消")
    return download_image(url, dest)


def generate_and_download(*, api_key, prompt, dest, aspect_ratio="9:16", resolution="2k",
                          quality="low", poll_interval=5, poll_timeout=900):
    return _generate_and_download_cancellable(
        api_key=api_key, prompt=prompt, dest=dest, aspect_ratio=aspect_ratio,
        resolution=resolution, quality=quality, poll_interval=poll_interval,
        poll_timeout=poll_timeout)
