"""Recovered queued PyAudio player used for announcements and danmu speech."""

from __future__ import annotations

import queue
import os
import subprocess
import threading
import time
from uuid import uuid4


def scan_audio_files(directory):
    """Return MP3/WAV files in the directory's native enumeration order."""
    audio_files = []
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) and filename.lower().endswith((".mp3", ".wav")):
            audio_files.append(file_path)
    return audio_files


class AudioPlayer:
    def __init__(self):
        import pyaudio

        self.normal_queue = queue.Queue()
        self.danmu_queue = queue.Queue()
        self.player = pyaudio.PyAudio()
        self.is_active = False
        self.stop_flag = False
        self.play_thread = None
        self.channels = 2
        self.rate = 44100
        self.chunk_size = 1024
        self.stream = None
        self.is_playing = False
        self._ffmpeg_error_printed = False
        self.output_device_index = None
        self._closed = False

    def start(self):
        if self._closed:
            raise RuntimeError("音频播放器已关闭")
        if self.is_active:
            return False
        self.stop_flag = False
        self.is_active = True
        self.play_thread = threading.Thread(target=self._play_audio_thread)
        self.play_thread.daemon = True
        self.play_thread.start()
        print("音频播放器已启动")
        return True

    def stop(self):
        self.stop_flag = True
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=2)
        self.is_active = False
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.is_playing = False
        print("音频播放器已停止")

    def set_output_device(self, device_index):
        if device_index is not None and type(device_index) is not int:
            raise ValueError("输出设备编号必须是整数")
        if self.is_active or self.is_playing:
            raise RuntimeError("播放中不能切换输出设备")
        self.output_device_index = device_index

    def close(self):
        if self._closed:
            return
        self.stop()
        self.player.terminate()
        self._closed = True

    def insert_audio(self, audio_path, queue_type="normal"):
        if queue_type.lower() == "danmu":
            self.danmu_queue.put(audio_path)
        else:
            self.normal_queue.put(audio_path)

    def _play_audio_thread(self):
        while not self.stop_flag:
            if not self.danmu_queue.empty():
                audio_path = self.danmu_queue.get()
                self._play_audio_file(audio_path)
                continue
            if not self.normal_queue.empty():
                audio_path = self.normal_queue.get()
                self._play_audio_file(audio_path)
                continue
            time.sleep(0.1)

    def _convert_audio_with_ffmpeg(self, input_path: str):
        target_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "..", "temp", "converted_audio_for_player",
        )
        os.makedirs(target_dir, exist_ok=True)
        output_filename = f"{uuid4()}.wav"
        output_path = os.path.join(target_dir, output_filename)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        command = [
            "ffmpeg", "-i", input_path,
            "-ar", str(self.rate),
            "-ac", str(self.channels),
            "-acodec", "pcm_s16le",
            "-y", "-hide_banner", "-loglevel", "error",
            output_path,
        ]
        try:
            subprocess.run(command, check=True, startupinfo=startupinfo)
            return output_path
        except FileNotFoundError:
            if not self._ffmpeg_error_printed:
                print("\n==================================================")
                print("!! 严重错误: `ffmpeg` 命令未找到 !!")
                print("请确保 ffmpeg 已被正确安装，并且其可执行文件路径已添加到系统的 PATH 环境变量中。")
                print("您可以从官网下载: https://ffmpeg.org/download.html")
                print("在问题解决前，音频播放功能将无法正常工作。")
                print("==================================================\n")
                self._ffmpeg_error_printed = True
            return None
        except subprocess.CalledProcessError:
            print(f"ffmpeg 转换音频 '{input_path}' 失败。文件可能已损坏或格式不受支持。")
            return None
        except Exception as error:
            print(f"执行ffmpeg时发生未知错误: {error}")
            return None

    def _play_audio_file(self, audio_path):
        from pydub import AudioSegment
        from pydub.utils import make_chunks

        converted_path = None
        self.is_playing = True
        try:
            converted_path = self._convert_audio_with_ffmpeg(audio_path)
            if not converted_path:
                print(f"音频转换失败，跳过播放: {audio_path}")
                return

            sound = AudioSegment.from_wav(converted_path)
            sound = sound.set_channels(self.channels)
            sound = sound.set_frame_rate(self.rate)
            chunks = make_chunks(sound, self.chunk_size)
            open_options = dict(
                format=self.player.get_format_from_width(sound.sample_width),
                channels=self.channels,
                rate=self.rate,
                output=True,
            )
            if self.output_device_index is not None:
                open_options["output_device_index"] = self.output_device_index
            self.stream = self.player.open(**open_options)
            for chunk in chunks:
                if self.stop_flag:
                    break
                if hasattr(self.stream, "is_stopped") and self.stream.is_stopped():
                    break
                self.stream.write(chunk._data)
        except Exception as error:
            print(f"播放音频时出错: {error}")
        finally:
            if self.stream is not None:
                try:
                    if hasattr(self.stream, "is_stopped") and not self.stream.is_stopped():
                        self.stream.stop_stream()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            if converted_path and os.path.exists(converted_path):
                try:
                    os.remove(converted_path)
                except OSError as error:
                    print(f"删除临时文件失败: {error}")
            self.is_playing = False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
