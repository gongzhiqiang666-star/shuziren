"""Validate held-product request planning through the real local Chromium UI."""

import argparse
import hashlib
import json
import sqlite3
import tempfile
import threading
import uuid
import wave
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore
from scripts.voice_store import VoiceStore


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--browser", type=Path,
                        default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
    parser.add_argument("--runtime-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit("local Chrome is missing")
    runtime_root = args.runtime_root.resolve()
    if not runtime_root.is_dir():
        raise SystemExit("runtime root is missing")
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    # Some bundled Windows SQLite builds release their last file handle only at
    # interpreter shutdown. The synthetic fixture is under the OS temp root, so
    # a late cleanup failure must not discard an otherwise complete UI report.
    with tempfile.TemporaryDirectory(prefix="hold-ui-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        avatar, product = root / "avatar.png", root / "product.jpg"
        audio = root / "speech.wav"
        Image.new("RGB", (64, 96), (210, 190, 170)).save(avatar)
        Image.new("RGB", (64, 64), (80, 130, 110)).save(product)
        with wave.open(str(audio), "wb") as sound:
            sound.setparams((1, 2, 24000, 24000, "NONE", ""))
            sound.writeframes(bytes(48000))
        data = root / "data"
        held_id = "owned-validation-result"
        held_directory = data / "hold-product-tasks" / held_id
        held_directory.mkdir(parents=True)
        held_output = held_directory / "held-product.png"
        held_output.write_bytes(avatar.read_bytes())
        held_state = {
            "id": held_id, "status": "succeeded", "output": str(held_output.resolve()),
            "output_sha256": hashlib.sha256(held_output.read_bytes()).hexdigest(), "error": None,
        }
        (data / "hold-product-tasks" / "task.json").write_text(
            json.dumps(held_state, ensure_ascii=False), encoding="utf-8")
        products = ProductStore(data)
        managed_product = products.save(title="青瓷杯", content="手持商品浏览器验证", product_index=1)
        script_id = products.add_script(managed_product, "这是当前已审核的青瓷杯讲解语音。")
        products.select_script(managed_product["id"], script_id)
        voices = VoiceStore(data)
        voice_id = str(uuid.uuid4())
        voice_directory = voices.root / voice_id
        voice_directory.mkdir()
        reference_audio = voice_directory / "ref_audio.wav"
        reference_text = voice_directory / "ref_text.txt"
        reference_audio.write_bytes(audio.read_bytes())
        reference_text.write_text("浏览器受管语音验证", encoding="utf-8")
        voice_audio_sha = hashlib.sha256(reference_audio.read_bytes()).hexdigest()
        voice_text_sha = hashlib.sha256(reference_text.read_bytes()).hexdigest()
        with sqlite3.connect(voices.path) as database:
            database.execute("""INSERT INTO voices
                (id,name,transcript,audio_sha256,text_sha256,duration,authorization_type)
                VALUES(?,?,?,?,?,?,?)""", (voice_id, "浏览器验证音色", "浏览器受管语音验证",
                voice_audio_sha, voice_text_sha, 1.0, "self_recorded"))
        voices.select(voice_id)
        tts_directory = data / "tts"
        tts_directory.mkdir()
        managed_audio = tts_directory / "managed-validation.wav"
        managed_audio.write_bytes(audio.read_bytes())
        managed_audio_sha = hashlib.sha256(managed_audio.read_bytes()).hexdigest()
        tts_id = "managed-validation-tts"
        tts_state = {
            "id": tts_id, "status": "succeeded", "product_id": managed_product["id"],
            "product_version": managed_product["version"], "product_title": managed_product["title"],
            "script_id": script_id, "voice_id": voice_id,
            "voice_audio_sha256": voice_audio_sha, "voice_text_sha256": voice_text_sha,
            "engine": "indextts", "result": {"output": str(managed_audio.resolve()),
                "sha256": managed_audio_sha, "provider": "recovered-voice-infer-v3"},
        }
        (data / "tts-task.json").write_text(
            json.dumps(tts_state, ensure_ascii=False), encoding="utf-8")
        store = ConfigStore(data)
        store.save({"version": 1, "runtime_root": str(runtime_root), "port": 5158})
        server = create_server(store, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                page.goto(base, wait_until="networkidle")
                page.locator("#tts-status").get_by_text("语音已生成").wait_for(timeout=10000)
                page.locator('a[href="#hold-product-panel"]').click()
                page.locator("#hold-avatar").fill(str(avatar))
                page.locator("#hold-product").fill(str(product))
                page.locator("#hold-product-name").fill("青瓷杯")
                page.locator("#hold-plan").click()
                result = page.locator("#hold-plan-result")
                result.get_by_text("2113900488247824386").wait_for(timeout=10000)
                plan = json.loads(result.text_content())
                if page.locator("#hold-api-key").input_value():
                    raise RuntimeError("request planning unexpectedly populated an API key")
                if (plan.get("engine") != "qwen21" or len(plan.get("uploads", [])) != 2
                        or not all(len(item.get("sha256", "")) == 64 for item in plan["uploads"])):
                    raise RuntimeError("held-product plan is incomplete")
                screenshot = report_dir / "hold-product-plan.png"
                page.locator("#hold-product-panel").screenshot(path=str(screenshot))
                if page.locator("#hold-motion-audio").input_value():
                    raise RuntimeError("managed TTS validation requires a blank manual audio path")
                page.locator("#hold-motion-resolution").select_option("720p")
                page.locator("#hold-motion-plan").click()
                motion_result = page.locator("#hold-motion-plan-result")
                motion_result.get_by_text("2031016553440878594").wait_for(timeout=10000)
                motion = json.loads(motion_result.text_content())
                if page.locator("#hold-motion-api-key").input_value():
                    raise RuntimeError("motion planning unexpectedly populated an API key")
                if (motion.get("engine") != "ltx" or motion.get("max_res") != 1280
                        or motion.get("fps") != 25 or motion.get("instance_type") != "plus"
                        or any(len(motion[k].get("sha256", "")) != 64 for k in ("image", "audio"))
                        or motion["image"]["sha256"] != held_state["output_sha256"]
                        or motion["audio"]["sha256"] != managed_audio_sha
                        or page.locator("#hold-motion-image").input_value()):
                    raise RuntimeError("held-product motion plan is incomplete")
                motion_screenshot = report_dir / "hold-product-motion-plan.png"
                page.locator("#hold-product-panel").screenshot(path=str(motion_screenshot))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)
    report = {"passed": True, "webapp_id": plan["webapp_id"], "engine": plan["engine"],
              "upload_count": len(plan["uploads"]), "api_key_persisted": False,
              "screenshot": str(screenshot), "motion_webapp_id": motion["webapp_id"],
              "motion_engine": motion["engine"], "motion_max_res": motion["max_res"],
              "motion_fps": motion["fps"], "motion_api_key_persisted": False,
              "managed_hold_handoff": True, "managed_tts_handoff": True,
              "motion_screenshot": str(motion_screenshot)}
    (report_dir / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
