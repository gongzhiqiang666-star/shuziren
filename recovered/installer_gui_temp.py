"""Recovered helpers from installer_gui_temp.py bytecode."""

import ctypes
import json
import os
import re
import subprocess
import sys

from .installer_text import TEXT


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_runtime_base_dir(base_dir):
    internal_dir = os.path.join(base_dir, "_internal")
    if os.path.isdir(internal_dir):
        return internal_dir
    return base_dir


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_as_admin():
    if is_admin():
        return True
    raw_args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    params = " ".join(f'"{arg}"' if " " in arg else arg for arg in raw_args)
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        return True
    except Exception as exc:
        from tkinter import messagebox

        messagebox.showerror(L("elevate_failed"), L("elevate_failed_msg", exc=exc))
        return False


CAMERA_CLSID = "{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"
VIETNAM_ADMIN_ID = 21


def is_vietnam_customer_pack():
    candidates = (
        get_runtime_base_dir(get_app_base_dir()),
        os.path.dirname(os.path.abspath(__file__)),
    )
    for base_dir in candidates:
        id_path = os.path.join(base_dir, "assets", "web", "id.txt")
        try:
            if os.path.exists(id_path):
                with open(id_path, "r", encoding="utf-8") as file:
                    admin_id = file.read().strip()
                    if admin_id.isdigit() and int(admin_id) == VIETNAM_ADMIN_ID:
                        return True
        except Exception:
            continue
    return False


VIETNAM_PACK = is_vietnam_customer_pack()


def L(key, **kwargs):
    text = TEXT[key]["vi" if VIETNAM_PACK else "zh"]
    return text.format(**kwargs) if kwargs else text


TORCH_CHECKER_SCRIPT = '\nimport json\nimport torch\n\nresult = {\n    "cuda_available": False,\n    "device_name": None,\n    "total_vram_gb": 0,\n    "error": None\n}\n\ntry:\n    if torch.cuda.is_available():\n        result["cuda_available"] = True\n        device = torch.device("cuda:0")\n        result["device_name"] = torch.cuda.get_device_name(0)\n        _, total_mem = torch.cuda.mem_get_info(device)\n        result["total_vram_gb"] = round(total_mem / (1024 ** 3), 2)\n    else:\n        result["error"] = "CUDA not available."\nexcept Exception as e:\n    result["error"] = str(e)\n\nprint(json.dumps(result))\n'


