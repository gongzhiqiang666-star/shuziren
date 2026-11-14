"""Validate live-sticker creation, preview, version switch, and reload in Chromium."""

import argparse
import hashlib
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
    generated_colours = iter(("red", "green", "blue", "navy", "teal", "gold"))

    def provider(_self, *, dest, **_kwargs):
        Image.new("RGB", (96, 160), next(generated_colours)).save(dest, "PNG")

    with tempfile.TemporaryDirectory(prefix="sticker-ui-", ignore_cleanup_errors=True) as temporary:
        store = ConfigStore(Path(temporary) / "data")
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch("recovered.main.Api._generate_live_sticker_image_file", provider):
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(
                        executable_path=str(args.browser), headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    page.goto(base, wait_until="networkidle")
                    page.locator('a[href="#sticker-panel"]').click()
                    page.locator("#sticker-new-name").fill("青瓷杯直播贴片")
                    page.locator("#sticker-create").click()
                    page.locator("#sticker-product-name").fill("青瓷杯")
                    page.locator("#sticker-selling-points").fill("青绿色，530毫升，适合泡茶")
                    page.locator("#sticker-save").click()
                    page.get_by_text("项目已保存并可重开。").wait_for(timeout=10000)
                    page.locator("#sticker-prompts").click()
                    page.locator("#sticker-bg-prompt").wait_for(timeout=10000)
                    wait_until(lambda: page.locator("#sticker-bg-prompt").input_value(), bool,
                               "sticker prompts were not populated")
                    page.locator("#sticker-api-key").fill("fixture-request-only-key")
                    page.locator("#sticker-generate").click()
                    wait_until(lambda: page.locator("#sticker-bg-preview").get_attribute("src"),
                               lambda value: bool(value and value.startswith("data:image/png;base64,")),
                               "first sticker preview set was not displayed")
                    first_sources = page.eval_on_selector_all(
                        ".preview-grid img", "nodes => nodes.map(node => node.src)")
                    if len(first_sources) != 4 or any(not value.startswith("data:image/png;base64,")
                                                     for value in first_sources):
                        raise RuntimeError("first sticker preview set is incomplete")
                    first_hashes = [hashlib.sha256(value.encode()).hexdigest()
                                    for value in first_sources]
                    first_screenshot = report_dir / "sticker-first-version.png"
                    page.locator("#sticker-panel").screenshot(path=str(first_screenshot))

                    page.locator("#sticker-api-key").fill("fixture-request-only-key")
                    page.locator("#sticker-generate").click()
                    wait_until(lambda: page.locator("#sticker-bg-preview").get_attribute("src"),
                               lambda value: bool(value and value != first_sources[0]),
                               "second sticker version was not displayed")
                    second_sources = page.eval_on_selector_all(
                        ".preview-grid img", "nodes => nodes.map(node => node.src)")
                    second_hashes = [hashlib.sha256(value.encode()).hexdigest()
                                     for value in second_sources]
                    if first_hashes == second_hashes or page.locator("#sticker-api-key").input_value():
                        raise RuntimeError("sticker version did not switch or key remained in the page")
                    page.reload(wait_until="networkidle")
                    page.locator('a[href="#sticker-panel"]').click()
                    page.locator("#sticker-list").select_option(index=1)
                    wait_until(lambda: page.locator("#sticker-cover-preview").get_attribute("src"),
                               lambda value: bool(value and value.startswith("data:image/png;base64,")),
                               "reopened sticker preview set was not displayed")
                    reopened_sources = page.eval_on_selector_all(
                        ".preview-grid img", "nodes => nodes.map(node => node.src)")
                    if reopened_sources != second_sources:
                        raise RuntimeError("reopened sticker previews do not match the current version")
                    second_screenshot = report_dir / "sticker-reopened-version.png"
                    page.locator("#sticker-panel").screenshot(path=str(second_screenshot))
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    report = {
        "passed": True,
        "preview_count": len(second_sources),
        "first_version_hashes": first_hashes,
        "second_version_hashes": second_hashes,
        "version_changed": first_hashes != second_hashes,
        "reload_preserved_current_version": reopened_sources == second_sources,
        "api_key_persisted": False,
        "first_screenshot": str(first_screenshot),
        "reopened_screenshot": str(second_screenshot),
    }
    (report_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
