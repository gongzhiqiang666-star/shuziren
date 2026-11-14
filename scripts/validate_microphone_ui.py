"""Exercise the browser microphone recorder with Chrome's controlled audio device."""

import argparse
from array import array
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import wave

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore
from scripts.voice_store import VoiceStore


def make_audio(path, seconds=4, sample_rate=44100):
    samples = array('h', (round(8000 * math.sin(2 * math.pi * 330 * index / sample_rate))
                          for index in range(seconds * sample_rate)))
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    runtime = args.runtime_root.resolve()
    ffmpeg = runtime / '_internal/env/ffmpeg/bin/ffmpeg.exe'
    if not args.browser.is_file() or not ffmpeg.is_file():
        raise SystemExit('Chrome or packaged FFmpeg is missing')
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix='microphone-ui-', ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        data = root / 'data'
        audio = root / 'microphone-fixture.wav'
        make_audio(audio)
        ConfigStore(data).save({'version': 1, 'runtime_root': str(runtime), 'port': 5158})
        server = create_server(ConfigStore(data), port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=str(args.browser), headless=True,
                    args=['--use-fake-device-for-media-stream',
                          '--use-fake-ui-for-media-stream',
                          '--use-file-for-fake-audio-capture=' + str(audio)])
                context = browser.new_context()
                context.grant_permissions(['microphone'], origin=base)
                page = context.new_page()
                page.goto(base, wait_until='networkidle')
                page.locator('a[href="#voice-panel"]').click()
                page.locator('#voice-name').fill('浏览器虚拟麦克风实测')
                page.locator('#voice-transcript').fill('这是本机浏览器录音链验证。')
                page.locator('#voice-authorization-type').select_option('self_recorded')
                page.locator('#voice-authorization-reference').fill('自动化虚拟设备夹具')
                page.locator('#record-start').click()
                page.locator('#record-status').filter(has_text='正在录音').wait_for(timeout=10_000)
                page.wait_for_timeout(1800)
                page.locator('#record-stop').click()
                page.locator('#record-status').filter(has_text='录音完成').wait_for(timeout=10_000)
                if not page.locator('#record-preview').get_attribute('src'):
                    raise RuntimeError('recording preview did not receive an object URL')
                page.locator('#record-save').click()
                for _ in range(200):
                    if (page.locator('#voice-message').text_content()
                            or page.locator('#voice-error').text_content()):
                        break
                    page.wait_for_timeout(100)
                saved_message = page.locator('#voice-message').text_content()
                saved_error = page.locator('#voice-error').text_content()
                if '录音已保存为音色' not in saved_message:
                    raise RuntimeError('recording save failed: ' + json.dumps({
                        'message': saved_message, 'error': saved_error,
                        'status': page.locator('#record-status').text_content(),
                    }, ensure_ascii=False))
                screenshot = report_dir / 'microphone-saved.png'
                page.screenshot(path=str(screenshot), full_page=True)
                browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=5)

        voices = VoiceStore(data)
        selected = voices.selected()
        record = voices.get(selected)
        with wave.open(str(voices.audio_path(selected)), 'rb') as normalized:
            media = {'channels': normalized.getnchannels(), 'sample_width': normalized.getsampwidth(),
                     'sample_rate': normalized.getframerate(),
                     'duration_seconds': normalized.getnframes() / normalized.getframerate()}
        if media['channels'] != 1 or media['sample_width'] != 2 or media['sample_rate'] != 24000:
            raise RuntimeError('saved browser recording was not normalized')
        if not 1 <= media['duration_seconds'] <= 30:
            raise RuntimeError('saved browser recording duration is outside the product contract')

    result = {
        'passed': True, 'voice_id': selected, 'voice_name': record['name'],
        'authorization_type': record['authorization_type'], 'normalized_media': media,
        'preview_created': True, 'saved_and_selected': True, 'screenshot': str(screenshot),
        'scope': 'real browser MediaRecorder with controlled virtual microphone; no human voice quality claim',
    }
    (report_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
