"""Recovered application entry point for the plugin and WebView integration."""

import json
import os
import shutil
import subprocess
import sys
import yaml
from datetime import datetime
from pathlib import Path
from threading import Event, RLock
from tempfile import TemporaryDirectory

from .clone_manager import CloneManager, VOICE_OPTIMIZE_MAX_SECONDS, VOICE_OPTIMIZE_SAMPLE_RATE, VOICE_OPTIMIZE_SAMPLE_TEXT
from .audio_duration import get_audio_duration
from .add_subtitles_to_video import DEFAULT_SUBTITLE_STYLE_PRESET
from .cosyvoice import clone_voice_cosyvoice, synthesize_speech_cosyvoice
from .live_manager_runtime import LiveManager
from .digital_live_params import build_local_params, is_required_video_fps, validate_video_drive_assets
from .face_hand_live_manager import FaceHandLiveManager
from .face_hand_video_group import validate_face_hand_video_group
from .main_config import load_effective_config, resolve_user_config_path
from .main_plugins import PluginInstallerApi
from .main_shutdown import _shutdown_srs, force_exit
from .main_webview import (append_timestamp, configure_webview_debugging,
                           get_environment_config, normalize_environment_config,
                           resolve_webview_url, run_webview)
from .main_environment import (configure_cmd_window_content as _configure_cmd_window_content_impl,
                               get_distribution_root, get_gpu_info,
                               initialize_environment, _initialize_environment,
                               read_startup_admin_id as _read_startup_admin_id_impl,
                               resolve_environment_dir)
from .minimax import clone_voice_minimax
from .output_resolution import resolve_portrait_size
from .record_live_manager import RecordLiveManager
from .video_player import _open_media_source
from .win_power_throttling import ensure_high_performance
from .srs_runtime import start_bundled_srs, srs_process_status


def _configure_cmd_window_content():
    return _configure_cmd_window_content_impl()


def _read_startup_admin_id():
    return _read_startup_admin_id_impl()


def _bounded_read_bytes(path, maximum, label):
    path = Path(path)
    size = path.stat().st_size
    if size > maximum:
        raise ValueError(f"{label}超过大小限制")
    data = path.read_bytes()
    if len(data) != size:
        raise OSError(f"{label}读取期间发生变化")
    return data


