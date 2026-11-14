"""File digest routine recovered from update_temp.py bytecode."""

import hashlib
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from .update_text import TEXT


def file_sha256(file_path):
    digest = hashlib.sha256()
    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


CONFIG_RELATIVE_PATHS = {
    Path("_internal") / "config" / "config.yaml",
    Path("config") / "config.yaml",
}


def is_update_config_path(relative_path):
    return Path(relative_path) in CONFIG_RELATIVE_PATHS


def version_number(value):
    if value in (None, ""):
        return 0
    return int(str(value).strip().lower().replace("v", ""))


def version_text(value):
    return f"v{version_number(value):03d}"


def get_runtime_base_dir():
    source = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(source).resolve().parent


def get_internal_base_dir(base_dir):
    base_path = Path(base_dir)
    internal_path = base_path / "_internal"
    if internal_path.exists():
        return internal_path
    return base_path


VIETNAM_ADMIN_ID = 21
LEGACY_UPDATE_URL = "http://111.230.31.15:5155/get_latest"


def _require_trusted_url(url, purpose):
    parsed = urlparse(str(url or "").strip())
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise ValueError(f"{purpose}必须使用 HTTPS（本机回环地址除外）")
    return parsed.geturl()


def _resolve_update_status_url(config):
    direct = config.get("update_url")
    environment = config.get("environment")
    current = (config.get("environments") or {}).get(environment, {})
    base = str(current.get("update_url") or direct or LEGACY_UPDATE_URL).rstrip("/")
    if not base.endswith("/get_latest"):
        base += "/get_latest"
    return _require_trusted_url(base, "更新检查地址")


def _validate_update_item(item):
    if not isinstance(item, dict):
        raise ValueError("更新元数据格式错误")
    _require_trusted_url(item.get("download_url"), "更新包地址")
    digest = str(item.get("sha256") or "").strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"更新 {item.get('version_text') or item.get('version')} 缺少有效的 SHA-256")


def is_vietnam_customer_pack():
    base_dir = get_runtime_base_dir()
    for candidate in (get_internal_base_dir(base_dir), base_dir):
        id_path = candidate / "assets" / "web" / "id.txt"
        try:
            if id_path.exists():
                admin_id = id_path.read_text(encoding="utf-8").strip()
                if admin_id.isdigit() and int(admin_id) == VIETNAM_ADMIN_ID:
                    return True
        except Exception:
            continue
    return False


def L(key, **kwargs):
    text = TEXT[key]["vi" if VIETNAM_PACK else "zh"]
    return text.format(**kwargs) if kwargs else text


VIETNAM_PACK = is_vietnam_customer_pack()


def get_update_status(runtime_dir, timeout=10):
    import requests
    import yaml

    config_path = Path(runtime_dir) / "config" / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(L("config_missing", path=config_path))

    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    local_version = version_number(config.get("version", "v000"))

    response = requests.get(_resolve_update_status_url(config), timeout=timeout)
    response.raise_for_status()
    versions = response.json()
    if not isinstance(versions, list):
        raise ValueError(L("bad_server_response"))

    pending = []
    latest_version = local_version
    for item in versions:
        if not isinstance(item, dict):
            continue
        current_version = version_number(item.get("version", 0))
        latest_version = max(latest_version, current_version)
        if current_version > local_version:
            update = dict(item)
            update["version"] = current_version
            update["version_text"] = version_text(current_version)
            pending.append(update)
    pending.sort(key=lambda update: update["version"])

    return {
        "status": "success",
        "local_version": version_text(local_version),
        "local_version_number": local_version,
        "latest_version": version_text(latest_version),
        "latest_version_number": latest_version,
        "has_update": bool(pending),
        "pending_updates": pending,
        "message": L("update_available" if pending else "already_latest"),
    }


def update_local_version(runtime_dir, new_version):
    import yaml

    config_path = runtime_dir / "config" / "config.yaml"
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    number = int(str(new_version).strip().lower().replace("v", ""))
    config["version"] = f"v{number:03d}"
    with config_path.open("w", encoding="utf-8") as file:
        yaml.dump(config, file, allow_unicode=True, sort_keys=False)


