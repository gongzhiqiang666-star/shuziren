"""Recovered helpers for the bundled virtual camera."""

import ntpath
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional


def _creationflags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0


def resolve_camera_dir() -> str:
    """Locate the camera assets beside the module or packaged executable."""
    module_root = Path(__file__).resolve().parent.parent
    executable_root = Path(sys.executable).resolve().parent
    assets = Path("assets", "plugin", "camera")
    candidates = (
        module_root / assets,
        executable_root / "_internal" / assets,
        executable_root / assets,
        module_root / "yunchuang_v122" / "_internal" / assets,
    )
    for candidate in candidates:
        if candidate.is_dir():
            return os.fspath(candidate)
    return os.fspath(candidates[0])


def _reg_get(path: str, value_name: str = "") -> Optional[str]:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except OSError:
        return None
    return value if isinstance(value, str) else None


def _reg_key_exists(path: str) -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path):
            return True
    except OSError:
        return False


OBS_CAMERA_CLSID = "{A3FCE0F5-3493-419F-958A-ABA1250EC20B}"
_VIDEO_INPUT_CATEGORY = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
_REGISTRY_CLASSES = (r"SOFTWARE\Classes", r"SOFTWARE\WOW6432Node\Classes")


def _obs_paths():
    return tuple(
        _reg_get(fr"{root}\CLSID\{OBS_CAMERA_CLSID}\InprocServer32")
        for root in _REGISTRY_CLASSES
    )


def _friendly_names():
    return tuple(
        _reg_get(fr"{root}\CLSID\{_VIDEO_INPUT_CATEGORY}\Instance\{OBS_CAMERA_CLSID}",
                 "FriendlyName")
        for root in _REGISTRY_CLASSES
    )


def is_virtual_cam_installed() -> bool:
    return bool(diagnose_virtual_cam().get("ok"))


HD_CAMERA_CLSID_64 = (
    "{5C2CD55C-92AD-4999-8666-912BD3E70010}",
    "{5C2CD55C-92AD-4999-8666-912BD3E70011}",
)
HD_CAMERA_CLSID_32 = (
    "{5C2CD55C-92AD-4999-8666-912BD3E70020}",
    "{5C2CD55C-92AD-4999-8666-912BD3E70021}",
)


def _hd_camera_present() -> bool:
    for root, clsids in zip(_REGISTRY_CLASSES, (HD_CAMERA_CLSID_64, HD_CAMERA_CLSID_32)):
        if any(_reg_key_exists(fr"{root}\CLSID\{clsid}") for clsid in clsids):
            return True
    for root, clsids in zip(_REGISTRY_CLASSES, (HD_CAMERA_CLSID_64, HD_CAMERA_CLSID_32)):
        for clsid in clsids:
            instance = fr"{root}\CLSID\{_VIDEO_INPUT_CATEGORY}\Instance\{clsid}"
            if "HD Camera" in (_reg_get(instance, "FriendlyName") or ""):
                return True
    return False


def diagnose_virtual_cam(camera_dir: Optional[str] = None) -> dict:
    """Report camera registration and bundled assets without changing them."""
    directory = Path(camera_dir if camera_dir is not None else resolve_camera_dir()).resolve()
    dll_paths = tuple(directory / f"obs-virtualcam-module{arch}.dll" for arch in (64, 32))
    issues = []
    if not all(dll.is_file() for dll in dll_paths):
        issues.append("找不到虚拟摄像头 DLL（assets/plugin/camera）。")
    obs_paths = (None, None)
    friendly_names = (None, None)
    hd_present = False
    if sys.platform == "win32":
        obs_paths = _obs_paths()
        friendly_names = _friendly_names()
        for arch, path, dll, name in zip((64, 32), obs_paths, dll_paths, friendly_names):
            if ntpath.normcase(ntpath.normpath(path or "")) != ntpath.normcase(ntpath.normpath(str(dll))):
                issues.append(f"{arch}位 OBS 虚拟摄像头未指向当前客户端 DLL")
            if name != "C920":
                issues.append(f"{arch}位显示名不是 C920")
        hd_present = _hd_camera_present()
        if hd_present:
            issues.append("检测到遗留 HD Camera（Unity Capture）")
    else:
        issues.append("虚拟摄像头注册诊断需要 Windows")
    return {
        "ok": not issues,
        "issues": issues,
        "camera_dir": os.fspath(directory),
        "dll64": os.fspath(dll_paths[0]),
        "dll32": os.fspath(dll_paths[1]),
        "path64": obs_paths[0],
        "path32": obs_paths[1],
        "name64": friendly_names[0],
        "name32": friendly_names[1],
        "hd_camera_present": hd_present,
    }


def _escape_ps(value: str) -> str:
    """Escape text for insertion inside a PowerShell single-quoted string."""
    return value.replace("'", "''")


