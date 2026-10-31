#!/usr/bin/env python3
"""Consistent local Compose database+audio backup. Restore requires --confirm-replace."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


class BackupError(RuntimeError):
    pass


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


class Compose:
    def __init__(self, project: Path):
        self.project = project

    def command(self, args, *, output=None, input_file=None, timeout=180):
        try:
            result = subprocess.run(["docker", "compose", *args], cwd=self.project, stdout=output if output is not None else subprocess.PIPE, stdin=input_file, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise BackupError("Compose命令不可用或超时。未输出可能含凭据的底层信息。") from None
        if result.returncode:
            raise BackupError("Compose操作失败；数据备份/恢复未完成。请在本机检查Docker状态。")
        return result.stdout.decode("utf-8").strip() if output is None else ""

    def running(self):
        return "app" in self.command(["ps", "--status", "running", "--services"]).splitlines()

    def image(self):
        container = self.container()

        try:
            result = subprocess.run(["docker", "inspect", "--format", "{{.Image}}", container], cwd=self.project, capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise BackupError("无法确认app镜像。") from None
        image = result.stdout.strip()
        if result.returncode or not re.fullmatch("sha256:[a-f0-9]{64}", image):
            raise BackupError("无法确认app镜像。")
        return image

    def container(self):
        container = self.command(["ps", "--all", "--quiet", "app"])
        if not re.fullmatch("[a-f0-9]{12,64}", container):
            raise BackupError("需要已经创建的单个app容器。")
        return container

    def volume_helper(self, script):
        # Use the exact stopped container's mounts and image, even if the
        # compose file or its image tag was subsequently edited.
        try:
            result = subprocess.run(["docker", "run", "--rm", "--network", "none", "--volumes-from", self.container(), "--user", "0", "--entrypoint", "sh", self.image(), "-c", script], cwd=self.project, capture_output=True, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise BackupError("音频卷维护失败。") from None
        if result.returncode:
            raise BackupError("音频卷维护失败。")

    def stop(self):
        self.command(["stop", "--timeout", "35", "app"], timeout=50)
        if self.running():
            raise BackupError("app仍在运行，不能获得数据库和音频的一致快照。")

    def start(self):
        self.command(["start", "app"])

    def dump(self, path):
        with path.open("xb") as output:
            self.command(["exec", "-T", "db", "pg_dump", "-U", "shuziren", "-d", "shuziren", "--format=custom", "--no-owner", "--no-privileges"], output=output, timeout=600)
        os.chmod(path, 0o600)

    def copy_audio_out(self, path):
        path.mkdir(mode=0o700)
        self.command(["cp", "app:/data/audio/.", str(path)], timeout=600)

    def restore(self, backup):
        with (backup / "database.dump").open("rb") as source:
            self.command(["exec", "-T", "db", "pg_restore", "-U", "shuziren", "-d", "shuziren", "--clean", "--if-exists", "--single-transaction", "--exit-on-error", "--no-owner", "--no-privileges"], input_file=source, timeout=600)
        # A historical snapshot must not resume old live output or redispatch
        # jobs. Restoration requires fresh operator review and a new output URL.
        pause_sql = """BEGIN;
UPDATE live_sessions SET status=CASE WHEN status='ended' THEN 'ended' ELSE 'paused' END,epoch=epoch+1,media_session_id=NULL,updated_at=now();
UPDATE speech_jobs SET status='cancelled',error_code='backup_restored',reason='从备份恢复后旧任务已取消，请重新生成和审核。',updated_at=now() WHERE status IN ('draft','blocked','approved','queued','synthesizing','ready','failed');
UPDATE speech_jobs SET status='delivery_unknown',error_code='restore_delivery_unknown',reason='备份中的发送结果不可确定，禁止重播。',updated_at=now() WHERE status='sending';
DO $$ BEGIN
IF to_regclass('session_outputs') IS NOT NULL THEN
 UPDATE session_outputs SET enabled=false,generation=generation+1,token_hash=NULL,lease_id=NULL,receiver_id=NULL,lease_epoch=NULL,lease_expires_at=NULL,last_heartbeat_at=NULL,peer_state='closed',video_ready=false,audio_ready=false,media_session_id=NULL,updated_at=now();
