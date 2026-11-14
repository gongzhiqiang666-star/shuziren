"""Recovered lifecycle methods for RecordLiveManager."""

import os
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from threading import Thread

from .local_voice import synthesize_local_audio


def _extract_real_shot_audio(video_path, audio_path, startupinfo=None):
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path, "-vn",
            "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1", audio_path,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
    )


def _mux_real_shot_video(video_path, audio_path, output_path, startupinfo=None):
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
            "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", output_path,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
    )


def _mix_real_shot_audio(original, narration, start_time, end_time):
    from pydub import AudioSegment

    original_duration = len(original)
    start_ms = min(original_duration, max(0, int(float(start_time) * 1000)))
    end_ms = min(original_duration, max(0, int(float(end_time) * 1000)))
    if end_ms <= start_ms:
        raise ValueError("报时音频替换区间必须位于原音轨内且结束时间大于开始时间")
    silence_duration = end_ms - start_ms
    part1 = original[:start_ms]
    part_middle_silence = AudioSegment.silent(
        duration=silence_duration, frame_rate=original.frame_rate
    )
    part3 = original[end_ms:]
    final_audio = part1 + part_middle_silence + part3
    return final_audio.overlay(narration, position=start_ms)


def stop_live(self) -> bool:
    """Stop the playback and ingest resources held by the manager."""
    errors = []
    if self.announcement_session.get("is_active"):
        try:
            self.cancel_announcement()
        except Exception as error:
            errors.append(error)
            self._cleanup_session()
    player, self.video_player = self.video_player, None
    if player is not None:
        try:
            player.stop()
        except Exception as error:
            errors.append(error)
    ingest, self.stream_ingest = self.stream_ingest, None
    if ingest is not None:
        try:
            ingest.stop()
        except Exception as error:
            errors.append(error)
    self.is_broadcasting = False
    if errors:
        self.last_error = f"停止录播直播时发生错误: {errors[0]}"
        return False
    return True