class Api(PluginInstallerApi):
    _INLINE_MEDIA_MAX_BYTES = 64 * 1024 * 1024
    _TOKEN_MAX_CHARS = 16 * 1024

    @staticmethod
    def _default_runtime_dir():
        bundled = Path(__file__).resolve().parent.parent / "yunchuang_v122" / "_internal"
        return bundled if bundled.is_dir() else Path(__file__).resolve().parent

    def __init__(self):
        runtime_dir = self._default_runtime_dir()
        config = load_effective_config(runtime_dir, resolve_user_config_path())
        self._initialize(runtime_dir, config)

    @classmethod
    def _create(cls, runtime_dir, config=None):
        instance = cls.__new__(cls)
        runtime_dir = Path(runtime_dir).expanduser().resolve()
        if config is None:
            config = load_effective_config(runtime_dir, resolve_user_config_path())
        instance._initialize(runtime_dir, config)
        return instance

    def _initialize(self, runtime_dir, config):
        super().__init__(runtime_dir)
        self.runtime_dir = runtime_dir
        self.base_dir = str(runtime_dir)
        self.config = {} if config is None else config
        self._digital_live_manager = LiveManager(self.config)
        self._record_live_manager = RecordLiveManager({} if config is None else config)
        self._face_hand_live_manager = FaceHandLiveManager({} if config is None else config)
        self._clone_manager = CloneManager(self.config)
        self._live_lifecycle_lock = RLock()
        self._live_sticker_generation_lock = RLock()
        self._live_sticker_cancel_events = {}
        self._cloud_dh_generation_lock = RLock()
        self._cloud_dh_cancel_events = {}
        self._ip_publish_lock = RLock()
        self._ip_publish_active = set()
        self._shutdown_complete = False
        self._live_action_assistant_process = None
        self._audio_editor_process = None
        self.srs_process = _start_srs(runtime_dir)

    @staticmethod
    def _resolve_user_config_path():
        return resolve_user_config_path()

    @staticmethod
    def _write_yaml_atomic(path, config):
        from .main_config import write_user_config
        write_user_config(path, config)

    def _load_user_config(self):
        from .main_config import load_user_config
        return load_user_config(self._resolve_user_config_path())

    def _save_user_config(self, updates):
        from .main_config import save_user_config
        save_user_config(self._resolve_user_config_path(), updates)

    @classmethod
    def _merge_config(cls, target, updates):
        from .main_config import merge_config
        merge_config(target, updates)

    @classmethod
    def _extract_private_config(cls, value):
        from .main_config import extract_private_config
        return extract_private_config(value)

    @classmethod
    def _clear_private_config(cls, value):
        from .main_config import clear_private_config
        clear_private_config(value)

    def _load_config(self):
        return load_effective_config(self.runtime_dir, self._resolve_user_config_path())

    def _asset_roots(self):
        runtime = Path(self.runtime_dir).resolve()
        values = [runtime, runtime / "_internal", runtime.parent / "_internal"]
        return list(dict.fromkeys(path for path in values if path.is_dir()))

    def _find_asset(self, relative):
        relative = Path(relative)
        if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            raise ValueError("资源路径无效")
        for root in self._asset_roots():
            candidate = (root / relative).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if candidate.exists(): return candidate
        return self._asset_roots()[0] / relative

    @staticmethod
    def _read_admin_id():
        return _read_startup_admin_id()

    def get_admin_id(self):
        try:
            path = self._find_asset("assets/web/id.txt")
            if path.is_file():
                value = _bounded_read_bytes(path, 128, "管理员ID").decode("utf-8").strip()
                if value.isdigit():
                    return {"status": "success", "admin_id": int(value)}
            return {"status": "success", "admin_id": None}
        except Exception as error:
            print(f"获取管理员ID失败: {error}")
            return {"error": str(error)}

    def get_token(self):
        try:
            return {"status": "success", "token": self.config.get("token", "") or ""}
        except Exception as error:
            print(f"获取Token时发生错误: {error}")
            return {"error": str(error)}

    def save_token(self, token):
        if not isinstance(token, str):
            raise TypeError("token must be a str")
        if len(token) > self._TOKEN_MAX_CHARS:
            return {"error": "Token长度超过限制"}
        try:
            self._save_user_config({"token": token})
            self.config["token"] = token
            self._update_managers_config()
            return {"status": "success", "message": "Token已保存"}
        except Exception as error:
            return {"error": str(error)}

    def clear_token(self):
        try:
            self._save_user_config({"token": ""})
            self.config["token"] = ""
            self._update_managers_config()
            return {"status": "success", "message": "Token已清除"}
        except Exception as error:
            return {"error": str(error)}

    def get_local_version(self):
        try:
            config_path = Path(self.base_dir) / "config" / "config.yaml"
            if config_path.is_file():
                config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            else:
                config = {}
            version = str(config.get("version", "v000")).strip() or "v000"
            return {"status": "success", "version": version}
        except Exception as error:
            return {"error": f"获取本地版本号失败: {error}"}

    def get_oem_config(self):
        try:
            path = self._find_asset("assets/web/oem_config.json")
            if not path.is_file():
                return {"status": "success", "config": {}}
            config = json.loads(_bounded_read_bytes(path, 1024 * 1024, "贴牌配置").decode("utf-8"))
            if not isinstance(config, dict):
                config = {}
            return {"status": "success", "config": config}
        except Exception as error:
            return {"status": "error", "message": f"读取贴牌配置失败: {error}", "config": {}}

    def get_background_image(self):
        import base64
        try:
            path = self._find_asset("assets/web/bg.png")
            if not path.is_file():
                return {"error": "背景图片不存在"}
            encoded_string = base64.b64encode(
                _bounded_read_bytes(path, 16 * 1024 * 1024, "背景图片")
            ).decode("utf-8")
            return {"status": "success", "image_data": "data:image/png;base64," + encoded_string}
        except Exception as error:
            return {"error": f"获取背景图片失败: {error}"}

    def get_local_resources(self):
        try:
            models, voices = self._clone_manager.get_local_models()
            return {"models": models, "voices": voices, "status": "success"}
        except Exception as error:
            return {"error": str(error)}

    def delete_model(self, model_name):
        if not isinstance(model_name, str):
            raise TypeError("model_name must be a str")
        try:
            self._clone_manager.delete_model(model_name)
            return {"status": "success"}
        except Exception as error:
            return {"error": f"删除模型失败: {error}"}

    def delete_voice(self, voice_name):
        if not isinstance(voice_name, str):
            raise TypeError("voice_name must be a str")
        try:
            self._clone_manager.delete_voice(voice_name)
            return {"status": "success"}
        except Exception as error:
            return {"error": f"删除音色失败: {error}"}

    def get_audio_file_count(self, folder_path):
        try:
            base = Path(folder_path).expanduser().resolve()
            if not base.is_dir(): raise NotADirectoryError(base)
            extensions = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
            files = [str(path) for path in base.rglob("*") if path.is_file() and path.suffix.lower() in extensions]
            return {"status": "success", "count": len(files), "files": files}
        except Exception as error: return {"status": "error", "message": str(error), "count": 0}

    def open_file_dialog(self, allow_dir=False):
        try:
            import webview
            dialog_type = webview.FOLDER_DIALOG if allow_dir else webview.OPEN_DIALOG
            files = webview.windows[0].create_file_dialog(dialog_type)
            if not files:
                return {"status": "cancelled", "files": []}
            return {"status": "success", "files": files}
        except Exception as error:
            print(f"打开文件对话框失败: {error}")
            return {"error": str(error)}

    def open_directory(self, path):
        if not isinstance(path, str):
            raise TypeError("path must be a str")
        try:
            if not os.path.exists(path):
                return {"error": "目录不存在"}
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return {"status": "success"}
        except Exception as error:
            return {"error": str(error)}

    def clear_cache(self):
        running_error = self._running_live_error()
        if running_error:
            return {**running_error, 'removed': 0, 'removed_bytes': 0, 'failures': []}
        try:
            from .cache_cleanup import clear_known_caches
            return clear_known_caches()
        except Exception as error:
            return {"status": "error", "message": str(error), "removed": 0,
                    'removed_bytes': 0, 'failures': []}

    def _get_gpu_info(self):
        import re
        result = {"cuda_available": False, "device_name": None, "total_vram_gb": 0,
                  "is_50_series": False, "error": None}
        try:
            import torch
            if torch.cuda.is_available():
                result["cuda_available"] = True; result["device_name"] = torch.cuda.get_device_name(0)
                try: _, total = torch.cuda.mem_get_info(torch.device("cuda:0"))
                except Exception:
                    props = torch.cuda.get_device_properties(0); total = props.total_memory
                result["total_vram_gb"] = round(total / 1024 ** 3, 2)
                result["is_50_series"] = bool(re.search(r"(?:RTX\s*)?50\d{2}", result["device_name"], re.I))
            else: result["error"] = "CUDA not available."
        except Exception as error: result["error"] = str(error)
        return result

    def get_gpu_info(self):
        value = getattr(self, "gpu_info", None) or self._get_gpu_info()
        return {"status": "success", **value}

    def get_available_cameras(self):
        try:
            import cv2
            items = []
            backend = cv2.CAP_DSHOW if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
            for index in range(10):
                capture = cv2.VideoCapture(index, backend)
                try:
                    if capture.isOpened():
                        ok, _ = capture.read()
                        if ok: items.append({"index": index, "name": f"摄像头 {index + 1}"})
                finally: capture.release()
            return {"status": "success", "cameras": items}
        except Exception as error: return {"status": "error", "message": str(error), "cameras": []}

    def probe_camera_availability(self, camera_index, resolution=None):
        try:
            import cv2
            capture = cv2.VideoCapture(int(camera_index), cv2.CAP_DSHOW if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY)
            try:
                if resolution:
                    width, height = map(int, str(resolution).lower().split("x", 1))
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width); capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                if not capture.isOpened(): raise RuntimeError("摄像头无法打开")
                ok, frame = capture.read()
                if not ok or frame is None: raise RuntimeError("摄像头无法读取画面")
                height, width = frame.shape[:2]
                return {"status": "success", "available": True, "width": width, "height": height}
            finally: capture.release()
        except Exception as error: return {"status": "error", "available": False, "message": str(error)}

    def detect_camera_resolutions(self, camera_index):
        common = ("1920x1080", "1080x1920", "1280x720", "720x1280", "640x480")
        supported = []
        for resolution in common:
            result = self.probe_camera_availability(camera_index, resolution)
            if result.get("available"):
                actual = f"{result['width']}x{result['height']}"
                if actual == resolution and actual not in supported: supported.append(actual)
        return {"status": "success", "resolutions": supported,
                "recommended": next((x for x in common if x in supported), supported[0] if supported else None)}

    @staticmethod
    def _probe_video_properties(video_path):
        import json
        ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
        if not ffprobe: raise RuntimeError("未找到 ffprobe")
        result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0",
                                 "-show_entries", "stream=width,height,avg_frame_rate", "-of", "json", str(video_path)],
                                capture_output=True, text=True)
        if result.returncode: raise RuntimeError(result.stderr.strip() or "ffprobe 读取视频失败")
        streams = json.loads(result.stdout).get("streams") or []
        if not streams: raise ValueError("视频文件没有视频轨道")
        stream = streams[0]; numerator, denominator = str(stream.get("avg_frame_rate") or "0/1").split("/", 1)
        return int(stream["width"]), int(stream["height"]), float(numerator) / float(denominator or 1)

    @staticmethod
    def _is_required_video_fps(fps):
        return is_required_video_fps(fps)

    @staticmethod
    def _format_video_fps_error(video_file, fps):
        return f"视频帧率必须为 25 FPS，当前文件 {video_file} ({float(fps):g} FPS)"

    @staticmethod
    def _iter_video_drive_files(path):
        from .digital_live_params import iter_video_drive_files
        return iter_video_drive_files(path)

    def _validate_video_drive_assets(self, path):
        for video in self._iter_video_drive_files(path):
            width, height, fps = self._probe_video_properties(video)
            if max(width, height) > 1920 or min(width, height) > 1080:
                raise ValueError(f"视频驱动素材分辨率必须为 1080P 及以下，当前文件 {video} ({width}×{height})")
            if not self._is_required_video_fps(fps): raise ValueError(self._format_video_fps_error(video, fps))

    def validate_video_drive_path(self, path):
        try:
            files = self._iter_video_drive_files(path); self._validate_video_drive_assets(path)
            return {"status": "success", "valid": True, "files": files}
        except Exception as error: return {"status": "error", "valid": False, "message": str(error)}

    def validate_local_video_file(self, path):
        try:
            file = Path(path)
            if not file.is_file(): raise FileNotFoundError(file)
            width, height, fps = self._probe_video_properties(str(file))
            if not self._is_required_video_fps(fps): raise ValueError(self._format_video_fps_error(str(file), fps))
            return {"status": "success", "valid": True, "width": width, "height": height, "fps": fps}
        except Exception as error: return {"status": "error", "valid": False, "message": str(error)}

    @staticmethod
    def _subprocess_startupinfo():
        if sys.platform != "win32": return None
        startup = subprocess.STARTUPINFO(); startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startup

    @staticmethod
    def _run_subprocess(command, cwd=None):
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              startupinfo=Api._subprocess_startupinfo(),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @staticmethod
    def _read_yaml_file(file_path):
        import yaml
        path = Path(file_path)
        if not path.is_file(): return {}
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _write_yaml_file(file_path, data):
        import yaml
        path = Path(file_path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    @staticmethod
    def _read_text_file(file_path):
        path = Path(file_path)
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try: return path.read_text(encoding=encoding)
            except UnicodeDecodeError: pass
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _format_seconds(seconds):
        value = max(0, int(round(float(seconds)))); minutes, seconds = divmod(value, 60); hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _resolve_ffprobe_executable():
        ffprobe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
        if not ffprobe: raise FileNotFoundError("未找到 ffprobe，请检查 FFMPEG_HOME 或 PATH")
        return ffprobe

    @classmethod
    def _resolve_asr_lang(cls, asr_lang):
        value = str(asr_lang or "auto").strip().lower().replace("_", "-")
        return {"zh-cn": "zh", "zh": "zh", "chinese": "zh", "en-us": "en", "english": "en",
                "ms-my": "ms", "malay": "ms", "vi-vn": "vi", "vietnamese": "vi"}.get(value, value)

    @classmethod
    def _validate_voice_clone_audio(cls, audio_path, min_seconds, max_seconds, label):
        duration = cls._get_audio_duration(audio_path)
        if not float(min_seconds) <= duration <= float(max_seconds):
            raise ValueError(f"{label}：参考音频时长须为 {min_seconds}–{max_seconds} 秒，当前 {duration:.1f} 秒")
        return duration

    @staticmethod
    def _count_script_audio_files(script_audio_dir):
        folder=Path(script_audio_dir)
        return sum(path.is_file() and path.suffix.lower() in {".wav",".mp3",".m4a",".aac",".flac",".ogg"} for path in folder.iterdir()) if folder.is_dir() else 0

    def _build_params(self, live_data):
        return build_local_params(live_data or {})

    def _normalize_lip_sync_record_data(self, live_data):
        value = dict(live_data or {}); nested = value.get("lip_sync_record")
        if isinstance(nested, dict): value.update(nested)
        aliases = {"model_id": "imageModelId", "voice_id": "voiceModelId", "audio_path": "audioPath",
                   "video_path": "videoPath", "output_path": "outputPath"}
        for target, source in aliases.items():
            if not value.get(target) and value.get(source): value[target] = value[source]
        return value

    def _update_managers_config(self):
        for manager in (getattr(self, "_digital_live_manager", None), getattr(self, "_record_live_manager", None),
                        getattr(self, "_face_hand_live_manager", None)):
            if manager is not None: manager.config = self.config

    @staticmethod
    def _get_browser_preview_path(video_path):
        path = Path(video_path); return str(path.with_name(path.stem + "_web_preview.mp4"))

    def _resolve_browser_preview_path(self, video_path, preview_path=None):
        candidate = Path(preview_path or self._get_browser_preview_path(video_path))
        return str(candidate if candidate.is_file() else Path(video_path))

    def _ensure_browser_preview_video(self, video_path, preview_path=""):
        source = Path(video_path)
        if not source.is_file(): raise FileNotFoundError(source)
        output = Path(preview_path or self._get_browser_preview_path(str(source)))
        if output.is_file() and output.stat().st_mtime_ns >= source.stat().st_mtime_ns: return str(output)
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        result = self._run_subprocess([ffmpeg, "-y", "-i", str(source), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                       "-c:a", "aac", "-movflags", "+faststart", str(output)])
        if result.returncode: raise RuntimeError(result.stderr[-1000:])
        return str(output)

    def _encode_media_data(self, file_path):
        import base64, mimetypes
        if not file_path or not os.path.exists(file_path):
            return ""
        try:
            if os.path.getsize(file_path) > self._INLINE_MEDIA_MAX_BYTES:
                return ""
            mime_type, _ = mimetypes.guess_type(file_path)
            mime_type = mime_type or "application/octet-stream"
            with open(file_path, "rb") as source:
                encoded = base64.b64encode(source.read()).decode("ascii")
            return f"data:{mime_type};base64,{encoded}"
        except Exception:
            return ""

    def launch_audio_editor(self):
        try:
            process = getattr(self, "_audio_editor_process", None)
            if process and process.poll() is None: return {"status": "success", "message": "音频编辑器已在运行", "pid": process.pid}
            self._audio_editor_process = subprocess.Popen([sys.executable, "-m", "recovered.edit_audio"], cwd=str(Path(__file__).resolve().parent.parent))
            return {"status": "success", "pid": self._audio_editor_process.pid}
        except Exception as error: return {"status": "error", "message": f"启动音频编辑器失败: {error}"}

    def launch_live_action_assistant(self):
        try:
            process = getattr(self, "_live_action_assistant_process", None)
            if process and process.poll() is None: return {"status": "success", "message": "场控助手已在运行", "pid": process.pid}
            self._live_action_assistant_process = subprocess.Popen([sys.executable, "-m", "recovered.auto_live_action"], cwd=str(Path(__file__).resolve().parent.parent))
            return {"status": "success", "pid": self._live_action_assistant_process.pid}
        except Exception as error: return {"status": "error", "message": f"启动场控助手失败: {error}"}

    def stop_live_action_assistant(self):
        process, self._live_action_assistant_process = getattr(self, "_live_action_assistant_process", None), None
        if not process or process.poll() is not None: return {"status": "success", "message": "场控助手未运行"}
        try:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
            return {"status": "success", "message": "场控助手已停止"}
        except Exception as error: return {"status": "error", "message": str(error)}

    @staticmethod
    def _stop_owned_process(process):
        if not process or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    def shutdown(self):
        """Release all resources owned by the desktop application instance."""
        with self._live_lifecycle_lock:
            if self._shutdown_complete:
                return {"status": "success", "already_stopped": True, "errors": []}
            errors = []
            for attribute in ("_face_hand_live_manager", "_record_live_manager", "_digital_live_manager"):
                manager = getattr(self, attribute, None)
                if manager is None:
                    continue
                try:
                    if getattr(manager, "is_broadcasting", False):
                        manager.stop_live()
                except Exception as error:
                    errors.append(f"{attribute}: {error}")
            for attribute in ("_live_action_assistant_process", "_audio_editor_process"):
                process = getattr(self, attribute, None)
                setattr(self, attribute, None)
                try:
                    self._stop_owned_process(process)
                except Exception as error:
                    errors.append(f"{attribute}: {error}")
            process, self.srs_process = getattr(self, "srs_process", None), None
            try:
                _shutdown_srs(process)
            except Exception as error:
                errors.append(f"srs_process: {error}")
            self._shutdown_complete = True
            return {"status": "partial" if errors else "success", "errors": errors}

    def _oba_state_path(self):
        return Path(self._resolve_user_config_path()).with_name("oba_live_installed_path.txt")

    def _save_oba_live_installed_path(self, exe_path):
        path = self._oba_state_path(); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(str(exe_path), encoding="utf-8")

    def _find_oba_live_installed_exe(self):
        approved_roots = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/oba-live-tool",
                          Path(os.environ.get("PROGRAMFILES", "")) / "oba-live-tool",
                          Path(self.runtime_dir) / "oba-live-tool"]
        candidates = []
        try:
            candidates.append(Path(self._oba_state_path().read_text(encoding="utf-8").strip()))
        except OSError:
            pass
        candidates += [root / "oba-live-tool.exe" for root in approved_roots]
        for path in candidates:
            try:
                resolved = path.expanduser().resolve()
                if resolved.is_file() and any(resolved.is_relative_to(root.expanduser().resolve()) for root in approved_roots):
                    return str(resolved)
            except (OSError, ValueError):
                continue
        return ""

    def _ensure_oba_live_installer(self):
        import requests
        from .update_integrity import _require_trusted_url, file_sha256

        target = Path(self.runtime_dir) / "oba-live-tool-setup.exe"
        expected = str(self.config.get("oba_live_installer_sha256") or "").strip().lower()
        if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
            raise ValueError("未配置有效的 OBA 安装包 SHA-256")
        if target.is_file() and target.stat().st_size and file_sha256(target) == expected:
            return str(target)
        url = str(self.config.get("oba_live_installer_url") or "").strip()
        if not url:
            raise ValueError("未配置 OBA 场控助手安装地址")
        _require_trusted_url(url, "OBA 安装包地址")
        temporary = target.with_suffix(target.suffix + ".download")
        temporary.unlink(missing_ok=True)
        try:
            with requests.get(url, stream=True, timeout=60) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            output.write(chunk)
            if not temporary.stat().st_size or file_sha256(temporary) != expected:
                raise ValueError("OBA 安装包 SHA-256 校验失败")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return str(target)

    def launch_oba_live_tool(self):
        try:
            executable = self._find_oba_live_installed_exe()
            if not executable:
                if sys.platform != "win32": raise OSError("OBA 场控助手仅支持 Windows")
                installer = self._ensure_oba_live_installer(); subprocess.run([installer], check=True)
                executable = self._find_oba_live_installed_exe()
                if not executable: return {"status": "error", "need_install": True, "message": "安装完成后请重新点击启动"}
            process = subprocess.Popen([executable]); self._save_oba_live_installed_path(executable)
            return {"status": "success", "pid": process.pid, "exe_path": executable}
        except Exception as error: return {"status": "error", "message": f"启动 OBA 场控助手失败: {error}"}

    def get_update_status(self):
        from .update_integrity import get_update_status
        try: return {"status": "success", **get_update_status(self.runtime_dir)}
        except Exception as error: return {"status": "error", "message": str(error)}

    def _shutdown_after_update_launch(self):
        self.shutdown()

    def start_app_update(self):
        try:
            process = subprocess.Popen([sys.executable, "-m", "recovered.update_integrity", "--auto-start"],
                                       cwd=str(Path(__file__).resolve().parent.parent))
            self._shutdown_after_update_launch()
            return {"status": "success", "pid": process.pid}
        except Exception as error: return {"status": "error", "message": f"启动更新程序失败: {error}"}

    def _preflight_camera_if_needed(self, local_params):
        if (local_params or {}).get("input_mode") != "camera": return
        result = self.probe_camera_availability(local_params.get("camera_index", -1),
                                                local_params.get("camera_resolution"))
        if not result.get("available"): raise RuntimeError(result.get("message") or "摄像头不可用")

    def process_face_hand_video_group(self, face_video_path, hand_video_path=""):
        from .face_hand_video_processor import process_face_hand_video_group
        try:
            output_root = Path(self.runtime_dir) / "assets/characters/face_hand_groups"
            result = process_face_hand_video_group(face_video_path, hand_video_path, output_root)
            return {"status": "success", **result}
        except Exception as error: return {"status": "error", "message": f"处理人脸人手视频失败: {error}"}

    def start_clone_local(self, video_path, model_name, model_id, resolution="720p", enable_kt_board=False):
        try:
            source = Path(video_path)
            if not source.is_file(): raise FileNotFoundError(source)
            if str(resolution).lower() not in {"480p", "720p", "1080p", "2k", "4k"}: raise ValueError("不支持的清晰度档位")
            base = Path(self.config.get("image_base_dir") or Path(self.runtime_dir) / "assets/characters/images")
            try: from bin.image_clone.infer_api import clone_video_local
            except ImportError: raise RuntimeError("本地形象克隆运行时尚未加载，请确认 image_clone 模块可用")
            generated_id = str(clone_video_local(str(source), str(base), str(model_name or model_id), str(resolution)))
            actual_id = generated_id or str(model_id)
            directory = base / actual_id; info_path = directory / "video_info.yaml"
            info = self._read_yaml_file(info_path); info.update({"model_id": actual_id, "model_name": model_name,
                                                                 "resolution": resolution, "enable_kt_board": bool(enable_kt_board)})
            self._write_yaml_file(info_path, info)
            return {"status": "success", "model_id": actual_id, "model_name": model_name,
                    "model_dir": str(directory), "enable_kt_board": bool(enable_kt_board)}
        except Exception as error: return {"status": "error", "message": f"本地形象克隆失败: {error}"}

    def export_kt_board_template(self):
        from shutil import copyfile

        from .product_kt_overlay import _ensure_std_kt_board_image

        try:
            import webview

            target = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG, save_filename="std_kt_board.png"
            )
            if not target:
                return {"status": "cancelled"}
            if isinstance(target, (tuple, list)):
                target = target[0]
            source = _ensure_std_kt_board_image(self.runtime_dir)
            if Path(source).resolve() != Path(target).resolve():
                copyfile(source, target)
            return {"status": "success", "path": str(target)}
        except Exception as error:
            return {"status": "error", "message": str(error)}

    def get_audio_input_devices(self):
        try:
            from .audio_devices import get_audio_devices

            devices = [
                {"index": device.get("index"), "name": device.get("name")}
                for device in get_audio_devices().get("input", [])
            ]
        except Exception as error:
            return {"status": "error", "message": str(error)}
        return {"status": "success", "devices": devices}

    def get_taobao_account(self):
        from .taobao_live_control import _get_taobao_account_status

        return _get_taobao_account_status(
            self.runtime_dir, self.config.get("taobao_storage_state")
        )

    def login_taobao_account(self, force_relogin=False):
        from .taobao_live_control import TaobaoLiveControl

        controller = TaobaoLiveControl._create(runtime_dir=self.runtime_dir)
        configured_state = self.config.get("taobao_storage_state")
        storage_path = configured_state if isinstance(configured_state, (str, Path)) else None
        try:
            controller.login(storage_path=storage_path, force_relogin=force_relogin)
            if isinstance(configured_state, dict):
                self.config.pop("taobao_storage_state", None)
            return {"status": "success"}
        except Exception as error:
            return {"status": "error", "message": str(error)}
        finally:
            controller.shutdown()

    def probe_taobao_live_status(self):
        from .taobao_live_control import _probe_taobao_live_status

        return _probe_taobao_live_status(
            runtime_dir=self.runtime_dir,
            storage_state=self.config.get("taobao_storage_state"),
        )

    def sync_taobao_products(self, source="commodity"):
        from .taobao_live_control import (TaobaoLoginRequired, _fetch_taobao_commodity_products,
                                          _fetch_taobao_live_plan_products)

        fetcher={"commodity":_fetch_taobao_commodity_products,"plan":_fetch_taobao_live_plan_products}.get(str(source))
        if fetcher is None:
            return {"status":"error","message":f"不支持的淘宝商品来源: {source}"}
        try:
            products = fetcher(
                runtime_dir=self.runtime_dir,
                storage_state=self.config.get("taobao_storage_state"),
            )
        except TaobaoLoginRequired as error:
            return {"status": "error", "message": str(error)}
        except Exception as error:
            return {"status": "error", "message": f"淘宝商品同步失败: {error}"}
        return {"status": "success", "products": products}

    def start_live(self, data):
        with self._live_lifecycle_lock:
            return self._start_live_locked(data)

    def stop_live(self):
        with self._live_lifecycle_lock:
            return self._stop_live_locked()

    def _stop_live_locked(self):
        errors = []
        for attribute, message in (
            ("_face_hand_live_manager", "人脸人手直播停止失败"),
            ("_record_live_manager", "本地转播/录播运行时停止失败"),
            ("_digital_live_manager", "本地智播停止失败"),
        ):
            manager = getattr(self, attribute, None)
            if manager is None or not manager.is_broadcasting:
                continue
            try:
                stopped = manager.stop_live()
                if stopped is None and not manager.is_broadcasting:
                    stopped = True
            except Exception as error:
                stopped = False
                errors.append(str(error) or message)
            if not stopped and not errors:
                errors.append(getattr(manager, "last_error", None) or message)
            elif not stopped and errors:
                current = getattr(manager, "last_error", None) or message
                if current not in errors:
                    errors.append(current)
        if errors:
            return {"status": "error", "message": errors[0]}
        return {"status": "success"}

    def _start_live_locked(self, data):
        if not isinstance(data, dict):
            return {"status": "error", "message": "启动参数格式错误"}
        live_data = data.get("config")
        if not live_data:
            return {"status": "error", "message": "直播配置为空"}
        live_type = live_data.get("live_type") or "digital_human"
        if live_type == "local_media":
            return self._start_local_media_live(live_data)
        if live_type == "face_hand_live":
            return self._start_face_hand_live(data, live_data)
        return self._start_digital_live(live_data)

    def speak(self, text):
        manager = self._digital_live_manager
        if not manager.is_broadcasting:
            return {"status": "error", "message": "请先开启直播"}
        if not isinstance(text, str) or not text.strip():
            return {"status": "error", "message": "请输入播报内容"}
        with self._live_lifecycle_lock:
            if manager.request_manual_speak(text):
                return {"status": "success"}
        return {"status": "error", "message": manager.last_error or "播报失败"}

    def start_danmu_capture(self, live_url, platform_type="douyin"):
        with self._live_lifecycle_lock:
            manager = self._digital_live_manager
            if not manager.is_broadcasting:
                return {"status": "error", "message": "请先开启直播"}
            if manager.start_danmu(live_url, platform_type):
                return {"status": "success"}
            return {"status": "error", "message": manager.last_error or "弹幕采集启动失败"}

    def stop_danmu_capture(self):
        with self._live_lifecycle_lock:
            manager = self._digital_live_manager
            if manager.stop_danmu():
                return {"status": "success"}
            return {"status": "error", "message": manager.last_error or "弹幕采集停止失败"}

    def simulate_question(self, text):
        with self._live_lifecycle_lock:
            manager = self._digital_live_manager
            if not manager.is_broadcasting:
                return {"status": "error", "message": "请先开启直播"}
            if not isinstance(text, str) or not manager.request_simulated_question(text):
                return {"status": "error", "message": "请输入有效的问题"}
        return {"status": "success"}

    def _start_digital_live(self, live_data):
        running_error = self._running_live_error()
        if running_error:
            return running_error
        voice_infer_version = live_data.get("voice_infer_version")
        minimax_voice_config = live_data.get("minimax_voice_config") or {}
        cosyvoice_voice_config = live_data.get("cosyvoice_voice_config") or {}
        if voice_infer_version == "minimax":
            api_key = str(minimax_voice_config.get("api_key") or "").strip()
            api_host = str(minimax_voice_config.get("api_host") or "").strip().lower()
            group_id = str(minimax_voice_config.get("group_id") or "").strip()
            if not api_key or ("minimax.io" in api_host and not group_id):
                return {
                    "status": "error",
                    "message": "Minimax 声音配置不完整，请先在配置页填写后再开播",
                }
        elif voice_infer_version == "cosyvoice":
            api_key = str(cosyvoice_voice_config.get("api_key") or "").strip()
            if not api_key:
                return {
                    "status": "error",
                    "message": "阿里云语音合成配置不完整，请先在配置页填写 API Key 后再开播",
                }
        if (
            voice_infer_version in {"v2", "malai_local", "vietnam_local"}
            and live_data.get("script_input_mode") == "text"
            and not live_data.get("origin_idle_video_mode")
        ):
            if not self._digital_live_manager.prepare_multilingual_audio_cache(
                scripts=live_data.get("scripts"),
                voice_id=live_data.get("voice_id"),
                assistant_voice_id=live_data.get("assistant_voice_id"),
                shift_schedule=live_data.get("shift_schedule"),
                multi_product_configs=live_data.get("multi_product_configs"),
                language=live_data.get("language", "zh-CN"),
                voice_speed=live_data.get("voice_speed", 1.1),
                voice_infer_version=voice_infer_version,
            ):
                return {"status": "error", "message": "多语种话术音频缓存准备失败"}
        try:
            local_params = build_local_params(live_data)
            manager = getattr(self, "_digital_live_manager", None)
            if manager is None:
                return {"status": "error", "message": "数字人直播运行时未初始化"}
            if manager.start_live(
                local_params=local_params,
                config=live_data.copy(),
                llm_config=live_data.get("llm_config"),
                minimax_voice_config=live_data.get("minimax_voice_config"),
                cosyvoice_voice_config=live_data.get("cosyvoice_voice_config"),
            ):
                return {
                    "status": "success",
                    "session_id": manager.current_session_id,
                    "danmu_capturing": bool(manager.is_capturing),
                }
            message = getattr(manager, "last_error", None) or "本地智播启动失败"
        except Exception as error:
            message = str(error)
        return {"status": "error", "message": message}

    def _running_live_error(self):
        for attribute, message in (
            ("_digital_live_manager", "已有数字人直播会话正在进行，请先停止"),
            ("_record_live_manager", "已有转播/录播直播正在进行，请先停止"),
            ("_face_hand_live_manager", "已有人脸人手直播正在进行，请先停止"),
        ):
            manager = getattr(self, attribute, None)
            if manager is not None and manager.is_broadcasting:
                return {"status": "error", "message": message}
        return None

    def _validate_local_video_fps(self, video_path):
        try:
            with _open_media_source(video_path) as container:
                fps = float(container.streams.video[0].average_rate)
        except Exception as error:
            return f"无法识别视频帧率: {error}"
        if not is_required_video_fps(fps):
            return f"视频帧率必须为 25 FPS，当前文件 {fps:g} FPS。请先用剪辑软件转码为 25 FPS 后再使用。"
        return None

    def _start_local_media_live(self, live_data):
        running_error = self._running_live_error()
        if running_error:
            return running_error
        manager = self._record_live_manager
        source_type = (live_data.get("video_source_type") or "local").strip()
        video_path = (live_data.get("main_video_path") or "").strip()
        douyin_url = (live_data.get("douyin_live_url") or "").strip()
        if source_type == "local":
            if not video_path:
                return {"status": "error", "message": "请先选择本地视频文件"}
            if not Path(video_path).exists():
                return {"status": "error", "message": "本地视频文件不存在"}
            error = self._validate_local_video_fps(video_path)
            if error:
                return {"status": "error", "message": error}
        elif source_type == "douyin":
            if not douyin_url:
                return {"status": "error", "message": "请先填写抖音直播间链接"}
        else:
            return {"status": "error", "message": f"不支持的视频源类型: {source_type}"}
        width, height = resolve_portrait_size(live_data.get("resolution"))
        if manager.start_live(
            video_path=video_path, video_source_type=source_type, douyin_live_url=douyin_url,
            width=width, height=height, output_mode=(live_data.get("output_mode") or "window").strip(),
            deduplication_config=live_data.get("deduplication_config"),
        ):
            return {"status": "success"}
        return {"status": "error", "message": manager.last_error or "本地转播/录播运行时启动失败"}

    def _start_face_hand_live(self, data, live_data):
        config = live_data
        manager = getattr(self, "_face_hand_live_manager", None)
        if manager is None:
            return {"status": "error", "message": "人脸人手直播运行时未初始化"}
        running_error = self._running_live_error()
        if running_error:
            return running_error
        if (config.get("live_platform") or "").strip().lower() != "taobao":
            return {"status": "error", "message": "人脸人手直播仅支持淘宝平台"}
        group_dir = (config.get("face_hand_video_group_dir") or "").strip()
        valid, message, _ = validate_face_hand_video_group(group_dir)
        if not valid:
            return {"status": "error", "message": message or "人脸人手视频组无效"}
        voice_ids = config.get("voice_ids") or []
        if not any(str(voice or "").strip() for voice in voice_ids) and not (
            config.get("voice_id") or ""
        ).strip():
            return {"status": "error", "message": "请先选择声音"}
        products = config.get("products") or config.get("product_scripts") or []
        product_groups = FaceHandLiveManager._build_product_groups(products)
        if not product_groups:
            return {"status": "error", "message": "请先配置商品话术"}
        runtime_config = dict(config, live_type="face_hand_live", room_template_type="face_hand_live")
        # The face/hand runtime disables product KT following in both config spellings.
        runtime_config["enableProductKtFollow"] = False
        runtime_config["enable_product_kt_follow"] = False
        qa_info = []
        for product in products:
            if not isinstance(product, dict):
                continue
            content = str(product.get("content") or "").strip()
            if content:
                qa_info.append(content)
        runtime_config["product_info"] = "\n\n".join(
            FaceHandLiveManager._format_product_info(product) for product in product_groups
        )
        runtime_config["qa_info"] = "\n\n".join(qa_info)
        voice_config = config.get("voice_general_config") or {}
        provider = (voice_config.get("provider") or "").strip().lower()
        cosyvoice_config = config.get("cosyvoice_voice_config")
        if provider == "minimax":
            return {"status": "error", "message": "人脸人手直播不支持 Minimax 云端声音"}
        if provider == "cosyvoice" and not ((cosyvoice_config or {}).get("api_key") or "").strip():
            return {
                "status": "error",
                "message": "阿里云语音合成配置不完整，请先在配置页填写 API Key 后再开播",
            }
        version = (config.get("voice_infer_version") or "v1").strip()
        if version not in {"v1", "v2", "v3", "malai_local", "vietnam_local"}:
            version = "v1"
        runtime_config["voice_infer_version"] = version
        if manager.start_live(
            config=runtime_config,
            llm_config=config.get("llm_config"),
            cosyvoice_voice_config=cosyvoice_config,
        ):
            return {"status": "success"}
        return {"status": "error", "message": getattr(manager, "last_error", None) or "人脸人手直播启动失败"}

    def validate_video_drive_path(self, path):
        try:
            files = self._iter_video_drive_files(path)
            self._validate_video_drive_assets(path)
        except Exception as error:
            return {"status": "error", "valid": False, "message": str(error)}
        return {"status": "success", "valid": True, "files": files}

    def validate_face_hand_video_group_dir(self, group_dir):
        try:
            valid, message, summary = validate_face_hand_video_group(group_dir)
        except (TypeError, ValueError, OSError) as error:
            return {"status": "error", "message": str(error)}
        if not valid:
            return {"status": "error", "message": message or "视频组无效"}
        return {
            "status": "success",
            "group_dir": summary.get("group_dir", str(Path(group_dir).resolve())),
            "face_count": summary.get("face_count", 0),
            "hand_count": summary.get("hand_count", 0),
        }

    def _voice_clone_duration_limits(self, clone_mode):
        return {"cosyvoice": (5, 60), "minimax": (40, 60)}.get(
            (clone_mode or "").strip().lower(), (1, 16)
        )

    @classmethod
    def _get_audio_duration(cls, audio_path):
        return get_audio_duration(str(audio_path))

    def process_audio_clip(self, file_path, min_seconds=8, max_seconds=15):
        from .audio_clip import process_and_split_audio
        from uuid import uuid4

        output_dir = Path(self.runtime_dir) / "utils" / "audio_clip" / "temp" / uuid4().hex
        asr_weight_path = Path(self._get_asr_weight_path())
        try:
            files = process_and_split_audio(
                file_path, output_dir, asr_weight_path,
                min_seconds=min_seconds, max_seconds=max_seconds,
            )
        except Exception as error:
            shutil.rmtree(output_dir, ignore_errors=True)
            return {"status": "error", "message": str(error)}
        manifest_path = output_dir / "manifest.json"
        return {"status": "success", "files": files, "output_dir": str(output_dir),
                "manifest_path": str(manifest_path) if manifest_path.is_file() else ""}

    def _get_asr_weight_path(self):
        candidates = (
            Path(self.runtime_dir) / "assets" / "pretrained_models" / "asr",
            Path(self.runtime_dir) / "static_sources" / "pretrained_models" / "asr",
        )
        return str(next((path for path in candidates if path.is_dir()), candidates[0]))

    def recognize_audio_file(self, file_path, asr_weight_path=None):
        from .asr_main import recognize_audio

        try:
            result = recognize_audio(file_path, asr_weight_path or self._get_asr_weight_path())
        except Exception as error:
            return {"status": "error", "message": str(error)}
        return {"status": "success", **result}

    def recognize_lip_sync_sentences(self, video_path, asr_weight_path=None):
        from .funasr_sentences import recognize_media_sentences

        try:
            sentences = recognize_media_sentences(
                video_path, asr_weight_path or self._get_asr_weight_path()
            )
        except Exception as error:
            return {"status": "error", "message": str(error)}
        return {"status": "success", "sentences": sentences}

    def remove_all_forbidden_words(self, text, additional_words=None):
        from .replace_forbidden_words import replace_forbidden_words

        return replace_forbidden_words(text, additional_words)

    @staticmethod
    def _parse_llm_json_object(raw_text):
        import re

        match = re.search(r"\{[\s\S]*\}", str(raw_text or ""))
        if not match:
            raise ValueError("未找到 JSON 对象")
        value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise ValueError("LLM 返回值不是 JSON 对象")
        return value

    def generalize_sentences_api(self, text, variations=3):
        from .generalize_sentences import generalize_sentences

        try:
            return generalize_sentences(text, int(variations))
        except Exception as error:
            return {"status": "error", "message": str(error)}

    def save_llm_config(self, llm_config_data):
        if not isinstance(llm_config_data, dict):
            raise TypeError("llm_config_data must be a dict")
        try:
            self._save_user_config({"llm_config": llm_config_data})
            self.config["llm_config"] = llm_config_data
            self._update_managers_config()
            return {"status": "success", "message": "配置已保存到本地"}
        except Exception as error:
            return {"error": str(error)}

    def test_llm_availability(self, llm_config):
        from .llm_base_chat import base_chat
        if not isinstance(llm_config, dict):
            raise TypeError("llm_config must be a dict")
        vendor = ""
        try:
            vendor = llm_config.get("vendor", "").lower()
            model = llm_config.get("model", "")
            endpoint = llm_config.get("endpoint", "")
            api_key = llm_config.get("api_key", "")
            provider = vendor or "unknown"
            if not vendor or not model or not endpoint or not api_key:
                return {
                    "status": "error",
                    "message": "未检测到可用的大模型配置，请先在设置中配置硅基流动 API Key。",
                    "is_available": False,
                    "is_recommended_provider": False,
                    "provider": provider,
                }
            reply = base_chat(
                question="回复一个字：好",
                sys_prompt="你是一个助手",
                chat_history=[],
                llm_config=llm_config,
            )
            if reply and len(reply.strip()) > 0 and reply.strip() != " ":
                return {
                    "status": "success",
                    "message": "大模型服务正常",
                    "is_available": True,
                    "is_recommended_provider": True,
                    "provider": provider,
                }
            return {
                "status": "error",
                "message": "当前大模型配置不可用，请检查设置中的模型参数，或改为配置硅基流动 API Key。",
                "is_available": False,
                "is_recommended_provider": False,
                "provider": provider,
            }
        except Exception as error:
            return {
                "status": "error",
                "message": f"测试大模型服务时出错: {error}",
                "is_available": False,
                "is_recommended_provider": False,
                "provider": vendor or "unknown",
            }

    def _normalize_volcengine_image_config(self, image_config_data):
        source = image_config_data if isinstance(image_config_data, dict) else {}
        aliases = {"api_key": ("api_key", "ark_api_key"), "model": ("model", "model_id", "image_model_id"),
                   "endpoint": ("endpoint", "api_url"), "provider": ("provider",)}
        result = {}
        for target, keys in aliases.items():
            result[target] = next((str(source.get(key) or "").strip() for key in keys if source.get(key)), "")
        result["provider"] = result["provider"] or "volcengine"
        return result

    def _read_volcengine_image_config(self):
        user = self._load_user_config(); raw = user.get("volcengine_image_config") or self.config.get("volcengine_image_config") or {}
        result = self._normalize_volcengine_image_config(raw)
        result.pop("gpt_image2", None)
        return result

    def _resolve_volcengine_image_config(self, override=None):
        result = self._read_volcengine_image_config()
        if isinstance(override, dict): result.update({k: v for k, v in self._normalize_volcengine_image_config(override).items() if v})
        return result

    def save_volcengine_image_config(self, image_config_data):
        try:
            normalized = self._normalize_volcengine_image_config(image_config_data)
            if not normalized.get("api_key"): raise ValueError("API Key 不能为空")
            self._save_user_config({"volcengine_image_config": normalized}); self.config["volcengine_image_config"] = normalized
            return {"status": "success", "config": normalized}
        except Exception as error: return {"status": "error", "message": str(error)}

    def get_volcengine_image_config(self):
        try: return {"status": "success", "config": self._read_volcengine_image_config()}
        except Exception as error: return {"status": "error", "message": str(error)}

    def generate_script(self, product_info, special_instructions=""):
        from .generate_structured_speech import generate_structured_speech
        if not isinstance(product_info, dict):
            raise TypeError("product_info must be a dict")
        if not isinstance(special_instructions, str):
            raise TypeError("special_instructions must be a str")
        try:
            print(f"开始处理商品列表,共有{len(product_info)}个商品")
            scripts = []
            failed_products = []
            for product_id, product in product_info.items():
                try:
                    if "content" not in product:
                        continue
                    script = generate_structured_speech(product["content"], special_instructions)
                    if script and str(script).strip():
                        scripts.append(script)
                    else:
                        print(f"处理商品 {product_id} 失败，写入空话术后继续")
                        failed_products.append(str(product_id))
                        scripts.append("")
                except Exception as error:
                    print(f"处理商品 {product_id} 时发生错误: {error}")
                    failed_products.append(str(product_id))
                    scripts.append("")
            result = {
                "script": "\n\n".join(scripts).strip(),
                "failed_products": failed_products,
            }
            if failed_products and not any(str(script).strip() for script in scripts):
                result["error"] = "没有成功生成任何话术"
            return result
        except Exception as error:
            print(f"生成脚本时发生错误：{error}")
            return {"script": "", "failed_products": [], "error": f"生成脚本时发生错误：{error}"}

    def translate_text(self, text, target_language):
        from .language_prompts import normalize_language_code
        from .llm_reply import translate_text_llm
        if not isinstance(text, str):
            raise TypeError("text must be a str")
        if not isinstance(target_language, str):
            raise TypeError("target_language must be a str")
        try:
            source = text if text else ""
            language = normalize_language_code(target_language if target_language else "zh-CN")
            return translate_text_llm(source, language, raise_on_failure=True)
        except Exception as error:
            print(f"翻译失败: {error}")
            return {"error": str(error)}

    def get_stream_urls(self):
        environment = self.config.get("environment", "production")
        current = (self.config.get("environments") or {}).get(environment, {})
        server = str(current.get("server_url") or self.config.get("server_url") or "").rstrip("/")
        return {"status": "success", "environment": environment, "server_url": server,
                "local_service": srs_process_status(getattr(self, "srs_process", None)),
                "push_url": self.config.get("push_url") or self.config.get("rtmp_push_url") or "rtmp://127.0.0.1/live/stream",
                "play_url": self.config.get("play_url") or self.config.get("rtmp_play_url") or "http://127.0.0.1:8080/live/stream.flv"}

    def toggle_interruption(self, data=None):
        enabled = bool((data or {}).get("enabled", (data or {}).get("is_interrupt", not self.config.get("is_interrupt", False))))
        self.config["is_interrupt"] = enabled
        for manager in (getattr(self, "_digital_live_manager", None), getattr(self, "_record_live_manager", None),
                        getattr(self, "_face_hand_live_manager", None)):
            if manager is not None:
                if hasattr(manager, "is_interrupt"): manager.is_interrupt = enabled
                if isinstance(getattr(manager, "config", None), dict): manager.config["is_interrupt"] = enabled
        return {"status": "success", "is_interrupt": enabled}

    def _get_short_video_base_dir(self):
        return str(Path(self.runtime_dir) / "short_videos")

    def generate_audio_for_short_video(self, data):
        from .generate_short_video_audio import generate_audio

        config = dict(self.config, project_root=str(self.runtime_dir))
        result = generate_audio(data or {}, config)
        return {"status": "success", **result} if result.get("success") else {
            "status": "error", "message": result.get("error", "音频生成失败")
        }

    def create_short_video(self, data):
        from .generate_lip_sync_video import create_short_video

        config = dict(self.config, project_root=str(self.runtime_dir),
                      video_output_dir=self._get_short_video_base_dir())
        result = create_short_video(data or {}, config)
        return {"status": "success", **result} if result.get("success") else {
            "status": "error", "message": result.get("error", "短视频生成失败")
        }

    def get_all_short_videos(self):
        base_dir = Path(self._get_short_video_base_dir())
        videos = []
        if base_dir.is_dir():
            for directory in sorted(base_dir.iterdir(), key=lambda path: path.stat().st_mtime,
                                    reverse=True):
                video = directory / "video.mp4"
                if directory.is_dir() and video.is_file():
                    info_path = directory / "video_info.yaml"
                    info = {}
                    if info_path.is_file():
                        try: info = yaml.safe_load(info_path.read_text(encoding="utf-8")) or {}
                        except (OSError, yaml.YAMLError): info = {}
                    videos.append({**info, "id": str(info.get("id") or directory.name),
                                   "video_path": str(video), "output_dir": str(directory)})
        return {"status": "success", "videos": videos}

    def delete_short_video(self, video_id):
        base_dir = Path(self._get_short_video_base_dir()).resolve()
        target = (base_dir / str(video_id)).resolve()
        if target.parent != base_dir:
            return {"status": "error", "message": "无效的短视频 ID"}
        if not target.is_dir():
            return {"status": "error", "message": "短视频不存在"}
        shutil.rmtree(target)
        return {"status": "success"}

    def _get_ip_agent_base_dir(self):
        return os.path.join(os.path.dirname(__file__), "assets", "ip_agent_projects")

    def _get_ip_agent_project_dir(self, project_id):
        import re
        identifier = str(project_id or "")
        if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier) is None or identifier in (".", ".."):
            raise ValueError("无效的 IP 项目 ID")
        base = Path(self._get_ip_agent_base_dir()).resolve()
        target = (base / identifier).resolve()
        if target.parent != base:
            raise ValueError("无效的 IP 项目 ID")
        return str(target)

    def _get_ip_agent_publish_audit_dir(self):
        return str((Path(self._get_ip_agent_base_dir()).resolve().parent / "ip_agent_publish_audit").resolve())

    def _archive_ip_agent_publish_audit(self, project_id, info):
        def audit_plan(value):
            plan = dict(value or {})
            plan["thumbnail_present"] = bool(plan.pop("thumbnail_path", ""))
            plan.pop("video_path", None)
            return plan

        attempts = []
        for value in list(info.get("publish_attempts") or [])[-100:]:
            attempt = dict(value or {})
            attempt["plan"] = audit_plan(attempt.get("plan"))
            attempts.append(attempt)
        last_result = info.get("publish_last_result") or {}
        if not attempts and not last_result:
            return ""
        audit_dir = Path(self._get_ip_agent_publish_audit_dir())
        audit_dir.mkdir(parents=True, exist_ok=True)
        archived_at = datetime.now().isoformat(timespec="seconds")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = audit_dir / f"{project_id}-{stamp}.yaml"
        record = {
            "schema_version": 1, "project_id": str(project_id),
            "project_name": str(info.get("name") or ""), "created_at": info.get("create_time", ""),
            "project_updated_at": info.get("update_time", ""), "archived_at": archived_at,
            "publish_last_request_id": info.get("publish_last_request_id", ""),
            "publish_last_plan": audit_plan(info.get("publish_last_plan")),
            "publish_last_result": last_result, "publish_attempts": attempts,
        }
        self._write_yaml_file(str(target), record)
        return str(target)

    def _get_ip_agent_project_info_path(self, project_id):
        return os.path.join(self._get_ip_agent_project_dir(project_id), "project_info.yaml")

    @staticmethod
    def _normalize_publish_tags(tags):
        import re
        values = re.split(r"[,，#\s]+", tags) if isinstance(tags, str) else tags or []
        result = []
        for item in values:
            value = str(item).strip().lstrip("#")[:30]
            if value and value not in result: result.append(value)
        return result[:20]

    @staticmethod
    def _stringify_publish_tags(tags):
        return " ".join("#" + value for value in Api._normalize_publish_tags(tags))

    @staticmethod
    def _encode_preview_image(image_path):
        import base64, mimetypes
        path = Path(image_path)
        if not path.is_file(): return ""
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    def _default_ip_agent_project_info(self, project_id, name):
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_dir = Path(self._get_ip_agent_project_dir(project_id)) / "result"
        audio_path = str(result_dir / "口播音频.wav")
        video_path = str(result_dir / "数字人口播.mp4")
        subtitle_path = str(result_dir / "口播字幕.srt")
        subtitle_video_path = str(result_dir / "字幕成片.mp4")
        final_video_path = str(result_dir / "最终成片.mp4")
        return {
            "id": project_id, "name": name, "create_time": now, "update_time": now,
            "benchmark_url": "", "benchmark_video_path": "", "benchmark_transcript_path": "",
            "original_script": "", "rewrite_prompt": "", "rewritten_script": "",
            "script_analysis": {}, "rewrite_versions": [], "highlight_keywords": [],
            "selected_language": "zh-CN", "selected_voice_id": "", "selected_model_id": "",
            "voice_speed": 1.0, "preview_audio_path": audio_path, "result_video_path": video_path,
            "audio_path": audio_path, "video_path": video_path,
            "subtitle_srt_path": subtitle_path, "subtitle_path": subtitle_path,
            "subtitle_style_preset": DEFAULT_SUBTITLE_STYLE_PRESET,
            "subtitle_highlight_enabled": True, "subtitle_highlight_color": "",
            "subtitle_animation": "fade", "subtitle_font_id": "", "subtitle_font_name": "",
            "subtitle_font_file": "", "subtitled_video_path": subtitle_video_path,
            "subtitle_video_path": subtitle_video_path,
            "result_video_preview_path": "", "subtitled_video_preview_path": "",
            "bgm_enabled": False, "bgm_music_id": "", "bgm_title": "", "bgm_url": "",
            "bgm_local_path": "", "bgm_volume": 0.16, "cover_template": "impact_yellow",
            "cover_title": "", "cover_path": "", "final_video_path": final_video_path,
            "final_video_preview_path": "", "publish_title": "", "publish_tags_text": "",
            "publish_platforms": ["douyin"], "publish_accounts": {}, "publish_last_result": {},
            "one_click_last_result": {},
        }

    def _build_ip_agent_project_summary(self, project_id, info):
        project_dir = self._get_ip_agent_project_dir(project_id)
        cover_path = str(info.get("cover_path") or "").strip()
        if not cover_path or not os.path.exists(cover_path):
            cover_path = os.path.join(project_dir, "result", "sample.jpg")
        create_time = info.get("create_time", "")
        return {
            "id": project_id,
            "name": info.get("name") or f"IP项目-{project_id}",
            "create_time": create_time,
            "update_time": info.get("update_time", create_time),
            "preview_url": self._encode_preview_image(cover_path),
            "path": os.path.abspath(project_dir),
        }

    def _load_ip_agent_project(self, project_id):
        project_dir = self._get_ip_agent_project_dir(project_id)
        if not os.path.isdir(project_dir):
            return None
        info = self._read_yaml_file(self._get_ip_agent_project_info_path(project_id))
        if not info:
            return None
        task = info.get("publish_task") or {}
        active = getattr(self, "_ip_publish_active", set())
        if task.get("status") == "running" and str(project_id) not in active:
            recovered_at = datetime.now().isoformat(timespec="seconds")
            task = {**task, "status": "interrupted", "updated_at": recovered_at,
                    "completed_at": recovered_at,
                    "error": "应用退出时发布结果未知，请先到平台核对后再决定是否重试"}
            history = list(info.get("publish_attempts") or [])
            replaced = False
            for index in range(len(history) - 1, -1, -1):
                if (history[index].get("request_id") == task.get("request_id")
                        and history[index].get("started_at") == task.get("started_at")):
                    history[index] = task
                    replaced = True
                    break
            if not replaced:
                history.append(task)
            info.update({"publish_task": task, "publish_attempts": history[-100:],
                         "status": "publish_interrupted"})
            self._write_yaml_file(self._get_ip_agent_project_info_path(project_id), info)
        info["id"] = project_id
        info["path"] = os.path.abspath(project_dir)
        cover_path = str(info.get("cover_path") or "").strip()
        if not cover_path or not os.path.exists(cover_path):
            cover_path = os.path.join(project_dir, "result", "sample.jpg")
        info["preview_url"] = self._encode_preview_image(cover_path)
        for video_path_key, preview_path_key in (
            ("result_video_path", "result_video_preview_path"),
            ("subtitled_video_path", "subtitled_video_preview_path"),
            ("final_video_path", "final_video_preview_path"),
        ):
            video_path = info.get(video_path_key, "")
            if video_path:
                info[preview_path_key] = self._resolve_browser_preview_path(
                    video_path, info.get(preview_path_key, "")
                )
        return info

    def _save_ip_agent_project(self, project_id, data):
        from datetime import datetime
        project_dir = self._get_ip_agent_project_dir(project_id)
        if not os.path.isdir(project_dir):
            raise FileNotFoundError("IP项目不存在")
        info_path = self._get_ip_agent_project_info_path(project_id)
        existing = self._read_yaml_file(info_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        defaults = self._default_ip_agent_project_info(
            project_id, existing.get("name") or f"IP项目-{project_id}"
        )
        value = {**defaults, **existing, **(data or {})}
        value["id"] = project_id
        value["update_time"] = now
        if not value.get("create_time"):
            value["create_time"] = now
        value.pop("subtitle_debug_json_path", None)
        self._write_yaml_file(info_path, value)
        result = self._load_ip_agent_project(project_id)
        return result if isinstance(result, dict) else None

    def create_ip_agent_project(self, name):
        from uuid import uuid4
        try:
            if not name:
                return {"error": "请输入项目名称"}
            name = name.strip()
            if not name:
                return {"error": "请输入项目名称"}
            project_id = uuid4().hex
            os.makedirs(self._get_ip_agent_project_dir(project_id), exist_ok=True)
            project = self._save_ip_agent_project(
                project_id, self._default_ip_agent_project_info(project_id, name)
            )
            return {"status": "success", "project": project}
        except Exception as error:
            return {"error": f"创建IP项目失败: {error}"}

    def get_all_ip_agent_projects(self):
        try:
            projects = []
            base_dir = self._get_ip_agent_base_dir()
            os.makedirs(base_dir, exist_ok=True)
            for project_id in os.listdir(base_dir):
                project_dir = os.path.join(base_dir, project_id)
                if not os.path.isdir(project_dir):
                    continue
                info = self._load_ip_agent_project(project_id)
                if info:
                    projects.append(self._build_ip_agent_project_summary(project_id, info))
            projects.sort(key=lambda item: item.get("update_time", ""), reverse=True)
            return {"status": "success", "projects": projects}
        except Exception as error:
            return {"error": f"获取IP项目列表失败: {error}"}

    def get_ip_agent_project(self, project_id):
        try:
            project = self._load_ip_agent_project(project_id)
            if not project:
                return {"error": "IP项目不存在"}
            return {"status": "success", "project": project}
        except Exception as error:
            return {"error": f"获取IP项目失败: {error}"}

    def update_ip_agent_project(self, project_id, data):
        try:
            project = self._save_ip_agent_project(project_id, data or {})
            return {"status": "success", "project": project}
        except Exception as error:
            return {"error": f"保存IP项目失败: {error}"}

    def import_ip_agent_final_video(self, project_id, source_path):
        from uuid import uuid4
        from .douyin_benchmark import probe_video, resolve_ffprobe
        from .ip_publish import file_sha256
        pending = None
        try:
            info = self._load_ip_agent_project(project_id)
            if not info:
                raise FileNotFoundError("IP项目不存在")
            source = Path(source_path).expanduser().resolve()
            if not source.is_file() or source.stat().st_size <= 0:
                raise FileNotFoundError("待导入成片不存在")
            project_dir = Path(self._get_ip_agent_project_dir(project_id)).resolve()
            target = Path(info["final_video_path"]).resolve()
            if project_dir not in target.parents:
                raise ValueError("项目成片路径无效")
            target.parent.mkdir(parents=True, exist_ok=True)
            pending = target.with_name(f".{target.name}.{uuid4().hex}.pending")
            shutil.copyfile(source, pending)
            probe_video(str(pending), resolve_ffprobe(self.runtime_dir))
            os.replace(pending, target)
            info.update({"final_video_path": str(target), "final_video_sha256": file_sha256(target),
                         "status": "ready_to_publish"})
            project = self._save_ip_agent_project(project_id, info)
            return {"status": "success", "project": project}
        except Exception as error:
            return {"status": "error", "message": f"导入成片失败: {error}"}
        finally:
            if pending is not None:
                try: pending.unlink(missing_ok=True)
                except OSError: pass

    def delete_ip_agent_project(self, project_id):
        try:
            target = self._get_ip_agent_project_dir(project_id)
            if not os.path.isdir(target):
                return {"error": "IP项目不存在"}
            if hasattr(self, "_ip_publish_lock"):
                with self._ip_publish_lock:
                    if str(project_id) in self._ip_publish_active:
                        return {"error": "项目正在发布，不能删除", "code": "publish_in_progress"}
            info_path = self._get_ip_agent_project_info_path(project_id)
            info = self._read_yaml_file(info_path) if os.path.isfile(info_path) else {}
            audit_path = self._archive_ip_agent_publish_audit(project_id, info)
            shutil.rmtree(target)
            result = {"status": "success", "message": "删除成功"}
            if audit_path:
                result["publish_audit_path"] = audit_path
            return result
        except Exception as error:
            return {"error": f"删除IP项目失败: {error}"}

    def get_ip_agent_creation_assets(self):
        from .add_subtitles_to_video import SUBTITLE_STYLE_PRESETS
        from .ip_agent_post_process import list_cover_templates, list_font_options, list_music_library
        try:
            subtitle_styles = [
                {"value": value, "font_name": style.get("font_name", "Microsoft YaHei"),
                 "highlight_color": style.get("highlight_color", "")}
                for value, style in SUBTITLE_STYLE_PRESETS.items()
            ]
            return {"status": "success", "music": list_music_library(limit=80),
                    "fonts": list_font_options(), "cover_templates": list_cover_templates(),
                    "subtitle_styles": subtitle_styles}
        except Exception as error:
            return {"error": f"获取IP智能体资源失败: {error}"}

    def get_ip_agent_media_data(self, file_path):
        try:
            full_path = os.path.abspath(file_path or "")
            if not full_path or not os.path.exists(full_path):
                return {"error": "媒体文件不存在"}
            data_url = self._encode_media_data(full_path)
            if not data_url:
                return {"error": "媒体文件过大或读取失败"}
            return {"status": "success", "file_path": full_path, "data_url": data_url}
        except Exception as error:
            return {"error": f"读取媒体失败: {error}"}

    @staticmethod
    def _normalize_keywords(value):
        import re
        values = value if isinstance(value, list) else re.split(r"[,，、\s]+", str(value or ""))
        return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))[:20]

    def rewrite_ip_script(self, data):
        from .llm_base_chat import base_chat
        from .ip_agent_post_process import infer_keywords_from_text
        try:
            data = data or {}
            original = str(data.get("text") or "").strip()
            if not original:
                return {"error": "请输入需要改写的文案"}
            custom = str(data.get("prompt") or "").strip()
            if not custom:
                custom = "保留原意，强化开头钩子、信息密度、口语节奏和行动引导，避免夸张虚假和空洞套话。"
            system = (
                "你是一名擅长短视频口播IP的爆款编导和文案医生。你会先拆解原文的钩子、痛点、结构、节奏和可优化点，"
                "再输出多个能直接给数字人口播的视频脚本版本。必须只输出 JSON，不要 Markdown，不要解释。"
            )
            output_schema = (
                "输出 JSON 格式如下：\n"
                "{\n"
                '  "analysis": {"hook": "开头钩子判断", "pain_point": "用户痛点", "structure": ["结构点1", "结构点2"], '
                '"rhythm": "节奏建议", "cta": "结尾引导", "risk_notes": "夸大、违规、低质表达风险"},\n'
                '  "versions": [{"name": "强钩子版", "text": "完整口播稿"}, {"name": "信任感版", "text": "完整口播稿"}, '
                '{"name": "短平快版", "text": "完整口播稿"}],\n'
                '  "keywords": ["用于字幕高亮的关键词1", "关键词2"]\n'
                "}\n"
                "三个版本都要像真人讲话，不要写分镜说明，不要写标题。"
            )
            question = (
                "请把下面文案做成「爆款拆解 + 成片口播稿」。\n\n【用户要求】\n"
                f"{custom}\n\n【原始文案】\n{original}\n\n{output_schema}"
            )
            raw = base_chat(
                question,
                system,
                model_type="script",
                raise_on_failure=True,
                llm_config=self.config.get("llm_config"),
            )
            import json, re
            match = re.search(r"\{[\s\S]*\}", str(raw or ""))
            parsed = json.loads(match.group(0) if match else str(raw or ""))
            versions = parsed.get("versions") or []
            normalized = []
            for index, item in enumerate(versions):
                if isinstance(item, dict):
                    text = str(item.get("text") or "").strip()
                    name = str(item.get("name") or f"改写版本{index + 1}").strip()
                else:
                    text = str(item or "").strip()
                    name = f"改写版本{index + 1}"
                if text:
                    normalized.append({"name": name, "text": text})
            fallback_text = str(parsed.get("rewritten_text") or parsed.get("text") or "").strip()
            if not normalized and fallback_text:
                normalized.append({"name": "成片稿", "text": fallback_text})
            if not normalized:
                return {"error": "改写失败，未获得有效内容"}
            rewritten_text = normalized[0]["text"]
            keywords = self._normalize_keywords(parsed.get("keywords"))
            if not keywords:
                keywords = infer_keywords_from_text(rewritten_text)
            result = {
                "status": "success",
                "rewritten_text": rewritten_text,
                "analysis": parsed.get("analysis") or {},
                "versions": normalized,
                "keywords": keywords,
            }
            project_id = str(data.get("project_id") or "").strip()
            if project_id and os.path.isdir(self._get_ip_agent_project_dir(project_id)):
                result["project"] = self._save_ip_agent_project(project_id, {
                    "original_script": original,
                    "rewrite_prompt": custom,
                    "rewritten_script": rewritten_text,
                    "script_analysis": result["analysis"],
                    "rewrite_versions": normalized,
                    "highlight_keywords": keywords,
                })
            return result
        except Exception as error:
            return {"error": f"改写文案失败: {error}"}

    def _get_douyin_downloader_paths(self):
        directory = Path(self.runtime_dir) / "tools" / "douyin_video_download"
        script = directory / "run_download.py"
        candidates = [directory / "env" / "python.exe", directory / "env" / "Scripts" / "python.exe",
                      directory / "env" / "bin" / "python", Path(sys.executable)]
        executable = next((path for path in candidates if path.is_file()), None)
        if not script.is_file(): raise FileNotFoundError("找不到抖音下载脚本")
        if executable is None: raise FileNotFoundError("找不到抖音下载工具运行环境")
        return str(executable), str(script)

    @staticmethod
    def _decode_subprocess_output(raw_data):
        if isinstance(raw_data, str): return raw_data
        for encoding in ("utf-8", "gb18030", "gbk"):
            try: return (raw_data or b"").decode(encoding)
            except UnicodeDecodeError: pass
        return (raw_data or b"").decode("utf-8", errors="replace")

    def extract_douyin_benchmark(self, url):
        from .asr_main import recognize_audio
        from .douyin_benchmark import (normalize_douyin_url, probe_video,
                                       resolve_ffprobe, select_downloaded_video)
        try:
            normalized_url = normalize_douyin_url(url)
            executable, script = self._get_douyin_downloader_paths()
            working_directory = Path(script).parent.resolve()
            result = subprocess.run([executable, script, normalized_url], cwd=str(working_directory),
                                    capture_output=True, timeout=600)
            stdout = self._decode_subprocess_output(result.stdout).strip(); stderr = self._decode_subprocess_output(result.stderr).strip()
            if result.returncode: raise RuntimeError(stderr or stdout or "抖音视频下载失败")
            video = select_downloaded_video(stdout, working_directory)
            probe_video(video, resolve_ffprobe(self.runtime_dir))
            weight = (Path(self.runtime_dir) / "assets" / "pretrained_models" / "asr" / "whisper" / "large-v3.pt")
            recognized = recognize_audio(str(video), str(weight))
            return {"status": "success", "video_path": str(video.resolve()),
                    "text_path": recognized["output_path"], "text": recognized["text"], "source_url": normalized_url}
        except Exception as error: return {"status": "error", "message": str(error)}

    def extract_ip_agent_benchmark(self, project_id, url):
        import tempfile
        try:
            info = self._load_ip_agent_project(project_id); result = self.extract_douyin_benchmark(url)
            if result.get("status") != "success": return result
            project_dir = Path(self._get_ip_agent_project_dir(project_id))
            target_dir = project_dir / "benchmark"
            staged = Path(tempfile.mkdtemp(prefix=".benchmark-", dir=str(project_dir)))
            backup = project_dir / ".benchmark-backup"
            suffix = Path(result["video_path"]).suffix.lower() or ".mp4"
            try:
                shutil.copy2(result["video_path"], staged / ("对标视频" + suffix))
                (staged / "对标文案.txt").write_text(result["text"], encoding="utf-8")
                if backup.exists(): shutil.rmtree(backup)
                if target_dir.exists(): target_dir.replace(backup)
                staged.replace(target_dir)
                shutil.rmtree(backup, ignore_errors=True)
            except Exception:
                shutil.rmtree(staged, ignore_errors=True)
                if backup.exists() and not target_dir.exists(): backup.replace(target_dir)
                raise
            video = target_dir / ("对标视频" + suffix); transcript = target_dir / "对标文案.txt"
            info.update({"benchmark_url": result.get("source_url") or url, "benchmark_video_path": str(video),
                         "benchmark_transcript_path": str(transcript), "benchmark_transcript": result["text"], "status": "benchmark_ready"})
            return {"status": "success", "project": self._save_ip_agent_project(project_id, info),
                    "video_path": str(video), "text_path": str(transcript), "text": result["text"]}
        except Exception as error: return {"status": "error", "message": f"提取对标视频失败: {error}"}

    def generate_ip_agent_publish_meta(self, project_id, data):
        from .generate_title import generate_title_and_tags
        try:
            project = self._load_ip_agent_project(project_id)
            if not project:
                return {"error": "IP项目不存在"}
            script = (data.get("script") or project.get("rewritten_script") or
                      project.get("original_script") or "").strip()
            if not script:
                return {"error": "请先准备文案内容"}
            video_url = data.get("video_url") or project.get("benchmark_url", "")
            title_result = generate_title_and_tags(script, video_url)
            title = str(title_result.get("title") or "").strip()
            tags = self._normalize_publish_tags(title_result.get("tags"))
            project = self._save_ip_agent_project(project_id, {
                "publish_title": title,
                "publish_tags_text": self._stringify_publish_tags(tags),
            })
            return {"status": "success", "title": title, "tags": tags, "project": project}
        except Exception as error:
            return {"error": f"生成发布标题和标签失败: {error}"}

    def generate_audio_for_ip_agent_project(self, project_id, data):
        from .short_video_audio_synthesis import synthesize_text_to_audio
        try:
            info = self._load_ip_agent_project(project_id)
            text = str(data.get("text") or data.get("script") or info.get("rewritten_script") or "").strip()
            voice_id = str(data.get("voice_id") or "").strip()
            if not text: raise ValueError("请先选择或生成口播文案")
            if not voice_id: raise ValueError("请选择声音模型")
            voice_base = Path(data.get("voice_base_dir") or self.config.get("voice_base_dir") or Path(self.runtime_dir) / "assets/characters/voices")
            voice_dir = voice_base / voice_id; reference_audio = voice_dir / "ref_audio.wav"; reference_text = voice_dir / "ref_text.txt"
            if not reference_audio.is_file(): raise FileNotFoundError(f"缺少参考音频: {reference_audio}")
            result = synthesize_text_to_audio(text=text, speed=float(data.get("speed", 1.0)),
                                              language=str(data.get("language") or "zh-CN"), scene="ip_agent",
                                              voice_id=voice_id, reference_audio=str(reference_audio),
                                              reference_text=reference_text.read_text(encoding="utf-8").strip() if reference_text.is_file() else "",
                                              config={**self.config, **(data.get("voice_config") or {}),
                                                      "voice_infer_version": data.get("voice_infer_version") or self.config.get("voice_infer_version")},
                                              project_root=str(self.runtime_dir), use_cache=bool(data.get("use_cache", True)))
            target = Path(info["audio_path"]); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(result["audio_path"], target)
            info.update({"rewritten_script": text, "voice_id": voice_id, "voice_infer_version": result["voice_infer_version"],
                         "language": result["language"], "audio_path": str(target),
                         "preview_audio_path": str(target), "status": "audio_ready"})
            return {"status": "success", "audio_path": str(target), "project": self._save_ip_agent_project(project_id, info)}
        except Exception as error: return {"status": "error", "message": f"生成驱动音频失败: {error}"}

    def create_ip_agent_video(self, project_id, data):
        from .generate_lip_sync_video import create_short_video
        try:
            info = self._load_ip_agent_project(project_id); audio = Path(data.get("audio_path") or info.get("audio_path", ""))
            if not audio.is_file(): raise FileNotFoundError("请先生成驱动音频")
            payload = {**data, "mode": "audio", "audio_path": str(audio),
                       "short_video_id": "lip_sync", "custom_output_dir": self._get_ip_agent_project_dir(project_id)}
            result = create_short_video(payload, {**self.config, "project_root": str(self.runtime_dir)})
            if not result.get("success"): raise RuntimeError(result.get("error") or "数字人口型生成失败")
            target = Path(info["video_path"]); shutil.copy2(result["video_path"], target)
            info.update({"video_path": str(target), "result_video_path": str(target), "status": "video_ready"})
            info = self._save_ip_agent_project(project_id, info)
            return {"status": "success", "video_path": str(target), "project": info}
        except Exception as error: return {"status": "error", "message": f"生成 IP 数字人视频失败: {error}"}

    def add_subtitles_to_ip_agent_video(self, project_id, data):
        from .add_subtitles_to_video import add_subtitles_to_video
        from .get_srt import generate_srt_for_video
        try:
            info = self._load_ip_agent_project(project_id)
            video = Path(data.get("video_path") or info.get("video_path", ""))
            if not video.is_file(): raise FileNotFoundError("请先生成数字人口播视频")
            srt = data.get("subtitle_path")
            if not srt:
                weight = data.get("asr_weight_path") or Path(self.runtime_dir) / "assets/pretrained_models/asr/whisper/large-v3.pt"
                srt = generate_srt_for_video(str(video), str(weight),
                                             output_path=str(Path(self._get_ip_agent_project_dir(project_id)) / "口播字幕.srt"))["srt_path"]
            options = {key: data[key] for key in ("style_preset", "font_name", "font_color", "outline_color", "font_size",
                       "margin_v", "margin_l", "margin_r", "max_chars_per_line", "highlight_words", "highlight_color",
                       "animation", "fonts_dir") if data.get(key) is not None}
            output = add_subtitles_to_video(str(video), str(srt), output_path=info["subtitle_video_path"], **options)
            info.update({"subtitle_path": str(srt), "subtitle_srt_path": str(srt),
                         "subtitle_video_path": output, "subtitled_video_path": output,
                         "status": "subtitle_ready"})
            return {"status": "success", "video_path": output, "subtitle_path": str(srt),
                    "project": self._save_ip_agent_project(project_id, info)}
        except Exception as error: return {"status": "error", "message": f"添加字幕失败: {error}"}

    def apply_ip_agent_finishing(self, project_id, data):
        from .ip_agent_post_process import download_music, mix_bgm
        try:
            info = self._load_ip_agent_project(project_id)
            candidates = [data.get("video_path"), info.get("subtitle_video_path"), info.get("video_path")]
            source = Path(next((item for item in candidates if item and Path(item).is_file()), ""))
            if not source.is_file(): raise FileNotFoundError("没有可后期处理的视频")
            target = Path(info["final_video_path"])
            if data.get("bgm_enabled"):
                bgm = data.get("bgm_path")
                if not bgm: bgm = download_music(str(data.get("music_id") or "default"), str(data.get("music_url") or ""))
                mix_bgm(str(source), str(bgm), str(target), volume=float(data.get("bgm_volume", .16)))
            else: shutil.copy2(source, target)
            info.update({"final_video_path": str(target), "status": "complete"})
            return {"status": "success", "video_path": str(target), "project": self._save_ip_agent_project(project_id, info)}
        except Exception as error: return {"status": "error", "message": f"成片后期处理失败: {error}"}

    def one_click_create_ip_agent_video(self, project_id, data):
        from datetime import datetime
        from .ip_pipeline import (PIPELINE_VERSION, StepFileCheckpoint,
                                  completed_step_ready, pipeline_fingerprint,
                                  project_pipeline_lock, result_summary)

        if not isinstance(data, dict):
            return {"status": "error", "message": "一键成片参数格式错误", "steps": []}
        operations = (("audio", self.generate_audio_for_ip_agent_project),
                      ("video", self.create_ip_agent_video),
                      ("subtitles", self.add_subtitles_to_ip_agent_video),
                      ("finishing", self.apply_ip_agent_finishing),
                      ("publish_meta", self.generate_ip_agent_publish_meta))
        with project_pipeline_lock(project_id):
            try:
                project = self._load_ip_agent_project(project_id)
                if not project:
                    raise FileNotFoundError("IP项目不存在")
                fingerprint = pipeline_fingerprint(project_id, data, project)
                previous = project.get("one_click_pipeline") or {}
                completed = list(previous.get("completed_steps") or []) if (
                    previous.get("version") == PIPELINE_VERSION and
                    previous.get("fingerprint") == fingerprint
                ) else []
                completed = [name for name in completed if name in dict(operations) and completed_step_ready(name, project)]
                if previous.get("status") == "complete" and len(completed) == len(operations):
                    return {"status": "success", "already_complete": True,
                            "steps": previous.get("steps") or [], "project": project}
                state = {
                    "version": PIPELINE_VERSION, "fingerprint": fingerprint,
                    "status": "running", "current_step": "", "completed_steps": completed,
                    "steps": list(previous.get("steps") or []) if completed else [],
                    "started_at": previous.get("started_at") or datetime.now().isoformat(timespec="seconds"),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                project["one_click_pipeline"] = state
                project["one_click_last_result"] = state["steps"]
                self._save_ip_agent_project(project_id, project)
            except Exception as error:
                return {"status": "error", "message": str(error), "steps": []}

            for name, operation in operations:
                project = self._load_ip_agent_project(project_id)
                if name in completed and completed_step_ready(name, project):
                    continue
                state["current_step"] = name
                state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                project["one_click_pipeline"] = state
                self._save_ip_agent_project(project_id, project)
                checkpoint = StepFileCheckpoint(project, name)
                try:
                    result = operation(project_id, data)
                except Exception as error:
                    result = {"status": "error", "message": str(error)}
                summary = {"step": name, "result": result_summary(result)}
                state["steps"] = [item for item in state["steps"] if item.get("step") != name] + [summary]
                if result.get("status") != "success":
                    rollback_errors = checkpoint.rollback()
                    state.update({"status": "failed", "current_step": name,
                                  "updated_at": datetime.now().isoformat(timespec="seconds")})
                    project = self._load_ip_agent_project(project_id)
                    project["one_click_pipeline"] = state
                    project["one_click_last_result"] = state["steps"]
                    self._save_ip_agent_project(project_id, project)
                    message = result.get("message") or result.get("error") or f"{name} 步骤失败"
                    if rollback_errors:
                        message += "；文件回滚不完整: " + "; ".join(rollback_errors)
                    return {"status": "error", "message": message, "failed_step": name,
                            "resumable": not rollback_errors, "steps": state["steps"]}
                checkpoint.close()
                completed.append(name)
                state["completed_steps"] = completed.copy()
                state["current_step"] = ""
                state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                project = self._load_ip_agent_project(project_id)
                project["one_click_pipeline"] = state
                project["one_click_last_result"] = state["steps"]
                self._save_ip_agent_project(project_id, project)
            state.update({"status": "complete", "current_step": "",
                          "completed_at": datetime.now().isoformat(timespec="seconds"),
                          "updated_at": datetime.now().isoformat(timespec="seconds")})
            project = self._load_ip_agent_project(project_id)
            project["one_click_pipeline"] = state
            project["one_click_last_result"] = state["steps"]
            project = self._save_ip_agent_project(project_id, project)
            return {"status": "success", "steps": state["steps"], "project": project}

    def publish_ip_agent_video(self, project_id, data):
        if data.get("dry_run"):
            return self._publish_ip_agent_video(project_id, data)
        if not hasattr(self, "_ip_publish_lock"):
            self._ip_publish_lock = RLock()
            self._ip_publish_active = set()
        project_key = str(project_id)
        with self._ip_publish_lock:
            if project_key in self._ip_publish_active:
                return {"status": "error", "message": "该项目已有发布任务正在运行，请勿重复提交",
                        "code": "publish_in_progress"}
            self._ip_publish_active.add(project_key)
        try:
            return self._publish_ip_agent_video(project_id, data)
        finally:
            with self._ip_publish_lock:
                self._ip_publish_active.discard(project_key)

    def _publish_ip_agent_video(self, project_id, data):
        import asyncio
        from .douyin_benchmark import probe_video, resolve_ffprobe
        from .ip_publish import build_publish_plan
        try:
            info = self._load_ip_agent_project(project_id)
            candidates = [data.get("video_path"), info.get("final_video_path"),
                          info.get("subtitle_video_path"), info.get("video_path")]
            video = next((str(value) for value in candidates if value and Path(value).is_file()), "")
            if not video: raise FileNotFoundError("请先生成可用的视频成片")
            title = str(data.get("title") or info.get("publish_title") or info.get("name") or "").strip()
            tags = self._normalize_publish_tags(data.get("tags") or info.get("publish_tags"))
            plan = build_publish_plan(
                video, title, tags, data.get("platforms", []),
                data.get("account_names") or data.get("publish_accounts") or {},
                data.get("publish_date", 0), data.get("thumbnail_path") or info.get("cover_path"),
                data.get("request_id"),
            )
            probe_video(plan["video_path"], resolve_ffprobe(self.runtime_dir))
            public_plan = {key: value for key, value in plan.items() if key != "publish_date_value"}
            if data.get("dry_run"):
                return {"status": "success", "dry_run": True, "publish_plan": public_plan}
            previous = info.get("publish_last_result") or {}
            if (not data.get("force_republish") and info.get("publish_last_request_id") == plan["request_id"]
                    and isinstance(previous, dict) and previous.get("success")):
                return {"status": "success", "already_published": True,
                        "publish_result": previous, "publish_plan": public_plan}
            previous_task = info.get("publish_task") or {}
            if (previous_task.get("status") == "interrupted"
                    and previous_task.get("request_id") == plan["request_id"]
                    and not data.get("confirm_retry_after_interruption")):
                return {"status": "error", "code": "publish_outcome_unknown",
                        "message": "上次发布被中断，结果未知；请先到平台核对，再确认是否重试",
                        "publish_task": previous_task, "publish_plan": public_plan}
            started_at = datetime.now().isoformat(timespec="seconds")
            attempt = {"request_id": plan["request_id"], "status": "running", "started_at": started_at,
                       "updated_at": started_at, "plan": public_plan}
            attempts = list(info.get("publish_attempts") or [])
            attempts.append(attempt)
            info.update({"publish_last_request_id": plan["request_id"], "publish_last_plan": public_plan,
                         "publish_task": attempt, "publish_attempts": attempts[-100:]})
            self._save_ip_agent_project(project_id, info)
            try:
                from tools.social_auto_upload.test import publish_video_to_platforms
            except ImportError:
                import importlib.util
                module_path = Path(self.runtime_dir) / "tools/social_auto_upload/test.py"
                if not module_path.is_file(): raise FileNotFoundError("未找到社交平台自动发布模块")
                spec = importlib.util.spec_from_file_location("recovered_social_auto_upload", module_path)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                publish_video_to_platforms = module.publish_video_to_platforms
            coroutine = publish_video_to_platforms(
                video_path=plan["video_path"], title=plan["title"], tags=plan["tags"], platforms=plan["platforms"],
                account_names=plan["account_names"], publish_date=plan["publish_date_value"],
                thumbnail_path=plan["thumbnail_path"] or None,
                handle_login=bool(data.get("handle_login", True)))
            try: asyncio.get_running_loop()
            except RuntimeError: result = asyncio.run(coroutine)
            else:
                import threading
                holder = {}
                def runner():
                    try: holder["result"] = asyncio.run(coroutine)
                    except Exception as error: holder["error"] = error
                thread = threading.Thread(target=runner); thread.start(); thread.join()
                if "error" in holder: raise holder["error"]
                result = holder["result"]
            try:
                if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
                    raise ValueError("发布模块返回结构无效")
            except Exception:
                raise
            completed_at = datetime.now().isoformat(timespec="seconds")
            attempt.update({"status": "success" if result.get("success") else "failed",
                            "updated_at": completed_at, "completed_at": completed_at, "result": result})
            info.update({"publish_platforms": plan["platforms"], "publish_accounts": plan["account_names"],
                         "publish_title": plan["title"], "publish_tags": plan["tags"],
                         "publish_date": public_plan["publish_date"], "publish_last_request_id": plan["request_id"],
                         "publish_last_plan": public_plan,
                         "publish_last_result": result, "publish_task": attempt,
                         "publish_attempts": attempts[-100:],
                         "status": "published" if result.get("success") else "publish_failed"})
            self._save_ip_agent_project(project_id, info)
            return {"status": "success" if result.get("success") else "error", "publish_result": result,
                    "publish_plan": public_plan,
                    "message": "发布任务完成" if result.get("success") else "部分或全部平台发布失败"}
        except Exception as error:
            if "attempt" in locals():
                failed_at = datetime.now().isoformat(timespec="seconds")
                attempt.update({"status": "failed", "updated_at": failed_at,
                                "completed_at": failed_at, "error": str(error)})
                try:
                    failed_info = self._load_ip_agent_project(project_id)
                    history = list(failed_info.get("publish_attempts") or [])
                    replaced = False
                    for index in range(len(history) - 1, -1, -1):
                        if (history[index].get("request_id") == attempt["request_id"]
                                and history[index].get("started_at") == attempt["started_at"]):
                            history[index] = attempt
                            replaced = True
                            break
                    if not replaced:
                        history.append(attempt)
                    failed_info.update({"publish_task": attempt, "publish_attempts": history[-100:],
                                        "publish_last_request_id": attempt["request_id"],
                                        "publish_last_plan": attempt["plan"], "status": "publish_failed"})
                    self._save_ip_agent_project(project_id, failed_info)
                except Exception:
                    pass
            return {"status": "error", "message": f"发布视频失败: {error}"}

    def _get_live_sticker_base_dir(self):
        return os.path.join(str(self.runtime_dir), "assets", "live_sticker_projects")

    def _get_live_sticker_project_dir(self, project_id):
        base = Path(self._get_live_sticker_base_dir()).resolve()
        target = (base / str(project_id)).resolve()
        if target.parent != base:
            raise ValueError("无效的贴片项目 ID")
        return str(target)

    def _get_live_sticker_project_info_path(self, project_id):
        return str(Path(self._get_live_sticker_project_dir(project_id)) / "project_info.yaml")

    def _get_live_sticker_history_dir(self, project_id):
        return str(Path(self._get_live_sticker_project_dir(project_id)) / "history")

    def _get_live_sticker_output_paths(self, project_id):
        directory = Path(self._get_live_sticker_project_dir(project_id))
        return {
            "bg": str(directory / "背景.png"),
            "fg_white": str(directory / "前景贴片_绿底.png"),
            "fg_alpha": str(directory / "前景贴片_透明.png"),
            "cover_raw": str(directory / "直播间封面_原始.png"),
            "cover": str(directory / "直播间封面.png"),
        }

    def _default_live_sticker_project_info(self, project_id, name):
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            "id": project_id, "name": name, "create_time": now, "update_time": now,
            "product_name": "", "product_price": "", "product_selling_points": "",
            "product_content": "", "product_item_id": "", "product_pic": "",
            "background_prompt": "", "foreground_prompt": "", "cover_prompt": "",
            "bg_path": "", "fg_white_path": "", "fg_alpha_path": "",
            "cover_path": "", "cover_raw_path": "", "bg_size": "", "fg_size": "",
            "cover_size": "", "room_title": "", "room_titles": [], "title_model": "",
            "last_error": "", "status": "draft",
        }

    def _build_live_sticker_project_summary(self, project_id, info):
        project_dir = self._get_live_sticker_project_dir(project_id)
        create_time = info.get("create_time", "")
        return {
            "id": project_id,
            "name": info.get("name") or f"贴片项目-{project_id}",
            "create_time": create_time,
            "update_time": info.get("update_time", create_time),
            "preview_url": self._encode_preview_image(str(info.get("bg_path") or "").strip()),
            "path": os.path.abspath(project_dir),
            "status": info.get("status") or "draft",
        }

    def _load_live_sticker_project(self, project_id):
        project_dir = self._get_live_sticker_project_dir(project_id)
        if not os.path.isdir(project_dir):
            return None
        value = self._read_yaml_file(self._get_live_sticker_project_info_path(project_id))
        if not value:
            return None
        value = dict(value)
        value["id"] = project_id
        value["path"] = os.path.abspath(project_dir)
        outputs = self._get_live_sticker_output_paths(project_id)
        for key, field in (
            ("bg", "bg_path"), ("fg_white", "fg_white_path"),
            ("fg_alpha", "fg_alpha_path"), ("cover_raw", "cover_raw_path"),
            ("cover", "cover_path"),
        ):
            configured = str(value.get(field) or "").strip()
            if not configured and os.path.exists(outputs[key]):
                value[field] = outputs[key]
        # Early builds stored the green foreground under this fixed filename but
        # omitted the YAML field. Preserve those production projects.
        legacy_green = os.path.join(project_dir, "前景贴片_绿底.png")
        if not str(value.get("fg_white_path") or "").strip() and os.path.exists(legacy_green):
            value["fg_white_path"] = legacy_green
        titles = value.get("room_titles")
        if isinstance(titles, str):
            titles = [item.strip() for item in titles.replace("，", ",").split(",") if item.strip()]
        elif not isinstance(titles, list):
            titles = []
        title = str(value.get("room_title") or "").strip()
        if title and title not in titles:
            titles.insert(0, title)
        value["room_titles"] = titles
        value["room_title"] = title or (titles[0] if titles else "")
        return value

    def _save_live_sticker_project(self, project_id, data):
        from datetime import datetime
        directory = self._get_live_sticker_project_dir(project_id)
        if not os.path.isdir(directory):
            raise FileNotFoundError("贴片项目不存在")
        current = self._read_yaml_file(self._get_live_sticker_project_info_path(project_id)) or {}
        name = str(current.get("name") or data.get("name") or f"贴片项目-{project_id}").strip()
        value = self._default_live_sticker_project_info(project_id, name)
        value.update(current)
        value.update(data)
        value["id"] = project_id
        value["name"] = str(value.get("name") or f"贴片项目-{project_id}").strip()
        value["create_time"] = value.get("create_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        value["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        titles = value.get("room_titles")
        if isinstance(titles, str):
            titles = [item.strip() for item in titles.replace("，", ",").split(",") if item.strip()]
        elif not isinstance(titles, list):
            titles = []
        value["room_titles"] = titles
        value["room_title"] = str(value.get("room_title") or (titles[0] if titles else "")).strip()
        self._write_yaml_file(self._get_live_sticker_project_info_path(project_id), value)
        return self._load_live_sticker_project(project_id)

    def _live_sticker_image_ready(self, image_config):
        return bool(image_config) and all(Path(path).is_file() for path in image_config.values())

    def _generate_live_sticker_image_file(self, *, image_config, prompt, dest, aspect_ratio="9:16"):
        from .runninghub_image import _generate_and_download_cancellable
        cancel_check = image_config.get("_cancel_check")
        _generate_and_download_cancellable(
            api_key=image_config["api_key"], prompt=prompt, dest=dest,
            aspect_ratio=aspect_ratio, resolution=image_config.get("resolution", "2k"),
            quality=image_config.get("quality", "low"),
            poll_interval=int(image_config.get("poll_interval", 5)),
            poll_timeout=int(image_config.get("poll_timeout", 900)),
            cancel_check=cancel_check)

    def _live_sticker_job_state(self):
        if not hasattr(self, "_live_sticker_generation_lock"):
            self._live_sticker_generation_lock = RLock(); self._live_sticker_cancel_events = {}
        return self._live_sticker_generation_lock, self._live_sticker_cancel_events

    def cancel_live_sticker_generation(self, project_id):
        if not isinstance(project_id, str) or not project_id.strip():
            return {"status": "error", "message": "贴片项目 ID 无效"}
        lock, jobs = self._live_sticker_job_state()
        with lock:
            event = jobs.get(project_id)
            if event is None: return {"status": "idle", "message": "当前没有贴片生成任务"}
            event.set()
        return {"status": "cancel_requested", "project_id": project_id}

    def _archive_live_sticker_outputs(self, project_id, info):
        from datetime import datetime
        existing = [Path(str(info.get(key) or "").strip()) for key in
                    ("bg_path", "fg_white_path", "fg_alpha_path", "cover_path")]
        existing = [path for path in existing if str(path) not in ("", ".") and path.is_file()]
        if not existing: return
        root = Path(self._get_live_sticker_history_dir(project_id))
        stem = datetime.now().strftime("%Y%m%d_%H%M%S"); history = root / stem
        suffix = 1
        while history.exists():
            history = root / f"{stem}_{suffix:02d}"; suffix += 1
        history.mkdir(parents=True, exist_ok=True)
        for path in existing: shutil.copy2(path, history / path.name)

    def _attach_live_sticker_previews(self, project):
        for field in ("bg", "fg_white", "fg_alpha", "cover"):
            path = str(project.get(field + "_path") or "").strip()
            project[field + "_preview_url"] = self._encode_preview_image(path)
        titles = project.get("room_titles")
        if not isinstance(titles, list):
            titles = []
        title = str(project.get("room_title") or "").strip()
        if not titles and title:
            titles = [title]
        project["room_titles"] = titles
        project["room_title"] = title or (titles[0] if titles else "")
        return project

    def create_live_sticker_project(self, name):
        from uuid import uuid4
        if not isinstance(name, str):
            raise TypeError("name must be a str")
        name = name.strip()
        if not name: return {"error": "请输入项目名称"}
        try:
            project_id = str(uuid4())
            os.makedirs(self._get_live_sticker_project_dir(project_id), exist_ok=True)
            info = self._default_live_sticker_project_info(project_id, name)
            self._write_yaml_file(self._get_live_sticker_project_info_path(project_id), info)
            return {"status": "success", "project": self._attach_live_sticker_previews(
                self._load_live_sticker_project(project_id))}
        except Exception as error: return {"error": f"创建贴片项目失败: {error}"}

    def get_all_live_sticker_projects(self):
        try:
            base = self._get_live_sticker_base_dir(); os.makedirs(base, exist_ok=True); projects = []
            for project_id in os.listdir(base):
                if not os.path.isdir(os.path.join(base, project_id)):
                    continue
                info = self._read_yaml_file(self._get_live_sticker_project_info_path(project_id))
                if info:
                    projects.append(self._build_live_sticker_project_summary(project_id, info))
            projects.sort(key=lambda item: item.get("update_time", ""), reverse=True)
            return {"status": "success", "projects": projects}
        except Exception as error: return {"error": f"获取贴片项目列表失败: {error}"}

    def get_live_sticker_project(self, project_id):
        if not isinstance(project_id, str):
            raise TypeError("project_id must be a str")
        try:
            project = self._load_live_sticker_project(project_id)
            if not project: return {"error": "贴片项目不存在"}
            return {"status": "success", "project": self._attach_live_sticker_previews(project)}
        except Exception as error: return {"error": f"获取贴片项目失败: {error}"}

    def update_live_sticker_project(self, project_id, data):
        if not isinstance(project_id, str):
            raise TypeError("project_id must be a str")
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        try:
            project = self._save_live_sticker_project(project_id, data or {})
            return {"status": "success", "project": self._attach_live_sticker_previews(project)}
        except Exception as error: return {"error": f"保存贴片项目失败: {error}"}

    def delete_live_sticker_project(self, project_id):
        if not isinstance(project_id, str):
            raise TypeError("project_id must be a str")
        try:
            target = Path(self._get_live_sticker_project_dir(project_id))
            if not target.is_dir(): return {"error": "贴片项目不存在"}
            shutil.rmtree(target); return {"status": "success", "message": "删除成功"}
        except Exception as error: return {"error": f"删除贴片项目失败: {error}"}

    def generate_live_sticker_prompts(self, data):
        from .live_sticker_prompts import build_prompt_pair
        try:
            project_id = data["project_id"]; info = self._load_live_sticker_project(project_id)
            product = data.get("product") or info.get("product") or {}; prompts = build_prompt_pair(product)
            info.update(prompts); info["product"] = product; self._save_live_sticker_project(project_id, info)
            return {"status": "success", **prompts}
        except Exception as error: return {"status": "error", "message": str(error)}

    def generate_live_sticker_room_titles(self, data):
        from .live_sticker_titles import generate_room_titles
        try:
            project_id = data["project_id"]; info = self._load_live_sticker_project(project_id)
            result = generate_room_titles(data.get("product") or info.get("product") or {},
                                          ark_api_key=str(data.get("ark_api_key") or ""))
            info["room_titles"] = result["room_titles"]; self._save_live_sticker_project(project_id, info)
            return {"status": "success", "titles": result["room_titles"]}
        except Exception as error: return {"status": "error", "message": f"生成直播间标题失败: {error}"}

    def generate_live_sticker_images(self, data):
        from .live_sticker_image_utils import (compress_sticker_image, image_size_label,
                                                key_green, resize_cover_square)
        info = None; cancel_event = None; project_id = None
        try:
            project_id = data["project_id"]; info = self._load_live_sticker_project(project_id)
            if not info: raise FileNotFoundError("贴片项目不存在")
            lock, jobs = self._live_sticker_job_state()
            with lock:
                if project_id in jobs: raise RuntimeError("该贴片项目正在生成")
                cancel_event = Event(); jobs[project_id] = cancel_event
            api_key = str(data.get("runninghub_api_key") or "").strip()
            if not api_key: raise ValueError("请填写 RunningHub API Key")
            outputs = self._get_live_sticker_output_paths(project_id)
            config = {"api_key": api_key, **(data.get("image_config") or {}),
                      "_cancel_check": cancel_event.is_set}
            directory = Path(self._get_live_sticker_project_dir(project_id))
            # Providers can fail or be cancelled after producing only part of a
            # batch. Build and validate all five assets off to the side so the
            # last complete project remains usable until the whole batch is ready.
            with TemporaryDirectory(prefix=".sticker-stage-", dir=directory) as staging_dir:
                staging = {key: str(Path(staging_dir) / Path(path).name) for key, path in outputs.items()}
                self._generate_live_sticker_image_file(
                    image_config=config, prompt=data.get("background_prompt") or info["background_prompt"],
                    dest=staging["bg"])
                self._generate_live_sticker_image_file(
                    image_config=config, prompt=data.get("foreground_prompt") or info["foreground_prompt"],
                    dest=staging["fg_white"])
                if cancel_event.is_set(): raise InterruptedError("图片生成已取消")
                key_green(staging["fg_white"], staging["fg_alpha"])
                self._generate_live_sticker_image_file(
                    image_config=config, prompt=data.get("cover_prompt") or info["cover_prompt"],
                    dest=staging["cover_raw"], aspect_ratio="1:1")
                if cancel_event.is_set(): raise InterruptedError("图片生成已取消")
                resize_cover_square(staging["cover_raw"], staging["cover"])
                compress_sticker_image(staging["bg"], staging["bg"])
                if not all(Path(path).is_file() and Path(path).stat().st_size for path in staging.values()):
                    raise RuntimeError("贴片生成结果不完整")
                self._archive_live_sticker_outputs(project_id, info)
                backup = Path(staging_dir) / "previous"; backup.mkdir()
                replaced = []
                try:
                    for key, target_value in outputs.items():
                        target = Path(target_value)
                        if target.is_file(): shutil.copy2(target, backup / target.name)
                        os.replace(staging[key], target); replaced.append(target)
                except Exception:
                    for target in replaced:
                        previous = backup / target.name
                        if previous.is_file(): os.replace(previous, target)
                        else: target.unlink(missing_ok=True)
                    raise
            info.update({
                "bg_path": outputs["bg"], "fg_white_path": outputs["fg_white"],
                "fg_alpha_path": outputs["fg_alpha"], "cover_raw_path": outputs["cover_raw"],
                "cover_path": outputs["cover"], "bg_size": image_size_label(outputs["bg"]),
                "fg_size": image_size_label(outputs["fg_alpha"]),
                "cover_size": image_size_label(outputs["cover"]), "status": "success",
                "last_error": "",
            })
            project = self._save_live_sticker_project(project_id, info)
            return {"status": "success", "project": self._attach_live_sticker_previews(project)}
        except Exception as error:
            status = "cancelled" if isinstance(error, InterruptedError) else "error"
            if info and cancel_event is not None:
                try: self._save_live_sticker_project(data["project_id"], {
                    "status": status, "last_error": str(error)})
                except Exception: pass
            return {"status": status, "message": f"生成贴片失败: {error}"}
        finally:
            if cancel_event is not None:
                lock, jobs = self._live_sticker_job_state()
                with lock:
                    if jobs.get(project_id) is cancel_event: jobs.pop(project_id, None)

    def _get_cloud_dh_base_dir(self):
        return str(Path(self.runtime_dir) / "cloud_dh_projects")

    def _get_cloud_dh_project_dir(self, project_id):
        base = Path(self._get_cloud_dh_base_dir()).resolve(); target = (base / str(project_id)).resolve()
        if target.parent != base: raise ValueError("无效的云数字人项目 ID")
        return str(target)

    def _get_cloud_dh_project_info_path(self, project_id):
        return str(Path(self._get_cloud_dh_project_dir(project_id)) / "project_info.yaml")

    def _get_cloud_dh_history_dir(self, project_id):
        return str(Path(self._get_cloud_dh_project_dir(project_id)) / "history")

    def _get_cloud_dh_output_paths(self, project_id):
        directory = Path(self._get_cloud_dh_project_dir(project_id))
        return {"avatar": str(directory / "数字人形象.png"), "audio": str(directory / "口播音频.wav"),
                "video": str(directory / "数字人口播.mp4")}

    def _default_cloud_dh_project_info(self, project_id, name):
        from datetime import datetime
        return {"id": project_id, "name": name, "created_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"), "avatar_prompt": "",
                "outputs": self._get_cloud_dh_output_paths(project_id)}

    def _build_cloud_dh_project_summary(self, project_id, info):
        outputs = self._get_cloud_dh_output_paths(project_id)
        task = info.get("generation_task") if isinstance(info.get("generation_task"), dict) else {}
        return {"id": project_id, "name": info.get("name", project_id), "updated_at": info.get("updated_at", ""),
                "avatar_ready": Path(outputs["avatar"]).is_file(), "audio_ready": Path(outputs["audio"]).is_file(),
                "video_ready": Path(outputs["video"]).is_file(),
                "generation_status": task.get("status"), "generation_operation": task.get("operation")}

    def _load_cloud_dh_project(self, project_id):
        import yaml
        path = Path(self._get_cloud_dh_project_info_path(project_id))
        if not path.is_file(): raise FileNotFoundError("云数字人项目不存在")
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return value if isinstance(value, dict) else {}

    def _save_cloud_dh_project(self, project_id, data):
        from datetime import datetime
        import yaml
        directory = Path(self._get_cloud_dh_project_dir(project_id)); directory.mkdir(parents=True, exist_ok=True)
        value = dict(data); value["id"] = project_id; value["outputs"] = self._get_cloud_dh_output_paths(project_id)
        value["updated_at"] = datetime.now().isoformat(timespec="seconds")
        target = Path(self._get_cloud_dh_project_info_path(project_id))
        temporary = target.with_name(".project_info.yaml.pending")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(yaml.safe_dump(value, allow_unicode=True, sort_keys=False))
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return value

    def _recover_cloud_dh_project(self, project_id, info):
        task = info.get("generation_task")
        if not isinstance(task, dict) or task.get("status") != "running": return info
        lock, jobs = self._cloud_dh_job_state()
        with lock:
            if project_id in jobs: return info
        directory = Path(self._get_cloud_dh_project_dir(project_id))
        for pattern in (".*.pending.*", ".*.importing"):
            for path in directory.glob(pattern):
                if path.is_file(): path.unlink(missing_ok=True)
        from datetime import datetime
        value = dict(info); value["generation_task"] = {
            **task, "status": "interrupted", "ended_at": datetime.now().isoformat(timespec="seconds"),
            "error": "上次任务在进程退出时中断",
        }
        return self._save_cloud_dh_project(project_id, value)

    def _resolve_cloud_dh_api_key(self, override=None):
        value = override.get("runninghub_api_key") if isinstance(override, dict) else override
        key = str(value or self.config.get("runninghub_api_key") or "").strip()
        if not key: raise ValueError("请填写 RunningHub API Key")
        return key

    def _archive_cloud_dh_outputs(self, project_id, info):
        from datetime import datetime
        existing = [Path(path) for path in self._get_cloud_dh_output_paths(project_id).values() if Path(path).is_file()]
        if existing:
            root = Path(self._get_cloud_dh_history_dir(project_id))
            stem = datetime.now().strftime("%Y%m%d_%H%M%S"); target = root / stem
            suffix = 1
            while target.exists():
                target = root / f"{stem}_{suffix:02d}"; suffix += 1
            target.mkdir(parents=True, exist_ok=True)
            for path in existing: shutil.copy2(path, target / path.name)
            return str(target)
        return ""

    def _attach_cloud_dh_previews(self, project):
        import base64
        value = dict(project); previews = {}
        for key, path in self._get_cloud_dh_output_paths(value["id"]).items():
            file = Path(path)
            if file.is_file() and key == "avatar":
                previews[key] = "data:image/png;base64," + base64.b64encode(file.read_bytes()).decode("ascii")
            elif file.is_file(): previews[key] = str(file)
        value["previews"] = previews; return value

    def create_cloud_dh_project(self, name):
        from uuid import uuid4
        try:
            if not str(name).strip(): raise ValueError("请输入项目名称")
            project_id = uuid4().hex
            return {"status": "success", "project": self._save_cloud_dh_project(
                project_id, self._default_cloud_dh_project_info(project_id, str(name).strip()))}
        except Exception as error: return {"status": "error", "message": f"创建云数字人项目失败: {error}"}

    def get_all_cloud_dh_projects(self):
        try:
            base = Path(self._get_cloud_dh_base_dir()); projects = []
            if base.is_dir():
                for directory in base.iterdir():
                    if directory.is_dir() and (directory / "project_info.yaml").is_file():
                        info = self._recover_cloud_dh_project(directory.name, self._load_cloud_dh_project(directory.name))
                        projects.append(self._build_cloud_dh_project_summary(directory.name, info))
            projects.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            return {"status": "success", "projects": projects}
        except Exception as error: return {"status": "error", "message": f"获取云数字人项目失败: {error}"}

    def get_cloud_dh_project(self, project_id):
        try:
            info = self._recover_cloud_dh_project(project_id, self._load_cloud_dh_project(project_id))
            return {"status": "success", "project": self._attach_cloud_dh_previews(info)}
        except Exception as error: return {"status": "error", "message": str(error)}

    def update_cloud_dh_project(self, project_id, data):
        try:
            info = self._load_cloud_dh_project(project_id); info.update(data or {})
            return {"status": "success", "project": self._save_cloud_dh_project(project_id, info)}
        except Exception as error: return {"status": "error", "message": str(error)}

    def delete_cloud_dh_project(self, project_id):
        try:
            target = Path(self._get_cloud_dh_project_dir(project_id))
            if not target.is_dir(): raise FileNotFoundError("云数字人项目不存在")
            shutil.rmtree(target); return {"status": "success"}
        except Exception as error: return {"status": "error", "message": str(error)}

    def _pick_cloud_dh_file(self, project_id, kind, extensions):
        import webview
        selected = webview.windows[0].create_file_dialog(webview.OPEN_DIALOG, file_types=extensions)
        if not selected: return {"status": "cancelled"}
        source = Path(selected[0] if isinstance(selected, (list, tuple)) else selected)
        return self._import_cloud_dh_file(project_id, kind, source)

    def _import_cloud_dh_file(self, project_id, kind, source):
        if kind not in ("avatar", "audio"): raise ValueError("云数字人素材类型无效")
        event = self._begin_cloud_dh_job(project_id, "import_" + kind)
        outcome = "succeeded"; failure = ""
        try:
            info = self._load_cloud_dh_project(project_id)
            source = Path(source).expanduser().resolve()
            if not source.is_file() or source.stat().st_size == 0: raise FileNotFoundError("素材文件不存在或为空")
            outputs = self._get_cloud_dh_output_paths(project_id); target = Path(outputs[kind])
            target.parent.mkdir(parents=True, exist_ok=True)
            staged = target.with_name(f".{target.name}.importing"); staged.unlink(missing_ok=True)
            try:
                shutil.copy2(source, staged)
                if kind == "avatar":
                    from PIL import Image
                    with Image.open(staged) as image:
                        image.verify()
                        if image.width < 64 or image.height < 64: raise ValueError("数字人形象尺寸过小")
                else:
                    duration = float(get_audio_duration(str(staged)))
                    if not 0 < duration <= 3600: raise ValueError("口播音频时长无效")
                if event.is_set(): raise InterruptedError("云数字人素材导入已取消")
                archive = self._archive_cloud_dh_outputs(project_id, info) if any(
                    Path(path).is_file() for path in outputs.values()) else ""
                os.replace(staged, target)
                Path(outputs["video"]).unlink(missing_ok=True)
            finally:
                staged.unlink(missing_ok=True)
            info.pop("last_task", None)
            if archive: info["last_archive"] = archive
            info = self._save_cloud_dh_project(project_id, info)
            return {"status": "success", "path": str(target), "project": self._attach_cloud_dh_previews(info)}
        except Exception as error:
            outcome = "cancelled" if isinstance(error, InterruptedError) else "failed"; failure = str(error)
            raise
        finally:
            self._end_cloud_dh_job(project_id, event, outcome, failure)

    def pick_cloud_dh_audio(self, data):
        project_id=(data or {}).get("project_id")
        try: return self._pick_cloud_dh_file(project_id, "audio", ("Audio (*.wav;*.mp3;*.m4a;*.aac)",))
        except Exception as error: return {"status": "error", "message": str(error)}

    def pick_cloud_dh_avatar(self, data):
        project_id=(data or {}).get("project_id")
        try: return self._pick_cloud_dh_file(project_id, "avatar", ("Images (*.png;*.jpg;*.jpeg;*.webp)",))
        except Exception as error: return {"status": "error", "message": str(error)}

    def generate_cloud_dh_avatar(self, data):
        from .cloud_dh_prompts import build_avatar_prompt
        from .runninghub_image import _generate_and_download_cancellable
        event = None; project_id = None; outcome = "succeeded"; failure = ""
        try:
            project_id = data["project_id"]
            event = self._begin_cloud_dh_job(project_id, "generate_avatar")
            info = self._load_cloud_dh_project(project_id)
            prompt = build_avatar_prompt(data.get("description") or data.get("avatar_prompt") or info.get("avatar_prompt", ""))
            outputs = self._get_cloud_dh_output_paths(project_id); output = Path(outputs["avatar"])
            staged = output.with_name(".数字人形象.pending.png"); staged.unlink(missing_ok=True)
            try:
                _generate_and_download_cancellable(
                    api_key=self._resolve_cloud_dh_api_key(data), prompt=prompt, dest=staged,
                    aspect_ratio="9:16", resolution=data.get("resolution", "2k"), quality=data.get("quality", "low"),
                    poll_interval=int(data.get("poll_interval", 5)), poll_timeout=int(data.get("poll_timeout", 900)),
                    cancel_check=event.is_set)
                from PIL import Image
                with Image.open(staged) as image:
                    image.verify()
                    if image.width < 64 or image.height < 64: raise ValueError("数字人形象尺寸过小")
                if event.is_set(): raise InterruptedError("云数字人形象生成已取消")
                archive = self._archive_cloud_dh_outputs(project_id, info) if any(
                    Path(path).is_file() for path in outputs.values()) else ""
                os.replace(staged, output)
                # A video generated from the previous avatar must not appear as
                # the result for the newly selected avatar.
                Path(outputs["video"]).unlink(missing_ok=True)
            finally:
                staged.unlink(missing_ok=True)
            info["avatar_prompt"] = prompt
            info.pop("last_task", None)
            if archive: info["last_archive"] = archive
            info = self._save_cloud_dh_project(project_id, info)
            return {"status": "success", "project": self._attach_cloud_dh_previews(info)}
        except Exception as error:
            status = "cancelled" if isinstance(error, InterruptedError) else "error"
            outcome = "cancelled" if status == "cancelled" else "failed"; failure = str(error)
            return {"status": status, "message": f"生成数字人形象失败: {error}"}
        finally:
            if event is not None: self._end_cloud_dh_job(project_id, event, outcome, failure)

    def generate_cloud_dh_video(self, data):
        from .runninghub_talk import _generate_talk_video_cancellable
        cancel_event = None; project_id = None; outcome = "succeeded"; failure = ""
        try:
            project_id = data["project_id"]
            cancel_event = self._begin_cloud_dh_job(project_id, "generate_video")
            info = self._load_cloud_dh_project(project_id)
            outputs = self._get_cloud_dh_output_paths(project_id)
            if not Path(outputs["avatar"]).is_file(): raise FileNotFoundError("请先生成或选择数字人形象")
            if not Path(outputs["audio"]).is_file(): raise FileNotFoundError("请先选择口播音频")
            target = Path(outputs["video"])
            staged = target.with_name(".数字人口播.pending.mp4")
            staged.unlink(missing_ok=True)
            try:
                result = _generate_talk_video_cancellable(
                    api_key=self._resolve_cloud_dh_api_key(data), image_path=outputs["avatar"],
                    audio_path=outputs["audio"], dest=staged,
                    poll_interval=int(data.get("poll_interval", 10)),
                    poll_timeout=int(data.get("poll_timeout", 2400)), cancel_check=cancel_event.is_set)
                if cancel_event.is_set(): raise InterruptedError("云数字人生成已取消")
                archive = self._archive_cloud_dh_outputs(project_id, info) if target.is_file() else ""
                os.replace(staged, target)
            finally:
                staged.unlink(missing_ok=True)
            result["video_path"] = str(target)
            info["last_task"] = result
            if archive: info["last_archive"] = archive
            info = self._save_cloud_dh_project(project_id, info)
            return {"status": "success", "result": result, "project": self._attach_cloud_dh_previews(info)}
        except Exception as error:
            status = "cancelled" if isinstance(error, InterruptedError) else "error"
            outcome = "cancelled" if status == "cancelled" else "failed"; failure = str(error)
            return {"status": status, "message": f"生成数字人口播失败: {error}"}
        finally:
            if cancel_event is not None:
                self._end_cloud_dh_job(project_id, cancel_event, outcome, failure)

    def _cloud_dh_job_state(self):
        if not hasattr(self, "_cloud_dh_generation_lock"):
            self._cloud_dh_generation_lock = RLock(); self._cloud_dh_cancel_events = {}
        return self._cloud_dh_generation_lock, self._cloud_dh_cancel_events

    def _begin_cloud_dh_job(self, project_id, operation="generate_video"):
        lock, jobs = self._cloud_dh_job_state()
        with lock:
            if project_id in jobs: raise RuntimeError("该云数字人项目正在生成或更新素材")
            event = Event(); jobs[project_id] = event
        try:
            from datetime import datetime
            info = self._load_cloud_dh_project(project_id)
            info["generation_task"] = {"status":"running", "operation":operation,
                                       "started_at":datetime.now().isoformat(timespec="seconds"),
                                       "ended_at":None, "error":""}
            self._save_cloud_dh_project(project_id, info)
            return event
        except Exception:
            with lock:
                if jobs.get(project_id) is event: jobs.pop(project_id, None)
            raise

    def _end_cloud_dh_job(self, project_id, event, status="succeeded", error=""):
        lock, jobs = self._cloud_dh_job_state()
        with lock:
            if jobs.get(project_id) is event: jobs.pop(project_id, None)
        try:
            from datetime import datetime
            info = self._load_cloud_dh_project(project_id); task = info.get("generation_task") or {}
            info["generation_task"] = {**task, "status":status,
                                       "ended_at":datetime.now().isoformat(timespec="seconds"),
                                       "error":str(error or "")}
            self._save_cloud_dh_project(project_id, info)
        except Exception: pass

    def cancel_cloud_dh_generation(self, project_id):
        if not isinstance(project_id, str) or not project_id.strip():
            return {"status": "error", "message": "云数字人项目 ID 无效"}
        lock, jobs = self._cloud_dh_job_state()
        with lock:
            event = jobs.get(project_id)
            if event is None: return {"status": "idle", "message": "当前没有云数字人生成任务"}
            event.set()
        return {"status": "cancel_requested", "project_id": project_id}

    def probe_voice_clone_audio(self, audio_path, clone_mode="local"):
        try:
            minimum, maximum = self._voice_clone_duration_limits(clone_mode)
            duration = self._get_audio_duration(audio_path)
        except Exception as error:
            return {"status": "error", "message": str(error)}
        return {
            "status": "success", "duration": duration,
            "min_seconds": minimum, "max_seconds": maximum,
            "valid": minimum <= duration <= maximum,
        }

    def _clone_cosyvoice_from_local_audio(
        self, audio_path, config, token, server_url, label="阿里云语音克隆",
    ):
        duration = self._get_audio_duration(audio_path)
        minimum, maximum = self._voice_clone_duration_limits("cosyvoice")
        if not minimum <= duration <= maximum:
            raise ValueError(f"{label}：参考音频时长须为 {minimum}–{maximum} 秒")
        audio_url = self._upload_cosyvoice_reference_audio(audio_path, token, server_url)
        return clone_voice_cosyvoice(audio_url=audio_url, duration=duration, api_config=config)

    def start_voice_clone_minimax(self, audio_path, voice_name, minimax_config=None):
        token = str(self.config.get("token") or "").strip()
        if not token:
            return {"status": "error", "message": "请先登录后再进行 Minimax 声音克隆"}
        server_url = str(self.config.get("server_url") or "").strip()
        config = minimax_config or self.config.get("minimax_voice_config") or {}
        if not server_url or not voice_name.strip() or not str(config.get("api_key") or "").strip():
            return {"status": "error", "message": "请填写服务地址、声音名称和 Minimax API Key"}
        try:
            duration = self._get_audio_duration(audio_path)
            minimum, maximum = self._voice_clone_duration_limits("minimax")
            if not minimum <= duration <= maximum:
                raise ValueError(f"参考音频时长须为 {minimum}–{maximum} 秒")
            metadata = clone_voice_minimax(audio_path=audio_path, duration=duration, api_config=config)
            voice = self._save_cloud_voice_record(
                "minimax", "Minimax", voice_name, metadata, token, server_url, audio_path=audio_path,
            )
        except Exception as error:
            return {"status": "error", "message": f"Minimax 克隆声音失败: {error}"}
        return {"status": "success", "voice": voice}

    def start_voice_clone_cosyvoice(
        self, audio_path, voice_name, cosyvoice_config=None, auto_audio_optimize=False,
    ):
        token = str(self.config.get("token") or "").strip()
        if not token:
            return {"status": "error", "message": "请先登录后再进行阿里云声音克隆"}
        server_url = str(self.config.get("server_url") or "").strip()
        config = cosyvoice_config or self.config.get("cosyvoice_voice_config") or {}
        if not server_url or not voice_name.strip() or not str(config.get("api_key") or "").strip():
            return {"status": "error", "message": "请填写服务地址、声音名称和阿里云 API Key"}
        try:
            metadata = self._clone_cosyvoice_from_local_audio(audio_path, config, token, server_url)
            if auto_audio_optimize:
                with TemporaryDirectory(prefix="cosyvoice_optimize_") as directory:
                    optimized = self._build_cosyvoice_optimized_audio(metadata, dict(config, cache_dir=directory))
                    metadata = self._clone_cosyvoice_from_local_audio(
                        optimized, config, token, server_url, label="阿里云优化二次克隆",
                    )
            voice = self._save_cosyvoice_record(voice_name, metadata, token, server_url)
        except Exception as error:
            return {"status": "error", "message": f"阿里云克隆声音失败: {error}"}
        return {"status": "success", "voice": voice}

    def start_voice_clone_local(
        self, audio_path, voice_name, voice_id, asr_lang="zh", auto_audio_optimize=False,
    ):
        from .voice_clone_infer_api import clone_voice_local

        target_id = str(voice_id or "").strip()
        if not target_id:
            return {"status": "error", "message": "声音 ID 不能为空"}
        output_dir = Path(self.runtime_dir) / "assets" / "characters" / "voices"
        try:
            exp_dir = clone_voice_local(
                audio_path, target_id, str(output_dir), self._get_asr_weight_path(), asr_lang
            )
            if auto_audio_optimize:
                from .local_voice import synthesize_local_audio

                voice_config = dict(self.config)
                voice_config.setdefault("voice_base_dir", str(output_dir))
                voice_config.setdefault(
                    "models_base_path",
                    str(Path(self.runtime_dir) / "assets" / "pretrained_models"),
                )
                with TemporaryDirectory(prefix="local_voice_optimize_") as directory:
                    generated = synthesize_local_audio(
                        voice_config, target_id, VOICE_OPTIMIZE_SAMPLE_TEXT, 1.0, "v1"
                    )
                    optimized = self._clone_manager._export_audio_within_seconds(
                        generated, Path(directory) / "optimized.wav",
                        VOICE_OPTIMIZE_MAX_SECONDS, sample_rate=VOICE_OPTIMIZE_SAMPLE_RATE,
                    )
                    exp_dir = clone_voice_local(
                        optimized, target_id, str(output_dir),
                        self._get_asr_weight_path(), asr_lang,
                    )
        except Exception as error:
            return {"status": "error", "message": f"本地声音克隆失败: {error}"}
        return {
            "status": "success", "voice_id": target_id, "voice_name": voice_name,
            "voice_dir": exp_dir, "auto_audio_optimize": bool(auto_audio_optimize),
        }

    def _build_cosyvoice_optimized_audio(self, first_metadata, config):
        directory = Path(config.get("cache_dir") or Path(self.runtime_dir) / "temp" / "cosyvoice_optimize")
        directory.mkdir(parents=True,exist_ok=True)
        voice_id = first_metadata.get("cosyvoice_voice_id") or first_metadata.get("voice_id")
        if not voice_id:
            raise ValueError("阿里云首轮克隆未返回音色 ID，无法做音频优化")
        audio = synthesize_speech_cosyvoice(
            text=VOICE_OPTIMIZE_SAMPLE_TEXT, voice_id=voice_id,
            cosyvoice_config=dict(config, cache_dir=directory), speed=1.0, use_cache=False,
            audio_format="WAV_24000HZ_MONO_16BIT",
        )
        return self._clone_manager._export_audio_within_seconds(
            audio, Path(directory) / "optimized.wav", VOICE_OPTIMIZE_MAX_SECONDS,
            sample_rate=VOICE_OPTIMIZE_SAMPLE_RATE,
        )

    @staticmethod
    def _save_cosyvoice_record(voice_name, metadata, token, server_url):
        return Api._save_cloud_voice_record("cosyvoice", "阿里云", voice_name, metadata, token, server_url)

    @staticmethod
    def _save_cloud_voice_record(provider, label, voice_name, metadata, token, server_url, *, audio_path=None):
        import requests

        from contextlib import ExitStack

        with ExitStack() as files:
            request_options = {}
            if audio_path is not None:
                path = Path(audio_path)
                source = files.enter_context(path.open("rb"))
                request_options["files"] = {
                    "reference_audio": (path.name, source, "application/octet-stream"),
                }
            response = requests.post(
                server_url.rstrip("/") + f"/voice/create_{provider}",
                headers={"token": token},
                data={
                    "voice_name": voice_name,
                    f"{provider}_metadata": json.dumps(metadata, ensure_ascii=False),
                },
                timeout=60,
                **request_options,
            )
        if response.status_code != 200:
            raise RuntimeError(f"保存{label}声音记录失败: {response.text}")
        return response.json()

    def _upload_cosyvoice_reference_audio(self, audio_path, token, server_url):
        from urllib.parse import urljoin

        import requests

        path = Path(audio_path)
        endpoint = server_url.rstrip("/") + "/voice/upload_reference_audio"
        with path.open("rb") as source:
            response = requests.post(
                endpoint,
                headers={"token": token},
                files={"reference_audio": (path.name, source, "application/octet-stream")},
                timeout=60,
            )
        if response.status_code != 200:
            raise RuntimeError(f"上传阿里云参考音频失败: {response.text}")
        url = str(response.json().get("url") or "").strip()
        if not url:
            raise RuntimeError("上传阿里云参考音频失败: 未返回 URL")
        return urljoin(server_url.rstrip("/") + "/", url)

    def prepare_record_announcement(self, data=None):
        manager = self._record_live_manager
        if not manager.is_broadcasting:
            return {"status": "error", "message": "请先开启转播/录播直播"}
        config = (data or {}).get("config")
        if not config:
            return {"status": "error", "message": "录播配置为空"}
        try:
            video_config = self._extract_local_media_video_config(config)
            return manager.prepare_announcement(video_config=video_config)
        except Exception as error:
            return {"status": "error", "message": str(error)}

    def _extract_local_media_video_config(self, config_data):
        return {
            "voice_id": config_data.get("voice_id"),
            "voice_infer_version": config_data.get("voice_infer_version", "v1"),
            "voice_speed": config_data.get("voice_speed", 1.1),
            "audio_text": config_data.get("audio_text") or "{time}",
            "real_shot": config_data.get("real_shot") or {},
        }


def _main(runtime_dir=None):
    if runtime_dir is None:
        workspace_runtime = Path(__file__).resolve().parent.parent / "yunchuang_v122" / "_internal"
        runtime_dir = workspace_runtime if workspace_runtime.is_dir() else Path(__file__).resolve().parent
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    _initialize_environment(runtime_dir)
    ensure_high_performance(keep_alive=True)
    config = load_effective_config(runtime_dir, resolve_user_config_path())
    api = Api._create(runtime_dir, config)
    try:
        run_webview(api, config, runtime_dir)
    finally:
        api.shutdown()


def main():
    return _main()

def _start_srs(runtime_dir):
    return start_bundled_srs(runtime_dir)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Launch the recovered yunchuang_v122 WebView")
    parser.add_argument("runtime_dir", nargs="?", default=Path.cwd(), type=Path)
    options = parser.parse_args()
    sys.exit(_main(options.runtime_dir))
