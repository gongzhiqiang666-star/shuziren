"""Validate cloud-digital-human project UI with local managed media fixtures."""

import argparse
import json
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from playwright.sync_api import sync_playwright

from recovered import runninghub_talk
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
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--browser", type=Path,
                        default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
    args = parser.parse_args(argv)
    if not args.browser.is_file() or not args.ffmpeg.is_file():
        raise SystemExit("local Chrome or FFmpeg is missing")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cloud-dh-ui-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        avatar = root / "avatar.png"
        audio = root / "speech.wav"
        video = root / "talk.mp4"
        Image.new("RGB", (96, 160), (40, 100, 180)).save(avatar)
        with wave.open(str(audio), "wb") as stream:
            stream.setparams((1, 2, 24000, 24000, "NONE", ""))
            stream.writeframes(bytes(48000))
        encoded = subprocess.run([
            str(args.ffmpeg), "-nostdin", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(avatar), "-i", str(audio), "-t", "1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-movflags", "+faststart", str(video),
        ], capture_output=True, timeout=30)
        if encoded.returncode != 0 or not video.is_file():
            raise RuntimeError("failed to create the managed video fixture")

        def provider(**kwargs):
            shutil.copyfile(video, kwargs["dest"])
            return {"task_id": "ui-managed-video", "status": "success",
                    "video_path": str(kwargs["dest"])}

        store = ConfigStore(root / "data")
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with patch.object(runninghub_talk, "_generate_talk_video_cancellable",
                              side_effect=provider):
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(
                        executable_path=str(args.browser), headless=True)
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    page.goto(base, wait_until="networkidle")
                    page.locator('a[href="#cloud-dh-panel"]').click()
                    page.locator("#cloud-dh-new-name").fill("青瓷杯云口播")
                    page.locator("#cloud-dh-create").click()
                    page.locator("#cloud-dh-prompt").fill("蓝色服装，正面镜头")
                    page.locator("#cloud-dh-save").click()
                    page.get_by_text("项目已保存并可重开。").wait_for(timeout=10000)
                    page.locator("#cloud-dh-avatar-source").fill(str(avatar))
                    page.locator("#cloud-dh-import-avatar").click()
                    wait_until(lambda: page.locator("#cloud-dh-avatar-preview").get_attribute("src"),
                               lambda value: bool(value and "/api/cloud-dh/media?" in value),
                               "managed avatar preview was not displayed")
                    page.locator("#cloud-dh-audio-source").fill(str(audio))
                    page.locator("#cloud-dh-import-audio").click()
                    wait_until(lambda: page.locator("#cloud-dh-audio-preview").get_attribute("src"),
                               lambda value: bool(value and "/api/cloud-dh/media?" in value),
                               "managed audio preview was not displayed")
                    page.locator("#cloud-dh-api-key").fill("fixture-request-only-key")
                    page.locator("#cloud-dh-generate-video").click()
                    wait_until(lambda: page.locator("#cloud-dh-video-preview").get_attribute("src"),
                               lambda value: bool(value and "/api/cloud-dh/media?" in value),
                               "managed video preview was not displayed")
                    if page.locator("#cloud-dh-api-key").input_value():
                        raise RuntimeError("cloud request key remained in the page")
                    first_screenshot = report_dir / "cloud-dh-complete.png"
                    page.locator("#cloud-dh-panel").screenshot(path=str(first_screenshot))
                    before = [page.locator(selector).get_attribute("src") for selector in (
                        "#cloud-dh-avatar-preview", "#cloud-dh-audio-preview", "#cloud-dh-video-preview")]
                    page.reload(wait_until="networkidle")
                    page.locator('a[href="#cloud-dh-panel"]').click()
                    page.locator("#cloud-dh-list").select_option(index=1)
                    wait_until(lambda: page.locator("#cloud-dh-video-preview").get_attribute("src"),
                               lambda value: bool(value and "/api/cloud-dh/media?" in value),
                               "reopened cloud media was not displayed")
                    after = [page.locator(selector).get_attribute("src") for selector in (
                        "#cloud-dh-avatar-preview", "#cloud-dh-audio-preview", "#cloud-dh-video-preview")]
                    if before != after:
                        raise RuntimeError("cloud project media URLs changed after reload")
                    reopened_screenshot = report_dir / "cloud-dh-reopened.png"
                    page.locator("#cloud-dh-panel").screenshot(path=str(reopened_screenshot))
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    report = {
        "passed": True,
        "managed_avatar_preview": True,
        "managed_audio_preview": True,
        "managed_video_preview": True,
        "reload_preserved_current_media": before == after,
        "api_key_persisted": False,
        "screenshot": str(first_screenshot),
        "reopened_screenshot": str(reopened_screenshot),
    }
    (report_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
