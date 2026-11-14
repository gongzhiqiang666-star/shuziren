"""Run the X11 recorded-interaction workflow through a real local Chromium page."""

import argparse
import hashlib
import json
import subprocess
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--browser", type=Path,
                        default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
    args = parser.parse_args(argv)
    runtime = args.runtime_root.resolve()
    ffmpeg = runtime / "_internal/env/ffmpeg/bin/ffmpeg.exe"
    if not ffmpeg.is_file() or not args.browser.is_file():
        raise SystemExit("runtime FFmpeg or local browser is missing")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="x11-ui-") as temporary:
        data = Path(temporary) / "data"
        data.mkdir()
        source = Path(temporary) / "source.mp4"
        reply = Path(temporary) / "reply.wav"
        subprocess.run([
            str(ffmpeg), "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=1.6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1.6", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([
            str(ffmpeg), "-y", "-f", "lavfi", "-i", "sine=frequency=660:duration=0.2",
            "-c:a", "pcm_s16le", str(reply),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        store = ConfigStore(data)
        store.save({"version": 1, "runtime_root": str(runtime), "port": 5158})
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(base, wait_until="networkidle")
                page.locator('a[href="#recorded-interaction-panel"]').click()
                page.locator("#recorded-source").fill(str(source))
                page.locator("#recorded-start").fill("100")
                page.locator("#recorded-end").fill("500")
                page.locator("#recorded-audio").fill(str(reply))
                page.locator("#recorded-source-id").fill("reply-one")
                page.locator("#recorded-add").click()
                page.locator("#recorded-start").fill("400")
                page.locator("#recorded-end").fill("700")
                page.locator("#recorded-source-id").fill("overlap")
                page.locator("#recorded-add").click()
                page.locator("#recorded-error").get_by_text("回复区间不能重叠").wait_for()
                page.locator("#recorded-start").fill("700")
                page.locator("#recorded-end").fill("1000")
                page.locator("#recorded-source-id").fill("reply-two")
                page.locator("#recorded-add").click()
                if page.locator("#recorded-replacements li").count() != 2:
                    raise RuntimeError("approved replacement list was not rendered")
                page.locator("#recorded-start-task").click()
                page.locator("#recorded-status").get_by_text("录播互动成片已生成").wait_for(timeout=30000)
                video_url = page.locator("#recorded-preview").get_attribute("src")
                download_url = page.locator("#recorded-download").get_attribute("href")
                if not video_url or video_url != download_url:
                    raise RuntimeError("preview and download do not reference the same owned result")
                response = page.request.get(base + video_url)
                if not response.ok or response.headers.get("content-type") != "video/mp4":
                    raise RuntimeError("published result is not downloadable as MP4")
                output = report_dir / "result.mp4"
                output.write_bytes(response.body())
                screenshot = report_dir / "recorded-interaction.png"
                page.locator("#recorded-interaction-panel").screenshot(path=str(screenshot))
                report = {
                    "passed": True,
                    "browser": str(args.browser),
                    "replacement_count": 2,
                    "overlap_rejected": True,
                    "video_url": video_url,
                    "output_bytes": output.stat().st_size,
                    "output_sha256": sha256(output),
                    "screenshot": str(screenshot),
                }
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
    (report_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
