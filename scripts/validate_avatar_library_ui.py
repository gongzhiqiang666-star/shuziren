"""Validate owned avatar import, selection, preview, deletion, and reload in Chromium."""

import argparse
import json
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

from PIL import Image
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


def avatar_fixture(root, colour):
    (root / "frames").mkdir(parents=True)
    (root / "positions").mkdir()
    Image.new("RGB", (24, 32), colour).save(root / "frames" / "000000.jpg")
    (root / "positions" / "000000.txt").write_text(
        "fps: 25\nwidth: 24\nheight: 32\nis_no_face: False\n"
        "bounding_box: [2, 20, 3, 22]\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--browser", type=Path,
                        default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit("local Chrome is missing")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="avatar-ui-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        first, second = root / "first-avatar", root / "second-avatar"
        avatar_fixture(first, (80, 130, 190))
        avatar_fixture(second, (180, 100, 80))
        store = ConfigStore(root / "data")
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        editor_launch = patch("recovered.main.Api.launch_audio_editor",
                              return_value={"status": "success", "pid": 4321})
        launch_mock = editor_launch.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=str(args.browser), headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.set_default_timeout(10000)
                page.goto(base, wait_until="networkidle")
                print("avatar-ui: page-ready", flush=True)
                page.locator("#audio-editor-start").click()
                page.get_by_text("音频编辑器已启动。").wait_for(timeout=10000)
                if launch_mock.call_count != 1:
                    raise RuntimeError("audio editor launch was not dispatched exactly once")
                page.locator('a[href="#avatar-panel"]').click()
                for name, source in (("主播形象", first), ("待删除形象", second)):
                    page.locator("#avatar-name").fill(name)
                    page.locator("#avatar-source").fill(str(source))
                    page.locator("#avatar-import").click()
                    page.get_by_text("形象已导入并选中。").wait_for(timeout=10000)
                    print("avatar-ui: imported " + name, flush=True)
                options = page.locator("#avatar-list option").all_text_contents()
                if options != ["请选择形象", "主播形象", "待删除形象"]:
                    raise RuntimeError("imported avatar list is incomplete")
                page.locator("#avatar-list").select_option(label="主播形象")
                wait_until(lambda: page.locator("#avatar-info").text_content(),
                           lambda value: bool(value and "主播形象" in value and "24×32" in value),
                           "selected avatar details were not displayed")
                wait_until(lambda: page.locator("#avatar-preview").get_attribute("src"),
                           lambda value: bool(value and "/api/avatars/sample?" in value),
                           "selected avatar preview was not displayed")
                delete_options = page.locator("#avatar-delete-list option").all_text_contents()
                if "主播形象" in delete_options or "待删除形象" not in delete_options:
                    raise RuntimeError("selected avatar deletion boundary is incorrect")
                page.locator("#avatar-delete-list").select_option(label="待删除形象")
                page.locator("#avatar-delete").click()
                page.get_by_text("形象已删除。").wait_for(timeout=10000)
                print("avatar-ui: deletion-complete", flush=True)
                first_screenshot = report_dir / "avatar-selected.png"
                page.locator("#avatar-panel").screenshot(path=str(first_screenshot))
                page.reload(wait_until="networkidle")
                page.locator('a[href="#avatar-panel"]').click()
                wait_until(lambda: page.locator("#avatar-list option").all_text_contents(),
                           lambda values: values == ["请选择形象", "主播形象"],
                           "avatar deletion or selection did not survive reload")
                if page.locator("#avatar-list").input_value() == "":
                    raise RuntimeError("selected avatar was not restored")
                reopened_screenshot = report_dir / "avatar-reopened.png"
                page.locator("#avatar-panel").screenshot(path=str(reopened_screenshot))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
            editor_launch.stop()

    report = {
        "passed": True,
        "imported_count": 2,
        "selected_avatar_protected": True,
        "unselected_avatar_deleted": True,
        "reload_preserved_selection": True,
        "audio_editor_launch_dispatched": True,
        "screenshot": str(first_screenshot),
        "reopened_screenshot": str(reopened_screenshot),
    }
    (report_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