END IF;
IF to_regclass('usage_events') IS NOT NULL THEN
 UPDATE usage_events SET status='unknown',error_code='backup_restored',updated_at=now() WHERE status='pending';
END IF;
IF to_regclass('taobao_actions') IS NOT NULL THEN
 UPDATE taobao_actions SET status='delivery_unknown',error_code='backup_restored',updated_at=now() WHERE status='pending';
END IF;
IF to_regclass('taobao_events') IS NOT NULL THEN
 UPDATE taobao_events SET status='ignored',error_code='backup_restored' WHERE status IN ('pending','generating');
END IF;
IF to_regclass('speech_schedules') IS NOT NULL THEN
 UPDATE speech_schedules SET status=CASE WHEN status='dispatching' THEN 'delivery_unknown' ELSE 'cancelled' END,error_code='backup_restored',reason='备份恢复后旧计划已失效，不会补播。',updated_at=now() WHERE status IN ('scheduled','dispatching');
END IF;
END $$;
INSERT INTO audit_events(shop_id,resource_id,event,details) SELECT id,id::text,'backup_restored','{"sessions_paused":true,"old_jobs_cancelled":true}'::jsonb FROM shops;
COMMIT;"""
        self.command(["exec", "-T", "db", "psql", "-U", "shuziren", "-d", "shuziren", "-v", "ON_ERROR_STOP=1", "-c", pause_sql])
        # The path and shell snippet are fixed code. User filenames never enter
        # this shell; subprocess arguments carry them separately in compose cp.
        self.volume_helper("find /data/audio -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +")
        self.command(["cp", str(backup / "audio") + "/.", "app:/data/audio"], timeout=600)
        self.volume_helper("chown -R 10001:10001 /data/audio")


def snapshot(compose: Compose, destination: Path) -> Path:
    if destination.exists():
        raise BackupError("备份目录已存在，拒绝覆盖。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".incomplete")
    if staging.exists():
        raise BackupError("同名未完成备份存在，请换一个输出目录。")
    staging.mkdir(mode=0o700)
    image = compose.image()
    compose.dump(staging / "database.dump")
    compose.copy_audio_out(staging / "audio")
    entries = {}
    for file in sorted(staging.rglob("*")):
        if file.is_symlink():
            raise BackupError("音频卷含符号链接，拒绝归档不确定目标。")
        if file.is_file():
            os.chmod(file, 0o600)
            entries[file.relative_to(staging).as_posix()] = {"sha256": digest(file), "bytes": file.stat().st_size}
    if not entries.get("database.dump", {}).get("bytes"):
        raise BackupError("数据库备份为空。")
    manifest = {"schema": 1, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "app_image": image, "files": entries, "environment_file_included": False, "consistent": "app_stopped_before_database_and_audio_snapshot"}
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(staging / "manifest.json", 0o600)
    staging.rename(destination)
    return destination


def verify_backup(folder: Path) -> dict:
    if folder.is_symlink() or not folder.is_dir():
        raise BackupError("备份必须是本地常规目录。")
    manifest_path = folder / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 16 * 1024 * 1024:
        raise BackupError("备份清单缺失或无效。")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BackupError("备份清单无法读取。") from None
    if not isinstance(manifest, dict) or manifest.get("schema") != 1 or not isinstance(manifest.get("files"), dict) or "database.dump" not in manifest["files"]:
        raise BackupError("备份清单版本或内容无效。")
    files = manifest["files"]
    if any(file.is_symlink() for file in folder.rglob("*")):
        raise BackupError("备份中不允许符号链接。")
    for relative, record in files.items():
        if not isinstance(relative, str):
            raise BackupError("备份路径类型无效。")
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative or relative not in {"database.dump"} and (not path.parts or path.parts[0] != "audio"):
            raise BackupError("备份含非法路径。")
        file = folder / relative
        if any(parent.is_symlink() for parent in [file, *file.parents] if parent != folder.parent) or not file.is_file():
            raise BackupError("备份文件缺失或含符号链接。")
        if not isinstance(record, dict) or file.stat().st_size != record.get("bytes") or digest(file) != record.get("sha256"):
            raise BackupError("备份文件完整性核验失败。")
    actual = {file.relative_to(folder).as_posix() for file in folder.rglob("*") if file.is_file() and file.name != "manifest.json"}
    if actual != set(files) or not (folder / "audio").is_dir() or (folder / "audio").is_symlink():
        raise BackupError("备份文件列表不一致。")
    if not isinstance(manifest.get("app_image"), str) or not re.fullmatch("sha256:[a-f0-9]{64}", manifest["app_image"]):
        raise BackupError("备份镜像标识无效。")
    if (folder / "database.dump").stat().st_size==0:
        raise BackupError("数据库备份为空。")
    return manifest


@contextmanager
def maintenance_lock(project: Path):
    lock = project / ".backup-restore.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise BackupError("另一备份/恢复正在运行，或上次进程异常退出。确认无维护任务后才能移除 .backup-restore.lock。") from None
    try:
        (lock / "owner.json").write_text(json.dumps({"pid": os.getpid(), "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}), encoding="utf-8")
        yield
    finally:
        (lock / "owner.json").unlink(missing_ok=True)
        lock.rmdir()


def backup(compose: Compose, destination: Path) -> Path:
    running = compose.running()
    try:
        compose.stop()
        return snapshot(compose, destination)
    finally:
        if running:
            compose.start()


def restore(compose: Compose, source: Path, safety_destination: Path, confirmed: bool):
    if not confirmed:
        raise BackupError("恢复会替换本地数据；请核对源目录后明确传入 --confirm-replace。")
    manifest = verify_backup(source)
    if compose.image() != manifest["app_image"]:
        raise BackupError("备份与当前app镜像不同。先恢复匹配的代码/镜像；此脚本不自动降级数据库。")
    running = compose.running()
    safe_to_start = True
    try:
        compose.stop()
        snapshot(compose, safety_destination)
        try:
            compose.restore(source)
        except BaseException:
            try:
                compose.restore(safety_destination)
            except BaseException:
                safe_to_start = False
                raise BackupError("恢复和自动回退均失败。app保持停止；请使用before-restore备份人工恢复，勿继续写入。") from None
            raise BackupError("恢复失败，已用操作前快照自动回退。") from None
    finally:
        if running and safe_to_start:
            compose.start()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("backup", "verify", "restore"), default="backup")
    parser.add_argument("path", type=Path, nargs="?")
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--confirm-replace", action="store_true")
    args = parser.parse_args(argv)
    project = args.project.resolve()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = args.path.resolve() if args.path else project / "backups" / ("backup-" + stamp)
    compose = Compose(project)
    try:
        if args.command == "backup":
            with maintenance_lock(project):
                backup(compose, target)
            print("Backup complete: " + str(target))
            print(".env与模型权重未打包，请分别保管原配置与模型。")
        elif args.command == "verify":
            if args.path is None:
                raise BackupError("verify需要提供备份目录。")
            verify_backup(target)
            print("Backup hashes verified: " + str(target))
        else:
            if args.path is None:
                raise BackupError("restore需要提供备份目录。")
            safety = project / "backups" / ("before-restore-" + stamp)
            with maintenance_lock(project):
                restore(compose, target, safety, args.confirm_replace)
            print("Restore complete. Previous state backup: " + str(safety))
    except (BackupError, OSError) as error:
        print(str(error) if isinstance(error, BackupError) else "本地文件操作失败；未完成备份或恢复。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
