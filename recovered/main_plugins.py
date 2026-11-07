"""Recovered plugin checks from the main extension."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .virtual_cam import _escape_ps, diagnose_virtual_cam, ensure_virtual_cam


class PluginInstallerService:
    def __init__(self, base_dir=None):
        self.base_dir = os.fspath(base_dir) if base_dir is not None else os.getcwd()
        self.plugin_dir = os.path.join(self.base_dir, "assets", "plugin")

    def _success_item(self, key, title, detail, installable=False, action_text="安装"):
        return {
            "key": key,
            "title": title,
            "detail": detail,
            "installed": True,
            "status_type": "success",
            "status_text": "已安装" if installable else "正常",
            "installable": bool(installable),
            "action_text": action_text,
        }

    def _warning_item(self, key, title, detail, installable=False, action_text="安装"):
        return {
            "key": key, "title": title, "detail": detail,
            "installed": False, "status_type": "warning", "status_text": "待处理",
            "installable": bool(installable), "action_text": action_text,
        }

    def _error_item(self, key, title, detail, installable=False, action_text="安装"):
        return {
            "key": key, "title": title, "detail": detail,
            "installed": False, "status_type": "danger",
            "status_text": "未安装" if installable else "异常",
            "installable": bool(installable), "action_text": action_text,
        }

    def _check_virtual_cam(self):
        try:
            report = diagnose_virtual_cam()
        except Exception as error:
            return self._warning_item("virtual_cam", "虚拟摄像头", f"检测失败: {error}")
        if report.get("ok"):
            return self._success_item(
                "virtual_cam", "虚拟摄像头", "已安装 C920，且驱动路径正常。",
                installable=True, action_text="修复",
            )
        detail = "；".join(report.get("issues") or []) or "虚拟摄像头状态异常。"
        return self._error_item(
            "virtual_cam", "虚拟摄像头", detail, installable=True, action_text="修复",
        )

    def _install_virtual_cam(self):
        ensure_virtual_cam(force=True)
        return "虚拟摄像头已安装并修复为 C920。"

    def _check_virtual_mic(self):
        key, title = "virtual_mic", "虚拟麦克风"
        try:
            import sounddevice

            if any("CABLE Output" in device["name"] for device in sounddevice.query_devices()):
                return self._success_item(key, title, "VB-CABLE 已安装，可用于音频回路。", True)
        except Exception as error:
            return self._warning_item(key, title, f"检测失败: {error}")
        return self._error_item(key, title, "未检测到 VB-CABLE。", True)

    def _install_virtual_mic(self):
        installer = os.path.join(self.plugin_dir, "VBCABLE_Driver_Pack45", "VBCABLE_Setup_x64.exe")
        self._run_elevated_process(installer)
        return "虚拟麦克风安装程序已完成。"

    def _check_webview(self):
        key, title = "webview2", "WebView2 Runtime"
        try:
            for root in (r"C:\Program Files\Microsoft\EdgeWebView\Application",
                         r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application"):
                if os.path.exists(root):
                    for version in os.listdir(root):
                        if os.path.exists(os.path.join(root, version, "msedgewebview2.exe")):
                            return self._success_item(key, title, "WebView2 Runtime 已安装。", True)
        except Exception as error:
            return self._warning_item(key, title, f"检测失败: {error}")
        return self._error_item(key, title, "未检测到 WebView2 Runtime。", True)

    def _probe_gpu(self):
        base = Path(self.base_dir)
        for root in (base, base / "_internal", base / "packed", base / "packed" / "_internal"):
            interpreter = root / "env" / "python.exe"
            if interpreter.is_file():
                break
        else:
            raise FileNotFoundError("未找到客户端自带 Python 运行时。")
        script = Path(__file__).with_name("gpu_probe.py").read_text(encoding="utf-8")
        result = subprocess.run(
            [str(interpreter), "-c", script],
            capture_output=True, text=True, encoding="utf-8", check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return json.loads(result.stdout)

    def _check_gpu_and_vram(self, min_vram_gb=6):
        key, title = "gpu", "显卡与显存"
        try:
            try:
                result = self._probe_gpu()
            except FileNotFoundError as error:
                return self._warning_item(key, title, str(error))
            if not result.get("cuda_available"):
                return self._error_item(key, title, "未检测到可用 CUDA 环境。")
            name = result["device_name"]
            vram = result["total_vram_gb"]
            if vram < min_vram_gb:
                return self._warning_item(
                    key, title, f"{name} 显存 {vram}GB，建议至少 {min_vram_gb}GB。",
                )
            if re.search(r"50\d{2}", name):
                return self._warning_item(key, title, f"{name} ({vram}GB)，50 系需确认驱动与环境兼容。")
            return self._success_item(key, title, f"{name} ({vram}GB)，环境可用。")
        except Exception as error:
            return self._warning_item(key, title, f"检测失败: {error}")

    def _check_path(self):
        issues = []
        if re.search(r"[\u4e00-\u9fa5]", self.base_dir):
            issues.append("中文")
        if any("." in part and ":" not in part for part in self.base_dir.split(os.sep)):
            issues.append("点号")
        if issues:
            detail = "当前路径包含" + "、".join(issues) + "，可能影响模型或插件加载。"
            return self._warning_item("path", "程序路径", detail)
        return self._success_item("path", "程序路径", "当前路径合规。")

    def _get_dotnet_items(self):
        detail = "如需使用弹幕捕获，请至少安装一次对应的 .NET Desktop Runtime。安装完成后一般无需重复安装。"
        return [
            {
                "key": f"dotnet_{major}", "title": f".NET {major}", "detail": detail,
                "installed": False, "status_type": "warning", "status_text": "按需安装",
                "installable": True, "action_text": "安装",
            }
            for major in (8, 9)
        ]

    def get_statuses(self):
        return {"status": "success", "items": [self._check_virtual_mic(), self._check_virtual_cam(), *self._get_dotnet_items(), self._check_webview(), self._check_gpu_and_vram(), self._check_path()]}

    def _run_elevated_process(self, file_path, args=None):
        if sys.platform != "win32":
            raise OSError("插件安装需要 Windows")
        file_path = os.path.abspath(file_path)
        if not os.path.isfile(file_path):
            raise FileNotFoundError(file_path)
        command = f"$ErrorActionPreference = 'Stop'; $p = Start-Process -FilePath '{_escape_ps(file_path)}'"
        if args:
            arguments = _escape_ps(subprocess.list2cmdline(args))
            command += f" -ArgumentList '{arguments}'"
        command += " -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], check=True)

    def _install_webview(self):
        installer = os.path.join(self.plugin_dir, "MicrosoftEdgeWebview2Setup.exe")
        self._run_elevated_process(installer)
        return "WebView2 Runtime 安装完成。"

    def install(self, item_key):
        handlers = {
            "virtual_mic": "_install_virtual_mic",
            "virtual_cam": "_install_virtual_cam",
            "dotnet_9": "_install_dotnet_9",
            "dotnet_8": "_install_dotnet_8",
            "webview2": "_install_webview",
        }
        handler = handlers.get(item_key)
        if handler is None:
            return {"status": "error", "message": f"不支持的安装项: {item_key}"}
        try:
            message = getattr(self, handler)()
            items = self.get_statuses().get("items", [])
        except Exception as error:
            return {"status": "error", "message": str(error)}
        return {"status": "success", "message": message, "items": items}

    def _install_dotnet_8(self):
        installer = os.path.join(self.plugin_dir, "windowsdesktop-runtime-8.0.17-win-x64.exe")
        self._run_elevated_process(installer)
        return ".NET 8 Desktop Runtime 安装完成。"

    def _install_dotnet_9(self):
        installer = os.path.join(self.plugin_dir, "windowsdesktop-runtime-9.0.6-win-x64.exe")
        self._run_elevated_process(installer)
        return ".NET 9 Desktop Runtime 安装完成。"


class PluginInstallerApi:
    """WebView entry points for the recovered plugin service."""

    def __init__(self, base_dir=None):
        self._plugin_installer = PluginInstallerService(base_dir)

    def get_plugin_install_status(self):
        return self._plugin_installer.get_statuses()

    def install_plugin_item(self, item_key: str):
        return self._plugin_installer.install(item_key)