class InstallerApp:
    def __init__(self, root):
        import tkinter as tk

        self.root = root
        root.title(L("window_title"))
        root.geometry("430x540")
        root.resizable(False, False)
        self.app_base_dir = get_app_base_dir()
        self.base_dir = get_runtime_base_dir(self.app_base_dir)
        self.plugin_dir = os.path.join(self.base_dir, "assets", "plugin")

        tk.Label(root, text=L("main_title"), font=("Segoe UI", 14, "bold")).pack(pady=(16, 8))
        status = tk.Frame(root)
        status.pack(pady=8, padx=18, fill=tk.X)
        self.mic_status_label = self._status_label(status, L("mic_checking"))
        self.cam_status_label = self._status_label(status, L("cam_checking"))
        self.chrome_status_label = self._status_label(status, L("chrome_checking"))
        self.webview_status_label = self._status_label(status, L("webview_checking"))
        self.gpu_status_label = self._status_label(status, L("gpu_checking"))
        self.path_status_label = self._status_label(status, L("path_checking"))

        buttons = tk.Frame(root)
        buttons.pack(pady=14, padx=48, fill=tk.X)
        for key, callback in (
            ("btn_install_mic", self.install_mic),
            ("btn_install_cam", self.install_cam),
            ("btn_install_chrome", self.install_chrome),
            ("btn_install_webview", self.install_webview),
            ("btn_install_dotnet9", self.install_dotnet_9),
            ("btn_install_dotnet8", self.install_dotnet_8),
            ("btn_disable_firewall", self.disable_firewall),
            ("btn_refresh", self.refresh_status),
        ):
            self._button(buttons, L(key), callback)
        tk.Label(root, text=L("hint"), fg="#666666", wraplength=360).pack(pady=(4, 0))
        self.refresh_status()

    def _status_label(self, parent, text):
        import tkinter as tk

        label = tk.Label(parent, text=text, anchor="w", justify=tk.LEFT)
        label.pack(fill=tk.X, pady=3)
        return label

    def _button(self, parent, text, command):
        import tkinter as tk

        tk.Button(parent, text=text, command=command).pack(pady=4, fill=tk.X)

    def _creationflags(self):
        return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    def _set_status(self, label, text, color):
        label.config(text=text, fg=color)

    def _escape_powershell(self, value):
        return str(value).replace("'", "''")

    def _run_elevated_process(self, file_path, args=None, wait=True):
        if os.path.basename(str(file_path)).lower() not in {"reg.exe", "netsh"}:
            file_path = os.path.abspath(file_path)
            if not os.path.exists(file_path):
                raise FileNotFoundError(L("file_missing", path=file_path))

        escaped_path = self._escape_powershell(file_path)
        escaped_args = ", ".join(f"'{self._escape_powershell(arg)}'" for arg in (args or []))
        command = f"Start-Process -FilePath '{escaped_path}'"
        if escaped_args:
            command += f" -ArgumentList @({escaped_args})"
        command += " -Verb RunAs"
        if wait:
            command += " -Wait"

        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            creationflags=self._creationflags(),
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(error or L("elevated_failed"))

    def check_virtual_mic(self):
        try:
            import sounddevice

            installed = any("CABLE Output" in device["name"] for device in sounddevice.query_devices())
            if installed:
                self._set_status(self.mic_status_label, L("mic_installed"), "green")
            else:
                self._set_status(self.mic_status_label, L("mic_missing"), "red")
        except Exception as exc:
            self._set_status(self.mic_status_label, L("mic_error", exc=exc), "orange")

    def check_virtual_cam(self):
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Classes\\CLSID\\{CAMERA_CLSID}"):
                self._set_status(self.cam_status_label, L("cam_installed"), "green")
        except FileNotFoundError:
            self._set_status(self.cam_status_label, L("cam_missing"), "red")
        except Exception as exc:
            self._set_status(self.cam_status_label, L("cam_error", exc=exc), "orange")

    def check_chrome(self):
        key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key):
                self._set_status(self.chrome_status_label, L("chrome_installed"), "green")
        except FileNotFoundError:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
                    self._set_status(self.chrome_status_label, L("chrome_installed"), "green")
            except FileNotFoundError:
                self._set_status(self.chrome_status_label, L("chrome_missing"), "red")
        except Exception as exc:
            self._set_status(self.chrome_status_label, L("chrome_error", exc=exc), "orange")

    def check_webview(self):
        base_paths = [
            r"C:\Program Files (x86)\Microsoft\EdgeWebView\Application",
            r"C:\Program Files\Microsoft\EdgeWebView\Application",
        ]
        try:
            for base_path in base_paths:
                if not os.path.exists(base_path):
                    continue
                for version in os.listdir(base_path):
                    runtime = os.path.join(base_path, version, "msedgewebview2.exe")
                    if os.path.exists(runtime):
                        self._set_status(self.webview_status_label, L("webview_installed"), "green")
                        return
            self._set_status(self.webview_status_label, L("webview_missing"), "red")
        except Exception as exc:
            self._set_status(self.webview_status_label, L("webview_error", exc=exc), "orange")

    def _runtime_python_candidates(self):
        candidates = [
            os.path.join(self.base_dir, "env", "python.exe"),
            os.path.join(self.base_dir, "env_50", "python.exe"),
        ]
        return [path for path in candidates if os.path.exists(path)]

    def check_path(self):
        path = self.app_base_dir
        issues = []
        if re.search(r"[\u4e00-\u9fa5]", path):
            issues.append(L("issue_chinese"))
        if any("." in part for part in path.split(os.sep) if ":" not in part):
            issues.append(L("issue_dot"))
        if not issues:
            self._set_status(self.path_status_label, L("path_ok"), "green")
            return

        issue_text = L("issue_joiner").join(issues)
        self._set_status(self.path_status_label, L("path_issue", issue_text=issue_text), "red")
        if not getattr(self, "_path_warning_shown", False):
            from tkinter import messagebox

            messagebox.showwarning(
                L("path_warning_title"),
                L("path_warning_body", issue_text=issue_text, path=path),
            )
            self._path_warning_shown = True

    def _plugin_path(self, *parts):
        return os.path.join(self.plugin_dir, *parts)

    def refresh_status(self):
        self.check_path()
        self.check_virtual_mic()
        self.check_virtual_cam()
        self.check_chrome()
        self.check_webview()
        self.check_gpu_and_vram()

    def check_gpu_and_vram(self, min_vram_gb=6):
        candidates = self._runtime_python_candidates()
        if not candidates:
            self._set_status(self.gpu_status_label, L("gpu_python_missing"), "red")
            return
        for executable in candidates:
            try:
                process = subprocess.run(
                    [executable, "-c", TORCH_CHECKER_SCRIPT],
                    capture_output=True, text=True, encoding="utf-8", check=True,
                    creationflags=self._creationflags(),
                )
                result = json.loads((process.stdout or "").strip() or "{}")
                if result.get("error"):
                    continue
                device_name = result.get("device_name", "N/A")
                vram = float(result.get("total_vram_gb", 0))
                if not result.get("cuda_available"):
                    self._set_status(self.gpu_status_label, L("gpu_cuda_unavailable"), "red")
                    return
                if vram < min_vram_gb:
                    self._set_status(
                        self.gpu_status_label,
                        L("gpu_vram_low", min_vram_gb=min_vram_gb, vram=vram),
                        "red",
                    )
                    return
                series = re.search(r"(10|20|30|40|50)\d{2}", device_name)
                if series and series.group(1) == "50":
                    self._set_status(
                        self.gpu_status_label, L("gpu_series50", device_name=device_name, vram=vram),
                        "orange",
                    )
                    return
                self._set_status(
                    self.gpu_status_label, L("gpu_ok", device_name=device_name, vram=vram),
                    "green",
                )
                return
            except Exception:
                continue
        self._set_status(self.gpu_status_label, L("gpu_failed"), "red")

    def _launch_installer(self, filename, tip_key, done_key):
        from tkinter import messagebox

        path = self._plugin_path(filename)
        messagebox.showinfo(L("tip"), L(tip_key))
        try:
            self._run_elevated_process(path, wait=False)
            messagebox.showinfo(L("success"), L(done_key))
        except Exception as exc:
            messagebox.showerror(L("launch_failed"), str(exc))

    def install_chrome(self):
        self._launch_installer("ChromeSetup.exe", "install_chrome_tip", "install_chrome_done")

    def install_webview(self):
        self._launch_installer(
            "MicrosoftEdgeWebview2Setup.exe", "install_webview_tip", "install_webview_done"
        )

    def install_dotnet_9(self):
        self._launch_installer(
            "windowsdesktop-runtime-9.0.6-win-x64.exe", "install_dotnet_tip", "install_dotnet9_done"
        )

    def install_dotnet_8(self):
        self._launch_installer(
            "windowsdesktop-runtime-8.0.17-win-x64.exe", "install_dotnet_tip", "install_dotnet8_done"
        )

    def install_mic(self):
        from tkinter import messagebox

        path = self._plugin_path("VBCABLE_Driver_Pack45", "VBCABLE_Setup_x64.exe")
        try:
            messagebox.showinfo(L("install_tip_title"), L("install_mic_tip"))
            self._run_elevated_process(path)
            messagebox.showinfo(L("done"), L("install_mic_done"))
        except Exception as exc:
            messagebox.showerror(L("install_failed"), str(exc))
        finally:
            self.check_virtual_mic()

    def install_cam(self):
        from tkinter import messagebox

        folder = self._plugin_path("camera")
        dll32 = os.path.join(folder, "obs-virtualcam-module32.dll")
        dll64 = os.path.join(folder, "obs-virtualcam-module64.dll")
        try:
            if not os.path.exists(dll32):
                raise FileNotFoundError(L("dll32_missing", path=dll32))
            if not os.path.exists(dll64):
                raise FileNotFoundError(L("dll64_missing", path=dll64))
            messagebox.showinfo(L("tip"), L("install_cam_tip"))
            windows = os.environ.get("SystemRoot", r"C:\Windows")
            reg32 = os.path.join(windows, "SysWOW64", "regsvr32.exe")
            reg64 = os.path.join(windows, "System32", "regsvr32.exe")
            self._run_elevated_process(
                reg32 if os.path.exists(reg32) else "regsvr32.exe", ["/s", "/i", dll32]
            )
            self._run_elevated_process(
                reg64 if os.path.exists(reg64) else "regsvr32.exe", ["/s", "/i", dll64]
            )
            key = (
                "HKLM\\SOFTWARE\\Classes\\CLSID\\"
                "{860BB310-5D01-11d0-BD3B-00A0C911CE86}\\Instance\\"
                + CAMERA_CLSID
            )
            self._run_elevated_process(
                "reg.exe", ["add", key, "/v", "FriendlyName", "/t", "REG_SZ", "/d", "C920", "/f"]
            )
            messagebox.showinfo(L("success"), L("install_cam_done"))
        except Exception as exc:
            messagebox.showerror(L("install_failed"), str(exc))
        finally:
            self.check_virtual_cam()

    def disable_firewall(self):
        from tkinter import messagebox

        try:
            messagebox.showinfo(L("tip"), L("firewall_tip"))
            self._run_elevated_process(
                "netsh", ["advfirewall", "set", "allprofiles", "state", "off"]
            )
            messagebox.showinfo(L("success"), L("firewall_done"))
        except Exception as exc:
            messagebox.showerror(L("operation_failed"), str(exc))


def main():
    import tkinter as tk

    if not is_admin():
        if run_as_admin():
            sys.exit(0)
        sys.exit(1)
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
