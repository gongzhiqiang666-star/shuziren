"""Source-controlled RunningHub LTX held-product motion adapter."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from .audio_duration import get_audio_duration
from .runninghub_talk import download_file, query_talk_task, upload_file


RH_BASE = "https://www.runninghub.cn"
LTX_WEBAPP_ID = "2031016553440878594"
DEFAULT_PROMPT = "保持镜头稳定，双手手持商品讲解"
DEFAULT_FPS = 25.0
LTX_LONG_EDGE = {"480p": 864, "720p": 1280, "1080p": 1536}


def normalize_ltx_res(value):
    text = str(value or "").lower().strip().removesuffix("p")
    return text + "p" if text in {"480", "720", "1080"} else "480p"


def resolve_ltx_long_edge(value="480p"):
    if type(value) is int and value in LTX_LONG_EDGE.values():
        return value
    return LTX_LONG_EDGE[normalize_ltx_res(value)]


def default_ltx_instance(max_res, low_cost=False):
    edge = resolve_ltx_long_edge(max_res)
    return "plus" if edge == 1536 or not low_cost else "default"


def _body(response):
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("RunningHub 返回了无效 JSON")
    code = value.get("code")
    if code not in (None, 0, 200, "0", "200", "SUCCESS") or value.get("success") is False:
        message = value.get("msg") or value.get("message") or value.get("error") or "Unknown"
        raise RuntimeError(f"RunningHub 请求失败: {code or 'UNKNOWN'} {message}")
    return value


def create_ltx_task(*, api_key, image_remote, audio_remote, prompt, duration_s,
                    max_res=864, fps=DEFAULT_FPS, instance_type=None,
                    webapp_id=LTX_WEBAPP_ID, full_audio=False,
                    action_prompt=DEFAULT_PROMPT, retain_seconds=0):
    if not str(api_key).strip():
        raise ValueError("RunningHub API Key 不能为空")
    edge = resolve_ltx_long_edge(max_res)
    rate = float(fps)
    if not 1 <= rate <= 60:
        raise ValueError("LTX 帧率无效")
    duration = float(duration_s)
    if not 0 < duration <= 3600:
        raise ValueError("LTX 音频时长无效")
    instance = str(instance_type or default_ltx_instance(edge)).strip()
    if instance not in {"default", "plus"}:
        raise ValueError("LTX 实例类型无效")
    nodes = [
        {"nodeId": "444", "fieldName": "image", "fieldValue": str(image_remote),
         "description": "人物图（9:16比例或16:9比例效果更佳）"},
        {"nodeId": "1755", "fieldName": "audio", "fieldValue": str(audio_remote),
         "description": "上传歌曲or语音"},
        {"nodeId": "1583", "fieldName": "value", "fieldValue": "0",
         "description": "生成秒数（35秒内更佳、0=整段音频）"},
        {"nodeId": "1776", "fieldName": "value", "fieldValue": "0",
         "description": "音频从几秒开始对口型"},
        {"nodeId": "1624", "fieldName": "value", "fieldValue": str(action_prompt or DEFAULT_PROMPT),
         "description": "动作提示词"},
        {"nodeId": "1606", "fieldName": "value", "fieldValue": str(edge),
         "description": "最大分辨率（小于1600，越大越慢）"},
        {"nodeId": "1586", "fieldName": "value", "fieldValue": str(rate), "description": "帧率"},
    ]
    payload = {"webappId": str(webapp_id), "apiKey": api_key, "nodeInfoList": nodes,
               "instanceType": instance}
    if int(retain_seconds) > 0:
        payload["retainSeconds"] = int(retain_seconds)
    body = _body(requests.post(RH_BASE + "/task/openapi/ai-app/run",
                               headers={"Content-Type": "application/json"}, json=payload,
                               timeout=(20, 60)))
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    task_id = data.get("taskId") or body.get("taskId")
    if not task_id:
        raise RuntimeError("RunningHub 未返回 taskId")
    return str(task_id)


def generate_ltx_video(*, api_key, image_path, audio_path, dest, prompt="", audio_duration=None,
                       video_res="480p", max_res=None, fps=DEFAULT_FPS, poll_interval=10,
                       poll_timeout=2400, instance_type=None, webapp_id=LTX_WEBAPP_ID,
                       full_audio=False, action_prompt=DEFAULT_PROMPT, low_cost=False,
                       cancel_check=None):
    if not 0 <= poll_interval <= 300 or not 1 <= poll_timeout <= 86400:
        raise ValueError("轮询间隔或超时无效")
    edge = resolve_ltx_long_edge(max_res if max_res is not None else video_res)
    instance = instance_type or default_ltx_instance(edge, low_cost)
    retain = 20 if low_cost and instance == "default" else 0
    if cancel_check and cancel_check():
        raise InterruptedError("手持商品动作视频生成已取消")
    image_remote = upload_file(api_key=api_key, file_path=image_path)
    if cancel_check and cancel_check():
        raise InterruptedError("手持商品动作视频生成已取消")
    audio_remote = upload_file(api_key=api_key, file_path=audio_path)
    duration = float(audio_duration) if audio_duration is not None else get_audio_duration(str(audio_path))
    task_id = create_ltx_task(
        api_key=api_key, image_remote=image_remote, audio_remote=audio_remote, prompt=prompt,
        duration_s=duration, max_res=edge, fps=fps, instance_type=instance, webapp_id=webapp_id,
        full_audio=full_audio, action_prompt=action_prompt, retain_seconds=retain)
    deadline = time.monotonic() + poll_timeout
    last = None
    while time.monotonic() < deadline:
        if cancel_check and cancel_check():
            raise InterruptedError("手持商品动作视频生成已取消")
        last = query_talk_task(api_key=api_key, task_id=task_id)
        if last["status"] == "success":
            if cancel_check and cancel_check():
                raise InterruptedError("手持商品动作视频生成已取消")
            output = download_file(last["video_url"], dest)
            if cancel_check and cancel_check():
                Path(output).unlink(missing_ok=True)
                raise InterruptedError("手持商品动作视频生成已取消")
            return {**last, "video_path": str(output), "max_res": edge, "instance_type": instance}
        if last["status"] == "failed":
            raise RuntimeError(f"RunningHub LTX 失败: {last['fail_reason']}")
        time.sleep(poll_interval)
    raise TimeoutError(f"RunningHub LTX taskId={task_id} 超时，最后状态={last}")
