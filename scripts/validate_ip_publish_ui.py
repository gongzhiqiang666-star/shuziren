"""Validate the IP publication UI against a local no-network platform adapter."""

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore


def wait_until(read, predicate, message, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(0.05)
    raise RuntimeError(message)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--browser", type=Path,
                        default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
    args = parser.parse_args(argv)
    if not args.browser.is_file() or not args.ffmpeg.is_file() or not args.runtime_root.is_dir():
        raise SystemExit("local Chrome, FFmpeg, or runtime root is missing")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    calls = []

    async def publish_video_to_platforms(**kwargs):
        calls.append({key: value for key, value in kwargs.items() if key != "publish_date"})
        return {"success": True, "results": {
            platform: {"success": True, "fixture": True}
            for platform in kwargs["platforms"]}}

    module = types.ModuleType("tools.social_auto_upload.test")
    module.publish_video_to_platforms = publish_video_to_platforms
    package = types.ModuleType("tools.social_auto_upload")
    package.__path__ = []

    with tempfile.TemporaryDirectory(prefix="ip-publish-ui-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        video = root / "final.mp4"
        encoded = subprocess.run([
            str(args.ffmpeg), "-nostdin", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=navy:s=320x240:r=25:d=1",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-movflags", "+faststart", str(video),
        ], capture_output=True, timeout=30)
        if encoded.returncode != 0 or not video.is_file():
            raise RuntimeError("failed to create the publication fixture")
        store = ConfigStore(root / "data")
        store.save({"version": 1, "runtime_root": str(args.runtime_root.resolve()), "port": 5158})
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.dict(sys.modules, {
                    "tools.social_auto_upload": package,
                    "tools.social_auto_upload.test": module}):
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(
                        executable_path=str(args.browser), headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    page.goto(base, wait_until="networkidle")
                    page.locator('a[href="#ip-agent-panel"]').click()
                    page.locator("#ip-new-name").fill("青瓷杯 IP 成片")
                    page.locator("#ip-create").click()
                    page.locator("#ip-video-source").fill(str(video))
                    page.locator("#ip-import-video").click()
                    wait_until(lambda: page.locator("#ip-status").text_content(),
                               lambda value: bool(value and "成片" in value and "尚未导入" not in value),
                               "managed final video was not imported")
                    page.locator("#ip-title").fill("青瓷杯介绍")
                    page.locator("#ip-tags").fill("茶杯 青瓷")
                    page.locator("#ip-platform-kuaishou").check()
                    page.locator("#ip-accounts").fill(
                        json.dumps({"douyin": "shop_1", "kuaishou": "shop_2"}))
                    page.locator("#ip-save").click()
                    page.get_by_text("发布设置已保存。").wait_for(timeout=10000)
                    page.locator("#ip-dry-run").click()
                    wait_until(lambda: page.locator("#ip-result").text_content(),
                               lambda value: bool(value and '"video_sha256"' in value
                                                  and '"platforms"' in value),
                               "publication dry-run was not displayed")
                    if calls:
                        raise RuntimeError("dry-run invoked the platform adapter")
                    page.locator("#ip-publish").click()
                    wait_until(lambda: len(calls), lambda value: value == 1,
                               "fixture platform adapter was not invoked exactly once")
                    wait_until(lambda: page.locator("#ip-status").text_content(),
                               lambda value: bool(value and "success" in value),
                               "successful publication state was not displayed")
                    page.locator("#ip-publish").click()
                    time.sleep(0.3)
                    if len(calls) != 1:
                        raise RuntimeError("idempotent repeat invoked the platform adapter again")
                    first_screenshot = report_dir / "ip-publish-succeeded.png"
                    page.locator("#ip-agent-panel").screenshot(path=str(first_screenshot))
                    page.reload(wait_until="networkidle")
                    page.locator('a[href="#ip-agent-panel"]').click()
                    page.locator("#ip-list").select_option(index=1)
                    wait_until(lambda: page.locator("#ip-status").text_content(),
                               lambda value: bool(value and "success" in value),
                               "reopened publication state was not restored")
                    reopened_screenshot = report_dir / "ip-publish-reopened.png"
                    page.locator("#ip-agent-panel").screenshot(path=str(reopened_screenshot))
                    page.locator("#ip-delete").click()
                    wait_until(lambda: page.locator("#ip-list option").count(),
                               lambda value: value == 1,
                               "deleted project remained in the project list")
                    if page.locator("#ip-list").input_value():
                        raise RuntimeError("deleted project remained selected")
                    deleted_screenshot = report_dir / "ip-project-deleted.png"
                    page.locator("#ip-agent-panel").screenshot(path=str(deleted_screenshot))
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    report = {
        "passed": True,
        "dry_run_no_side_effect": True,
        "platforms": calls[0]["platforms"],
        "adapter_call_count": len(calls),
        "repeat_was_idempotent": len(calls) == 1,
        "reload_preserved_success": True,
        "crud": {"create": True, "update": True, "read_after_reload": True,
                 "delete": True, "remaining_project_options": 1},
        "screenshot": str(first_screenshot),
        "reopened_screenshot": str(reopened_screenshot),
        "deleted_screenshot": str(deleted_screenshot),
    }
    (report_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