class RecordLiveManager:
    """Recovered manager state and stop behavior."""

    def __init__(self, main_config: dict):
        self.main_config = main_config
        self.video_player = None
        self.stream_ingest = None
        self.is_broadcasting = False
        self.last_error = ""
        self.announcement_session = {
            "is_active": False,
            "temp_files": [],
            "worker_thread": None,
        }

    def start_live(self, video_path, video_source_type="local", douyin_live_url="",
                   width=720, height=1280, output_mode="window", deduplication_config=None):
        from .video_player import Player

        self.last_error = ""
        if self.is_broadcasting:
            self.stop_live()
        try:
            source_type = str(video_source_type or "local").strip().lower()
            if source_type == "local":
                video_path = str(video_path or "")
                print(f"收到本地视频开播请求: {video_path}")
                if not os.path.exists(video_path):
                    self.last_error = f"本地视频文件不存在: {video_path}"
                    print(f"错误: {self.last_error}")
                    return False
                playback_source = os.path.abspath(video_path)
            elif source_type == "douyin":
                from .stream_ingest import LiveStreamIngestProcess

                douyin_live_url = str(douyin_live_url or "").strip()
                print(f"收到抖音转播开播请求: {douyin_live_url}")
                if not douyin_live_url:
                    self.last_error = "抖音直播间链接不能为空"
                    print(f"错误: {self.last_error}")
                    return False
                self.stream_ingest = LiveStreamIngestProcess(self.main_config)
                playback_source = self.stream_ingest.start(douyin_live_url)
            else:
                raise ValueError(f"不支持的视频源类型: {source_type}")
            frame_processor = None
            if deduplication_config and deduplication_config.get("enabled"):
                from .deduplication_processor import DeduplicationFrameProcessor

                frame_processor = DeduplicationFrameProcessor(deduplication_config)
            print("创建新的播放器实例。")
            player = Player(
                width=width,
                height=height,
                output_mode=output_mode,
                frame_processor=frame_processor,
            )
            self.video_player = player
            print("正在启动播放器...")
            self.video_player.start(playback_source, loop=True)
            self.is_broadcasting = True
            print("录播直播已成功启动。")
            return True
        except Exception as error:
            self.last_error = f"录播直播启动失败: {error}"
            print(self.last_error)
            print("错误详情:")
            traceback.print_exc()
            if self.video_player is not None:
                try:
                    self.video_player.stop()
                except Exception:
                    pass
                self.video_player = None
            if self.stream_ingest is not None:
                try:
                    self.stream_ingest.stop()
                except Exception:
                    pass
                self.stream_ingest = None
            self.is_broadcasting = False
            return False

    stop_live = stop_live

    def cancel_announcement(self) -> dict:
        if not self.announcement_session["is_active"]:
            return {"status": "success", "message": "没有活动的报时会话"}

        self._cleanup_session()
        return {"status": "success", "message": "报时会话已取消"}

    def _cleanup_session(self):
        for path in self.announcement_session.get("temp_files", []):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"已清理临时文件: {path}")
            except Exception as error:
                print(f"清理文件失败 {path}: {error}")

        self.announcement_session["is_active"] = False
        self.announcement_session["temp_files"] = []
        self.announcement_session["worker_thread"] = None

    def prepare_announcement(self, video_config: dict) -> dict:
        try:
            if not self.is_broadcasting or not self.video_player:
                return {"status": "error", "message": "必须先启动录播才能进行报时"}

            if self.announcement_session["is_active"]:
                print("注意：已有正在进行的报时任务，正在强制取消以启动新任务...")
                self.cancel_announcement()

            return self._prepare_real_shot_announcement(video_config)
        except Exception as error:
            self.cancel_announcement()
            return {"status": "error", "message": str(error)}

    def _prepare_real_shot_announcement(self, video_config):
        try:
            if not video_config:
                return {"status": "error", "message": "报时配置为空"}

            real_shot = video_config.get("real_shot", {})
            video_path = real_shot.get("video_path")
            start_time = real_shot.get("audio_replace_start", 0)
            end_time = real_shot.get("audio_replace_end", 0)
            if not video_path or not os.path.exists(video_path):
                return {"status": "error", "message": "实拍视频路径无效"}
            try:
                start_time = float(start_time)
                end_time = float(end_time)
            except (TypeError, ValueError):
                return {"status": "error", "message": "报时音频替换区间格式无效"}
            if start_time < 0 or end_time <= start_time:
                return {"status": "error", "message": "报时音频替换结束时间必须大于开始时间"}

            self.announcement_session["is_active"] = True
            self.announcement_session["temp_files"] = []
            worker = Thread(
                target=self._process_real_shot_task,
                args=(video_path, start_time, end_time, video_config),
                daemon=True,
            )
            self.announcement_session["worker_thread"] = worker
            worker.start()
            return {"status": "success", "message": "实拍视频处理已启动", "target_time": 0, "voice_speed": 0}
        except Exception as error:
            self.cancel_announcement()
            return {"status": "error", "message": f"实拍模式启动失败: {error}"}

    def _process_real_shot_task(self, video_path, start_time, end_time, video_config):
        from pydub import AudioSegment

        session = self.announcement_session
        worker = session["worker_thread"]
        output = None
        inserted = False
        try:
            print(f"[RealShot] 开始处理实拍视频: {video_path}, 替换区间: {start_time}s - {end_time}s")
            template = video_config.get("audio_text_template", video_config.get("audio_text") or "{time}")
            text = template.format(time=datetime.now().strftime("%H点%M分"))
            narration_path = self._synthesize_local_audio(
                text=text, speed=video_config.get("voice_speed", 1.1), video_config=video_config
            )
            if not narration_path or not os.path.exists(narration_path):
                raise FileNotFoundError("报时音频生成失败")

            work_dir = Path(__file__).resolve().parent.parent / "temp" / "real_shot_temp"
            work_dir.mkdir(parents=True, exist_ok=True)
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            with TemporaryDirectory(dir=work_dir) as temporary:
                original_path = Path(temporary) / "original.wav"
                mixed_path = Path(temporary) / "mixed.wav"
                _extract_real_shot_audio(video_path, original_path, startupinfo)
                original = AudioSegment.from_wav(original_path)
                narration = AudioSegment.from_file(narration_path)
                mixed = _mix_real_shot_audio(original, narration, start_time, end_time)
                with mixed.export(mixed_path, format="wav"):
                    pass
                output = work_dir / f"output_{uuid4().hex}.mp4"
                _mux_real_shot_video(video_path, mixed_path, output, startupinfo)
            print(f"[RealShot] 视频生成成功: {output}")

            if session["worker_thread"] is worker and session["is_active"]:
                if self.video_player and self.is_broadcasting:
                    session["temp_files"].append(str(output))
                    try:
                        self.video_player.insert_video(str(output))
                        inserted = True
                        if str(output) in session["temp_files"]:
                            session["temp_files"].remove(str(output))
                        print("[RealShot] 自动插入视频")
                    except Exception as error:
                        print(f"[RealShot] 自动插入失败: {error}")
                else:
                    print("[RealShot] 播放器已停止，放弃插入")
        except Exception as error:
            print(f"[RealShot] 处理失败: {error}")
        finally:
            if output is not None and not inserted:
                try:
                    Path(output).unlink(missing_ok=True)
                except OSError as error:
                    print(f"[RealShot] 清理未插入成片失败: {error}")
            if session["worker_thread"] is worker:
                print("[RealShot] 任务完成，自动结束会话")
                self._cleanup_session()

    def _synthesize_local_audio(self, text: str, speed: float, video_config: dict) -> str:
        voice_id = str(video_config.get("voice_id") or "").strip()
        if not voice_id:
            raise ValueError("未配置本地声音ID (voice_id)")

        return synthesize_local_audio(self.main_config, voice_id, text, speed)
