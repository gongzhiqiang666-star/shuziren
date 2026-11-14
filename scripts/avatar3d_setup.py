#!/usr/bin/env python3
"""Prepare the pinned CC0 GLB sample; no model runtime or third-party package is needed."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.request


SOURCE_COMMIT = "8c3fe13df098fac1ad62bb61972a404d2827ba54"
SOURCE_URL = (
    "https://raw.githubusercontent.com/met4citizen/TalkingHead/"
    + SOURCE_COMMIT
    + "/avatars/mpfb.glb"
)
EXPECTED_BYTES = 36_815_920
EXPECTED_SHA256 = "63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c"
READ_TIMEOUT_SECONDS = 30
DOWNLOAD_SECONDS = 180
CHUNK_BYTES = 1024 * 1024
PROJECT_DIR = Path(__file__).resolve().parents[1]
ASSET_PATH = PROJECT_DIR / "web" / "public" / "avatar-assets" / "mpfb.glb"


class SetupError(Exception):
    """A preparation failure with an operator-readable explanation."""


def verified_file(path: Path) -> bool:
    """A cache hit requires both the exact byte count and the pinned content hash."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size != EXPECTED_BYTES:
        return False
    digest = hashlib.sha256()
    received = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_BYTES)
            if not chunk:
                break
            received += len(chunk)
            if received > EXPECTED_BYTES:
                return False
            digest.update(chunk)
    return received == EXPECTED_BYTES and digest.hexdigest() == EXPECTED_SHA256


def check_destination(path: Path) -> bool:
    """Do not replace a user-provided file or follow an asset-directory symlink."""
    for parent in path.parents:
        if parent.is_symlink():
            raise SetupError("样例目录含符号链接，已停止。请在项目的实际目录中准备资源。")
    if path.is_symlink():
        raise SetupError("样例路径是符号链接，已保留原文件。请移走该链接后重试。")
    if path.exists():
        if verified_file(path):
            return True
        raise SetupError(
            "样例位置已有其他内容，已保留且不会覆盖。"
            "请将该文件移到自己的素材目录，或使用 --no-sample 导入它。"
        )
    return False


def prepare_sample(path: Path = ASSET_PATH) -> bool:
    """Return True for a verified cache hit, False for a newly downloaded sample."""
    if check_destination(path):
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    started = time.monotonic()
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "shuziren-avatar3d-setup/1", "Accept-Encoding": "identity"},
    )
    try:
        with urllib.request.urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise SetupError("下载服务未返回完整文件，请稍后重试。")
            declared_size = response.headers.get("Content-Length")
            if declared_size is not None:
                try:
                    correct_length = int(declared_size) == EXPECTED_BYTES
                except ValueError:
                    correct_length = False
                if not correct_length:
                    raise SetupError("下载大小与固定版本不符，已拒绝该响应。")
            digest = hashlib.sha256()
            received = 0
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=".mpfb-", suffix=".download", delete=False
            ) as output:
                temporary = Path(output.name)
                while True:
                    if time.monotonic() - started > DOWNLOAD_SECONDS:
                        raise SetupError("下载超过总等待时限，请检查网络后重试。")
                    chunk = response.read(CHUNK_BYTES)
                    if time.monotonic() - started > DOWNLOAD_SECONDS:
                        raise SetupError("下载超过总等待时限，请检查网络后重试。")
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > EXPECTED_BYTES:
                        raise SetupError("下载内容超过固定文件大小，已停止。")
                    digest.update(chunk)
                    output.write(chunk)
                if received != EXPECTED_BYTES:
                    raise SetupError("下载未完成，临时文件将被删除；可以重新运行。")
                if digest.hexdigest() != EXPECTED_SHA256:
                    raise SetupError("SHA256 校验失败，未安装该文件。请重新下载固定版本。")
                output.flush()
                os.fsync(output.fileno())
            # A parallel setup may have finished while this process was downloading.
            if check_destination(path):
                return True
            os.replace(temporary, path)
            temporary = None
            return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="准备本地 3D 页使用的固定版本 CC0 人物样例。")
    parser.add_argument(
        "--no-sample", action="store_true", help="跳过样例下载，打开页面后导入自己的 GLB 文件"
    )
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        print("需要 Python 3.10 或更新版本；本脚本不安装任何 Python 包。", file=sys.stderr)
        return 1
    if args.no_sample:
        print("已跳过内置人物样例。打开 3D 页面后，使用本地 GLB 导入功能。")
        return 0
    print("检查 CC0 人物样例（36.8 MB），文件位置：" + str(ASSET_PATH))
    try:
        cached = prepare_sample()
    except (SetupError, OSError, urllib.error.URLError, http.client.HTTPException) as error:
        print("样例准备失败：" + str(error)[:500], file=sys.stderr)
        print("可以用启动脚本的 --no-sample 选项跳过下载，再在页面导入自己的 GLB。", file=sys.stderr)
        print("也可手动下载下面的固定文件，保存到上述位置后重新运行校验：", file=sys.stderr)
        print(SOURCE_URL, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已取消样例准备，未完成的临时文件已清理。", file=sys.stderr)
        return 130
    print("已有样例的大小和 SHA256 均正确，直接复用。" if cached else "样例已下载并通过大小和 SHA256 校验。")
    print("只准备本地 3D 资源，不需要 CUDA、Docker 或云端数字人接口。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
