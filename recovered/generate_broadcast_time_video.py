"""Recovered image-to-video announcement generation utilities."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml

from .audio_duration import get_audio_duration


def image_to_base64(image_path: str) -> Optional[str]:
    path = Path(image_path)
    if not path.is_file():
        return None
    content_type = get_content_type(str(path))
    return f"data:{content_type};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _get_media_duration(file_path: str) -> float:
    try:
        return get_audio_duration(file_path)
    except Exception as error:
        raise RuntimeError(f"Error getting duration for {file_path}: {error}") from error


def _ffmpeg() -> str:
    configured = os.environ.get("FFMPEG_HOME", "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_dir():
            candidate /= "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not found:
        raise RuntimeError("未找到 ffmpeg")
    return found


def _generate_lip_sync_video_api_call(video_path: str, audio_path: str,
                                      output_path: str,
                                      config: Optional[Dict[str, Any]] = None) -> bool:
    settings = config or {}
    server_url = str(settings.get("server_url") or "").rstrip("/")
    if not server_url:
        return False
    headers = {"token": str(settings.get("token") or "")}
    with open(video_path, "rb") as video_file, open(audio_path, "rb") as audio_file:
        response = requests.post(
            server_url + "/video/generate_lip_sync", headers=headers,
            files={"video": (Path(video_path).name, video_file, "video/mp4"),
                   "audio": (Path(audio_path).name, audio_file, get_content_type(audio_path))},
            timeout=float(settings.get("submit_timeout", 120)),
        )
    response.raise_for_status()
    payload = response.json()
    task_id = payload.get("task_id") or payload.get("id")
    if not task_id:
        return False
    deadline = time.monotonic() + float(settings.get("poll_timeout", 900))
    while time.monotonic() < deadline:
        status = requests.get(server_url + "/video/get_lip_sync_status",
                              headers=headers, params={"task_id": task_id}, timeout=30)
        status.raise_for_status()
        result = status.json()
        state = str(result.get("status") or "").lower()
        if state in {"success", "succeeded", "completed"}:
            url = result.get("video_url") or result.get("url")
            download = requests.get(url, timeout=120); download.raise_for_status()
            Path(output_path).write_bytes(download.content)
            return True
        if state in {"failed", "error", "cancelled"}:
            return False
        time.sleep(float(settings.get("poll_interval", 3)))
    return False


def _loop_and_combine_with_audio(video_path: str, audio_path: str, temp_dir: str,
                                 enable_lip_sync: bool = False,
                                 lip_sync_config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    video, audio = Path(video_path), Path(audio_path)
    if not video.is_file() or not audio.is_file():
        return None
    temp = Path(temp_dir); temp.mkdir(parents=True, exist_ok=True)
    reversed_video_path = temp / "reversed.mp4"
    looped_video_path = temp / "looped.mp4"
    padded_audio_path = temp / "padded_audio.wav"
    final_video_path = temp / "final_video.mp4"
    ffmpeg = _ffmpeg()
    commands = [
        [ffmpeg, "-y", "-i", str(video), "-vf", "reverse", "-an", str(reversed_video_path)],
        [ffmpeg, "-y", "-i", str(video), "-i", str(reversed_video_path), "-filter_complex",
         "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", str(looped_video_path)],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr[-1500:])
    looped_duration = _get_media_duration(str(looped_video_path))
    result = subprocess.run([ffmpeg, "-y", "-i", str(audio), "-af", "apad",
                             "-t", f"{looped_duration:.3f}", str(padded_audio_path)],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])
    if enable_lip_sync and _generate_lip_sync_video_api_call(
            str(looped_video_path), str(padded_audio_path), str(final_video_path), lip_sync_config):
        return str(final_video_path)
    result = subprocess.run([ffmpeg, "-y", "-i", str(looped_video_path), "-i", str(padded_audio_path),
                             "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_video_path)],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])
    return str(final_video_path)


def _get_full_config() -> Dict[str, Any]:
    candidates = [Path.cwd() / "config/config.yaml",
                  Path(__file__).resolve().parent.parent / "config/config.yaml"]
    for path in candidates:
        if path.is_file():
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return value if isinstance(value, dict) else {}
    return {}


def _load_video_announcement_config() -> Dict[str, Any]:
    value = _get_full_config().get("video_announcement") or {}
    return dict(value) if isinstance(value, dict) else {}


def get_video_ratio(video_path: str) -> str:
    ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not ffprobe:
        raise RuntimeError("未找到 ffprobe")
    result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height", "-of", "json", video_path],
                            capture_output=True, text=True, check=True)
    stream = (json.loads(result.stdout).get("streams") or [{}])[0]
    width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    if not width or not height:
        raise ValueError("视频分辨率无效")
    return "9:16" if height > width else ("1:1" if abs(width - height) / max(width, height) < .08 else "16:9")


def get_content_type(file_path: str) -> str:
    overrides = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                 ".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4"}
    return overrides.get(Path(file_path).suffix.lower(), mimetypes.guess_type(file_path)[0] or "application/octet-stream")


def _download(url: str, suffix: str = ".mp4") -> str:
    response = requests.get(url, timeout=180); response.raise_for_status()
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    with handle:
        handle.write(response.content)
    return handle.name


def _poll_json(url: str, *, headers: Dict[str, str], payload: Dict[str, Any],
               timeout: float = 900, interval: float = 5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status(); result = response.json()
        state = str(result.get("status") or result.get("task_status") or "").lower()
        if state in {"success", "succeeded", "completed"}:
            return result
        if state in {"failed", "error", "cancelled"}:
            raise RuntimeError(result.get("message") or result.get("status_msg") or state)
        time.sleep(interval)
    raise TimeoutError("视频生成任务超时")


def generate_video_from_image_minimax(image_path: str, prompt: str, audio_path: str,
                                      api_key: str, enable_lip_sync: bool,
                                      lip_sync_config: Optional[dict] = None) -> Optional[str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = requests.post("https://api.minimaxi.com/v1/video_generation", headers=headers,
                             json={"model": "video-01", "prompt": prompt,
                                   "first_frame_image": image_to_base64(image_path)}, timeout=60)
    response.raise_for_status(); task_id = response.json().get("task_id")
    result = _poll_json("https://api.minimaxi.com/v1/query/video_generation", headers=headers,
                        payload={"task_id": task_id})
    file_id = result.get("file_id")
    retrieve = requests.get("https://api.minimaxi.com/v1/files/retrieve",
                            headers=headers, params={"file_id": file_id}, timeout=60)
    retrieve.raise_for_status(); url = retrieve.json().get("file", {}).get("download_url") or retrieve.json().get("download_url")
    generated = _download(url)
    with tempfile.TemporaryDirectory(prefix="broadcast_video_") as directory:
        final = _loop_and_combine_with_audio(generated, audio_path, directory,
                                             enable_lip_sync, lip_sync_config)
        if not final: return None
        stable = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        shutil.copy2(final, stable); return stable


def generate_video_from_image_siliconflow(image_path: str, prompt: str, audio_path: str,
                                          api_key: str, enable_lip_sync: bool,
                                          lip_sync_config: Optional[dict] = None) -> Optional[str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = requests.post("https://api.siliconflow.cn/v1/video/submit", headers=headers,
                             json={"model": "Wan-AI/Wan2.1-I2V-14B-720P", "prompt": prompt,
                                   "image": image_to_base64(image_path)}, timeout=60)
    response.raise_for_status(); task_id = response.json().get("requestId") or response.json().get("task_id")
    result = _poll_json("https://api.siliconflow.cn/v1/video/status", headers=headers,
                        payload={"requestId": task_id})
    url = result.get("video_url") or (result.get("results") or {}).get("videos", [{}])[0].get("url")
    generated = _download(url)
    with tempfile.TemporaryDirectory(prefix="broadcast_video_") as directory:
        final = _loop_and_combine_with_audio(generated, audio_path, directory, enable_lip_sync, lip_sync_config)
        if not final: return None
        stable = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        shutil.copy2(final, stable); return stable


def _generate_video_from_image_aliyun(image_path: str, prompt: str, audio_path: str,
                                      api_key: str, model: str, enable_lip_sync: bool,
                                      lip_sync_config: Optional[dict] = None) -> Optional[str]:
    headers = {"Authorization": f"Bearer {api_key}", "X-DashScope-Async": "enable",
               "Content-Type": "application/json"}
    endpoint = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
    response = requests.post(endpoint, headers=headers,
                             json={"model": model, "input": {"prompt": prompt,
                                                               "img_url": image_to_base64(image_path)}}, timeout=60)
    response.raise_for_status(); task_id = response.json().get("output", {}).get("task_id")
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        query = requests.get(f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}", headers=headers, timeout=60)
        query.raise_for_status(); result = query.json(); state = result.get("output", {}).get("task_status")
        if state == "SUCCEEDED":
            generated = _download(result["output"]["video_url"]); break
        if state == "FAILED": raise RuntimeError(result.get("message", "DashScope video failed"))
        time.sleep(5)
    else: raise TimeoutError("DashScope 视频生成超时")
    with tempfile.TemporaryDirectory(prefix="broadcast_video_") as directory:
        final = _loop_and_combine_with_audio(generated, audio_path, directory, enable_lip_sync, lip_sync_config)
        if not final: return None
        stable = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        shutil.copy2(final, stable); return stable


def generate_video_from_image(image_path: str, prompt: str, audio_path: str,
                              api_key_or_config: Any) -> Optional[str]:
    config = api_key_or_config if isinstance(api_key_or_config, dict) else {"api_key": api_key_or_config}
    provider = str(config.get("provider") or "aliyun").lower()
    common = (image_path, prompt, audio_path, str(config.get("api_key") or ""),
              bool(config.get("enable_lip_sync", False)), config.get("lip_sync_config"))
    if provider == "minimax": return generate_video_from_image_minimax(*common)
    if provider in {"siliconflow", "silicon_flow"}: return generate_video_from_image_siliconflow(*common)
    return _generate_video_from_image_aliyun(image_path, prompt, audio_path, common[3],
                                             str(config.get("model") or "wanx2.1-i2v-turbo"), common[4], common[5])