def _write_repair_script(camera_dir: str, script_path: str) -> None:
    directory = Path(camera_dir).resolve()
    dlls = [directory / f"obs-virtualcam-module{arch}.dll" for arch in (64, 32)]
    if not all(dll.is_file() for dll in dlls):
        raise FileNotFoundError("找不到虚拟摄像头 DLL（assets/plugin/camera）。")
    lines = ["$ErrorActionPreference = 'Stop'"]
    if sys.platform == "win32":
        for legacy_dll in _collect_hd_dlls():
            system_dir = "SysWOW64" if legacy_dll.lower().endswith("32.dll") else "System32"
            lines.extend([
                fr"$reg = Join-Path $env:SystemRoot '{system_dir}\regsvr32.exe'",
                f"& $reg /u /s '{_escape_ps(legacy_dll)}' | Out-Null",
            ])
        for root, clsids in zip(_REGISTRY_CLASSES, (HD_CAMERA_CLSID_64, HD_CAMERA_CLSID_32)):
            for clsid in clsids:
                key = fr"{root}\CLSID\{clsid}"
                lines.append(
                    fr"if (Test-Path -LiteralPath 'HKLM:\{key}') {{ "
                    fr"reg.exe delete 'HKLM\{key}' /f | Out-Null }}"
                )
    for arch, system_dir, root, dll in zip((64, 32), ("System32", "SysWOW64"), _REGISTRY_CLASSES, dlls):
        instance = fr"HKLM:\{root}\CLSID\{_VIDEO_INPUT_CATEGORY}\Instance\{OBS_CAMERA_CLSID}"
        lines.extend([
            fr"$reg = Join-Path $env:SystemRoot '{system_dir}\regsvr32.exe'",
            f"$dll = '{_escape_ps(str(dll))}'",
            "& $reg /u /s $dll | Out-Null",
            "& $reg /i /s $dll",
            f"if ($LASTEXITCODE -ne 0) {{ throw '注册{arch}位虚拟摄像头失败' }}",
            f"Set-ItemProperty -LiteralPath '{instance}' -Name FriendlyName -Value 'C920'",
            f"$name = (Get-ItemProperty -LiteralPath '{instance}' -Name FriendlyName).FriendlyName",
            f"if ($name -cne 'C920') {{ throw \"{arch}位显示名仍为 $name\" }}",
        ])
    Path(script_path).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def _run_elevated_script_file(script_path: str) -> None:
    if sys.platform != "win32":
        raise OSError("虚拟摄像头修复需要 Windows")
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    script = _escape_ps(str(Path(script_path).resolve()))
    command = (
        "$ErrorActionPreference = 'Stop'; "
        f"$args = '-NoProfile -ExecutionPolicy Bypass -File \"{script}\"'; "
        f"$p = Start-Process -FilePath '{_escape_ps(str(powershell))}' "
        "-ArgumentList $args -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
    )
    subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", command], check=True)


def repair_virtual_cam(camera_dir: Optional[str] = None) -> dict:
    """Register the bundled DLLs and verify the resulting configuration."""
    if sys.platform != "win32":
        raise OSError("虚拟摄像头修复需要 Windows")
    directory = resolve_camera_dir() if camera_dir is None else camera_dir
    with TemporaryDirectory(prefix="virtual-cam-") as temp_dir:
        script = os.fspath(Path(temp_dir) / "repair.ps1")
        _write_repair_script(directory, script)
        try:
            _run_elevated_script_file(script)
        except subprocess.CalledProcessError as error:
            raise RuntimeError("用户取消授权或虚拟摄像头安装失败") from error
    report = diagnose_virtual_cam(directory)
    if not report["ok"]:
        raise RuntimeError("虚拟摄像头修复后仍异常: " + "，".join(report["issues"]))
    return report


def ensure_virtual_cam(force: bool = False) -> dict:
    """Check the device before playback and repair its registration when needed."""
    report = diagnose_virtual_cam()
    if report["ok"] and not force:
        return report
    try:
        return repair_virtual_cam(report["camera_dir"])
    except (OSError, RuntimeError):
        if sys.platform != "win32":
            raise
        current = diagnose_virtual_cam(report["camera_dir"])
        path64 = current["path64"]
        if path64 and Path(path64).is_file():
            return current
        raise


def _collect_hd_dlls():
    """Collect existing DLLs referenced by the known Unity Capture classes."""
    paths = {}
    for root, clsids in zip(_REGISTRY_CLASSES, (HD_CAMERA_CLSID_64, HD_CAMERA_CLSID_32)):
        for clsid in clsids:
            path = _reg_get(fr"{root}\CLSID\{clsid}\InprocServer32")
            if path and Path(path).is_file():
                paths.setdefault(ntpath.normcase(ntpath.normpath(path)), path)
    return list(paths.values())
