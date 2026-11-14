"""Source-controlled RunningHub Qwen 2.1 held-product image adapter."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

from .runninghub_image import download_image
from .runninghub_talk import upload_file


RH_BASE = "https://www.runninghub.cn"
HOLD_PRODUCT_WEBAPP_ID = "2113900488247824386"
HOLD_PRODUCT_ASPECT = "9:16 (Portrait Widescreen)"
MAX_INPUT_BYTES = 100 * 1024 * 1024


def build_hold_prompt(product_name=""):
    name = "指定商品" if not str(product_name).strip() else f"商品“{str(product_name).strip()}”"
    return (f"图1为主播，图2为{name}的商品主图。仅提取图2的商品本体，忽略模特、背景、价格和促销文字。"
            "移除主播手中原有物品，让主播双手在胸前自然展示该商品，商品正面朝向镜头且比例真实。"
            "保持主播脸部、发型、服装、表情、姿势、背景和光线不变；保持商品形状、颜色、文字和标志与图2一致。")


def _local_image(value, label):
    supplied = Path(str(value or ""))
    if supplied.is_symlink():
        raise ValueError(f"{label}不是普通图片文件")
    path = supplied.expanduser().resolve()
    if (not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
            or not 0 < path.stat().st_size <= MAX_INPUT_BYTES):
        raise ValueError(f"{label}不存在、格式无效或超过 100 MiB")
    return path


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def request_plan(*, avatar, product, product_name="", prompt=""):
    avatar_path = _local_image(avatar, "主播图")
    product_path = _local_image(product, "商品图")
    resolved_prompt = str(prompt).strip() or build_hold_prompt(product_name)
    if not 1 <= len(resolved_prompt) <= 4000:
        raise ValueError("持品提示词长度无效")
    return {
        "provider": "runninghub", "engine": "qwen21", "webapp_id": HOLD_PRODUCT_WEBAPP_ID,
        "aspect_ratio": HOLD_PRODUCT_ASPECT, "megapixels": "1", "uploads": [
            {"role": "avatar", "path": str(avatar_path), "sha256": _sha256(avatar_path)},
            {"role": "product", "path": str(product_path), "sha256": _sha256(product_path)},
        ], "prompt": resolved_prompt,
    }


def _check_body(response):
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("RunningHub 返回了无效 JSON")
    code = body.get("code")
    if code not in (None, 0, 200, "0", "200", "SUCCESS") or body.get("success") is False:
        message = body.get("msg") or body.get("message") or body.get("error") or "Unknown"
        raise RuntimeError(f"RunningHub 请求失败: {code or 'UNKNOWN'} {message}")
    return body


def submit_hold_task(*, api_key, avatar_remote, product_remote, prompt):
    if not str(api_key).strip():
        raise ValueError("RunningHub API Key 不能为空")
    nodes = [
        {"nodeId": "37", "fieldName": "image", "fieldValue": str(avatar_remote)},
        {"nodeId": "63", "fieldName": "image", "fieldValue": str(product_remote)},
        {"nodeId": "33", "fieldName": "aspect_ratio", "fieldValue": HOLD_PRODUCT_ASPECT},
        {"nodeId": "33", "fieldName": "megapixels", "fieldValue": "1"},
        {"nodeId": "32", "fieldName": "text", "fieldValue": str(prompt)},
    ]
    body = _check_body(requests.post(
        RH_BASE + "/task/openapi/ai-app/run", headers={"Content-Type": "application/json"},
        json={"webappId": HOLD_PRODUCT_WEBAPP_ID, "apiKey": api_key, "nodeInfoList": nodes,
              "instanceType": "default", "retainSeconds": 20}, timeout=(20, 60)))
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    task_id = data.get("taskId") or body.get("taskId")
    if not task_id:
        raise RuntimeError("RunningHub 未返回 taskId")
    return str(task_id)


def query_hold_task(*, api_key, task_id):
    body = _check_body(requests.post(
        RH_BASE + "/task/openapi/outputs", headers={"Content-Type": "application/json"},
        json={"apiKey": api_key, "taskId": task_id}, timeout=(20, 60)))
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    raw = str(data.get("status") or data.get("taskStatus") or body.get("status") or "").upper()
    outputs = data.get("outputs") or data.get("results") or data.get("output") or []
    if isinstance(outputs, dict):
        outputs = [outputs]
    urls = []
    for item in outputs:
        url = item if isinstance(item, str) else item.get("fileUrl") or item.get("url")
        if url:
            urls.append(str(url))
    direct = data.get("fileUrl") or body.get("fileUrl")
    if direct:
        urls.insert(0, str(direct))
    failed = raw in {"FAILED", "FAIL", "ERROR", "CANCELLED"}
    status = "failed" if failed else "success" if urls else "running" if raw in {
        "RUNNING", "PROCESSING"} else "queued"
    return {"task_id": str(task_id), "status": status, "image_url": urls[0] if urls else "",
            "fail_reason": (data.get("failedReason") or data.get("failReason") or
                            body.get("msg") or body.get("message") or "") if failed else ""}


def generate_hold_image(*, api_key, avatar, product, dest, product_name="", prompt="",
                        poll_interval=5, poll_timeout=900, cancel_check=None):
    if not 0 <= poll_interval <= 300 or not 1 <= poll_timeout <= 86400:
        raise ValueError("轮询间隔或超时无效")
    plan = request_plan(avatar=avatar, product=product, product_name=product_name, prompt=prompt)
    if cancel_check and cancel_check():
        raise InterruptedError("手持商品图生成已取消")
    avatar_remote = upload_file(api_key=api_key, file_path=plan["uploads"][0]["path"])
    if cancel_check and cancel_check():
        raise InterruptedError("手持商品图生成已取消")
    product_remote = upload_file(api_key=api_key, file_path=plan["uploads"][1]["path"])
    task_id = submit_hold_task(api_key=api_key, avatar_remote=avatar_remote,
                               product_remote=product_remote, prompt=plan["prompt"])
    deadline = time.monotonic() + poll_timeout
    last = None
    while time.monotonic() < deadline:
        if cancel_check and cancel_check():
            raise InterruptedError("手持商品图生成已取消")
        last = query_hold_task(api_key=api_key, task_id=task_id)
        if last["status"] == "success":
            output = download_image(last["image_url"], dest)
            return {**last, "image_path": str(output), "plan": plan}
        if last["status"] == "failed":
            raise RuntimeError(f"RunningHub 手持商品图失败: {last['fail_reason']}")
        time.sleep(poll_interval)
    raise TimeoutError(f"RunningHub 手持商品 taskId={task_id} 超时，最后状态={last}")