def run_update_flow(self):
    try:
        self.gui.set_status(L("checking"), 3)
        status = get_update_status(self.runtime_dir, timeout=15)
        if status.get("status") != "success":
            self.gui.finish(status.get("message", L("check_failed")), is_error=True)
            return
        updates = status.get("pending_updates", [])
        if not updates:
            self.gui.finish(L("already_latest_done"), auto_close_ms=1800)
            return

        for item in updates:
            _validate_update_item(item)
        self.kill_processes()
        total = len(updates)
        for index, item in enumerate(updates):
            version = item.get("version_text", f"v{item['version']:03d}")
            self.download_and_extract(item["download_url"], version, index, total, item.get("sha256"))
            self.update_files(version, index, total)
            self.update_local_version(item["version"])
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self._set_progress(index, total, 0.98, L("version_done", version=version))
        self.gui.finish(L("update_complete"), auto_close_ms=1800)
    except Exception as error:
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.zip_path.unlink(missing_ok=True)
        self.gui.finish(str(error), is_error=True)


UPDATER_SKIP_NAMES = {"一键更新系统.exe", "更新.exe", "cập nhật.exe"}


def _current_executable_name(self):
    source = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(source).name.lower()


def _set_progress(self, version_index, total_versions, inner_ratio, text):
    overall = (version_index + inner_ratio) / max(total_versions, 1) * 100
    self.gui.set_status(text, overall)


def _is_target_process(self, proc_info):
    if proc_info.get("pid") == os.getpid():
        return False
    name = (proc_info.get("name") or "").lower()
    exe_path = os.path.normcase(proc_info.get("exe") or "")
    cmdline = " ".join(proc_info.get("cmdline") or []).lower()
    base_dir = os.path.normcase(str(self.base_dir))
    if name in UPDATER_SKIP_NAMES or "update_temp" in name:
        return False
    if name == self._current_executable_name():
        return False
    if exe_path and os.path.dirname(exe_path) == base_dir:
        return True
    return base_dir in cmdline and ("start.py" in cmdline or "main.py" in cmdline)


def kill_processes(self):
    import time

    import psutil

    self.gui.set_status(L("closing_old"), 5)
    for process in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        try:
            if self._is_target_process(process.info):
                process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    time.sleep(1.2)


def _validated_zip_members(archive):
    members = []
    for info in archive.infolist():
        raw = info.filename.replace("\\", "/")
        path = Path(raw)
        mode = info.external_attr >> 16
        if (not raw or raw.startswith("/") or path.is_absolute() or path.drive or
                any(part in ("", ".", "..") for part in path.parts) or stat.S_ISLNK(mode)):
            raise ValueError(f"不安全的更新包路径: {info.filename}")
        members.append(info)
    return members


def _verify_download_digest(zip_path, expected_sha256, version_text):
    expected = str(expected_sha256 or "").strip().lower()
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError(f"更新 {version_text} 缺少有效的 SHA-256，已拒绝不可信更新包")
    actual = file_sha256(zip_path)
    if actual != expected:
        raise ValueError(f"更新 {version_text} SHA-256 校验失败")


def download_and_extract(self, download_url, version_text, version_index, total_versions, expected_sha256=None):
    import zipfile

    import requests

    self.gui.set_status(L("downloading", version=version_text), None)
    if self.temp_dir.exists():
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    if self.zip_path.exists():
        self.zip_path.unlink(missing_ok=True)

    with requests.get(download_url, stream=True, timeout=30) as response:
        response.raise_for_status()
        total_bytes = int(response.headers.get("content-length", 0))
        downloaded = 0
        with self.zip_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=524288):
                if not chunk:
                    continue
                file.write(chunk)
                downloaded += len(chunk)
                if total_bytes > 0:
                    ratio = 0.05 + downloaded / total_bytes * 0.45
                    self._set_progress(
                        version_index, total_versions, ratio,
                        L("downloading", version=version_text),
                    )

    _verify_download_digest(self.zip_path, expected_sha256, version_text)

    self._set_progress(
        version_index, total_versions, 0.55, L("extracting", version=version_text)
    )
    with zipfile.ZipFile(self.zip_path, "r") as archive:
        members = _validated_zip_members(archive)
        files = [info for info in members if not info.is_dir()]
        if not files:
            raise ValueError(L("empty_package", version=version_text))
        if not any(info.filename.replace("\\", "/").startswith("_internal/") for info in files):
            raise ValueError(L("bad_package", version=version_text))
        for info in members:
            archive.extract(info, self.temp_dir)
    self.zip_path.unlink(missing_ok=True)


