"""Validate the real local IP media pipeline with one recoverable failure."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import yaml

from recovered.main import Api
from recovered.add_subtitles_to_video import DEFAULT_SUBTITLE_STYLE_PRESET
from scripts.avatar_store import AvatarStore
from scripts.voice_store import VoiceStore
from scripts.v122_acceleration import configure_runtime


class ValidationApi(Api):
    def __init__(self, runtime_internal, data_root, config):
        self.runtime_dir = Path(runtime_internal).resolve()
        self.data_root = Path(data_root).resolve()
        self.config = config
        self.calls = []
        self.fail_subtitles_once = True

    def _get_ip_agent_base_dir(self):
        return str(self.data_root / "projects")

    def generate_audio_for_ip_agent_project(self, project_id, data):
        self.calls.append("audio")
        return super().generate_audio_for_ip_agent_project(project_id, data)

    def create_ip_agent_video(self, project_id, data):
        self.calls.append("video")
        return super().create_ip_agent_video(project_id, data)

    def add_subtitles_to_ip_agent_video(self, project_id, data):
        self.calls.append("subtitles")
        result = super().add_subtitles_to_ip_agent_video(project_id, data)
        if result.get("status") == "success" and self.fail_subtitles_once:
            self.fail_subtitles_once = False
            return {"status": "error", "message": "injected failure after real subtitle render"}
        return result

    def apply_ip_agent_finishing(self, project_id, data):
        self.calls.append("finishing")
        return super().apply_ip_agent_finishing(project_id, data)

    def generate_ip_agent_publish_meta(self, project_id, data):
        self.calls.append("publish_meta")
        project = self._load_ip_agent_project(project_id)
        project.update({"publish_title": "本机全链验证", "publish_tags_text": "#数字人 #验证"})
        project = self._save_ip_agent_project(project_id, project)
        return {"status": "success", "title": project["publish_title"],
                "tags": ["数字人", "验证"], "project": project}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def probe_media(ffprobe, path):
    result = subprocess.run(
        [str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=60,
    )
    body = json.loads(result.stdout)
    video = next(item for item in body["streams"] if item["codec_type"] == "video")
    audio = next(item for item in body["streams"] if item["codec_type"] == "audio")
    return {"width": int(video["width"]), "height": int(video["height"]),
            "video_codec": video["codec_name"], "audio_codec": audio["codec_name"],
            "duration": float(body["format"]["duration"])}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--source-voice-data", required=True, type=Path)
    parser.add_argument("--source-avatar-directory", required=True, type=Path)
    parser.add_argument("--report-directory", required=True, type=Path)
    args = parser.parse_args(argv)

    # configure_runtime changes the process working directory to the packaged
    # runtime. Resolve every caller path before that intentional side effect.
    source_voice_data = args.source_voice_data.resolve()
    source_avatar_directory = args.source_avatar_directory.resolve()
    report_directory = args.report_directory.resolve()
    internal = configure_runtime(args.runtime_root.resolve())
    config = yaml.safe_load((internal / "config/config.yaml").read_text(encoding="utf-8"))
    config.update({
        "models_base_path": str(internal / "assets/pretrained_models"),
        "voice_base_dir": str(source_voice_data / "voices"),
        "image_base_dir": str(source_avatar_directory.parent),
        "voice_infer_version": "v3",
        "project_root": str(internal),
    })
    ffmpeg_dir = internal / "env/ffmpeg/bin"
    os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
    voice_id = VoiceStore(source_voice_data).selected()
    if not voice_id:
        raise RuntimeError("没有已选择的参考音")
    avatar_id = source_avatar_directory.name
    # Validate the prepared avatar before handing it to the media pipeline.
    AvatarStore(source_avatar_directory.parents[1]).get(avatar_id)

    root = report_directory / ("run-" + str(int(time.time())))
    root.mkdir(parents=True, exist_ok=False)
    api = ValidationApi(internal, root, config)
    project = api.create_ip_agent_project("真实一键成片验证")["project"]
    subtitle = Path(project["subtitle_path"])
    subtitle.parent.mkdir(parents=True, exist_ok=True)
    subtitle.write_text("1\n00:00:00,000 --> 00:00:08,000\n这是本机真实一键成片链路验证。\n", encoding="utf-8")
    data = {
        "text": "这是本机真实一键成片链路验证，需要完成语音、数字人口型、字幕和最终视频处理。",
        "voice_id": voice_id, "voice_base_dir": config["voice_base_dir"],
        "voice_infer_version": "v3", "language": "zh-CN", "speed": 1.0,
        "use_cache": False, "model_id": avatar_id, "subtitle_path": str(subtitle),
        "style_preset": DEFAULT_SUBTITLE_STYLE_PRESET, "bgm_enabled": False,
    }
    started = time.time()
    first = api.one_click_create_ip_agent_video(project["id"], data)
    if first.get("failed_step") != "subtitles" or not first.get("resumable"):
        raise RuntimeError(f"字幕故障没有正确持久化: {first}")
    failed_project = api._load_ip_agent_project(project["id"])
    if not Path(failed_project["audio_path"]).is_file() or not Path(failed_project["video_path"]).is_file():
        raise RuntimeError("故障后已完成的真实音频或视频丢失")
    if Path(failed_project["subtitle_video_path"]).exists():
        raise RuntimeError("故障后字幕半成品未回滚")

    second = api.one_click_create_ip_agent_video(project["id"], data)
    if second.get("status") != "success":
        raise RuntimeError(f"续跑失败: {second}")
    calls_after_resume = list(api.calls)
    third = api.one_click_create_ip_agent_video(project["id"], data)
    if not third.get("already_complete") or api.calls != calls_after_resume:
        raise RuntimeError("完成后重试不幂等")
    final = api._load_ip_agent_project(project["id"])
    paths = {name: final[name] for name in ("audio_path", "video_path", "subtitle_path",
                                            "subtitle_video_path", "final_video_path")}
    if not all(Path(path).is_file() and Path(path).stat().st_size for path in paths.values()):
        raise RuntimeError("全链产物不完整")
    media = probe_media(ffmpeg_dir / "ffprobe.exe", paths["final_video_path"])
    subprocess.run([str(ffmpeg_dir / "ffmpeg.exe"), "-v", "error", "-i", paths["final_video_path"],
                    "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "NUL"],
                   check=True, timeout=120)
    report = {
        "status": "passed", "wall_seconds": time.time() - started,
        "first_failed_step": first["failed_step"], "first_resumable": first["resumable"],
        "calls": api.calls, "completed_steps": final["one_click_pipeline"]["completed_steps"],
        "already_complete": third["already_complete"], "media": media,
        "artifacts": {name: {"bytes": Path(path).stat().st_size, "sha256": sha256(path)}
                      for name, path in paths.items()},
    }
    (root / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(root / "result.json"), **report}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