def update_files(self, version_text, version_index, total_versions):
    source = self.temp_dir
    target = self.base_dir
    current_name = self._current_executable_name()
    items = list(source.glob("**/*"))
    if not any(item.is_file() for item in items):
        raise ValueError(L("no_files", version=version_text))
    total = max(len(items), 1)
    ordered = sorted(
        items,
        key=lambda item: (
            1 if item.is_file() else 0,
            str(item.relative_to(source)).replace("\\", "/").lower(),
        ),
    )
    backup_root = Path(tempfile.mkdtemp(prefix="update-backup-", dir=str(target)))
    replaced = []
    created = []
    staged_paths = []
    try:
        for index, item in enumerate(ordered, start=1):
            relative = item.relative_to(source)
            destination = target / relative
            if item.name.lower() == current_name:
                continue
            if item.is_file() and is_update_config_path(relative):
                continue
            if item.is_dir():
                destination.mkdir(exist_ok=True, parents=True)
            else:
                destination.parent.mkdir(exist_ok=True, parents=True)
                existed = destination.exists()
                backup = None
                if existed:
                    backup = backup_root / relative
                    backup.parent.mkdir(exist_ok=True, parents=True)
                    shutil.copy2(destination, backup)
                staged = destination.with_name(destination.name + ".update-new")
                staged_paths.append(staged)
                shutil.copy2(item, staged)
                if file_sha256(item) != file_sha256(staged):
                    staged.unlink(missing_ok=True)
                    raise RuntimeError(L("hash_mismatch", path=relative))
                os.replace(staged, destination)
                staged_paths.remove(staged)
                if existed:
                    replaced.append((destination, backup))
                else:
                    created.append(destination)
            self._set_progress(
                version_index, total_versions, 0.55 + index / total * 0.35,
                L("applying", version=version_text),
            )
    except Exception as error:
        rollback_errors = []
        for destination in reversed(created):
            try:
                destination.unlink(missing_ok=True)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        for destination, backup in reversed(replaced):
            try:
                shutil.copy2(backup, destination)
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            raise RuntimeError(f"{error}; 更新回滚不完整: {'; '.join(rollback_errors)}") from error
        raise
    finally:
        for staged in staged_paths:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                pass
        shutil.rmtree(backup_root, ignore_errors=True)


class Updater:
    def __init__(self, gui, base_dir):
        self.gui = gui
        self.base_dir = Path(base_dir)
        self.runtime_dir = get_internal_base_dir(self.base_dir)
        self.temp_dir = self.base_dir / "temp_update"
        self.zip_path = self.base_dir / "update.zip"

    _current_executable_name = _current_executable_name
    _set_progress = _set_progress
    _is_target_process = _is_target_process
    kill_processes = kill_processes
    download_and_extract = download_and_extract
    update_files = update_files
    run_update_flow = run_update_flow

    def update_local_version(self, new_version):
        update_local_version(self.runtime_dir, new_version)


class UpdateWindow:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        root.title(L("window_title"))
        root.geometry("460x180")
        root.resizable(False, False)
        frame = tk.Frame(root, padx=20, pady=18)
        frame.pack(fill=tk.BOTH, expand=True)
        self.title_label = tk.Label(frame, text=L("title"), font=("Segoe UI", 14, "bold"))
        self.title_label.pack(anchor="w")
        self.desc_label = tk.Label(frame, text=L("desc"), fg="#666666", pady=10)
        self.desc_label.pack(anchor="w")
        self.progress = ttk.Progressbar(frame, orient="horizontal", length=100, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(8, 10))
        self.status_label = tk.Label(frame, text=L("prepare_check"), anchor="w")
        self.status_label.pack(fill=tk.X)

    def set_status(self, text, progress=None):
        def update():
            if progress is not None:
                self.progress["value"] = max(0, min(100, progress))
            self.status_label.config(text=text)
            self.root.update_idletasks()

        self.root.after(0, update)

    def finish(self, message, is_error=False, auto_close_ms=None):
        def finish():
            self.progress["value"] = self.progress["value"] if is_error else 100
            self.status_label.config(text=message)
            if is_error:
                from tkinter import messagebox

                messagebox.showerror(L("update_failed"), message)
            if auto_close_ms:
                self.root.after(auto_close_ms, self.root.destroy)

        self.root.after(0, finish)


def main():
    import argparse
    import threading
    import tkinter as tk

    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-start", action="store_true", help="启动后自动开始更新")
    parser.parse_args()

    base_dir = get_runtime_base_dir()
    os.chdir(base_dir)
    root = tk.Tk()
    gui = UpdateWindow(root)
    updater = Updater(gui, base_dir=base_dir)
    thread = threading.Thread(target=updater.run_update_flow, daemon=True)
    thread.start()
    root.mainloop()


if __name__ == "__main__":
    main()
