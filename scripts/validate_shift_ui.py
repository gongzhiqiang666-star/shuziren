"""Browser validation for shift configuration, assistant voice and rotation handoff."""

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import uuid
import wave

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore
from scripts.voice_store import VoiceStore


class FakeTTS:
    def __init__(self, runtime, *_args, **_kwargs):
        self.runtime = Path(runtime).resolve()

    def close(self):
        pass

    def state(self):
        return {'status': 'idle'}


class FakeLive:
    active_states = {'preparing', 'running', 'stopping'}
    configured = []

    def __init__(self, _tts, _directory):
        self.value = {'status': 'idle'}

    def start(self, audio_device, **options):
        self.value = {'id': 'shift-browser-scene', 'status': 'running', 'audio_device': audio_device,
                      'frames': 25, 'manual': False, 'revision': 0, **options}
        return self.state()

    def state(self):
        return dict(self.value)

    def configure_rotation(self, session_id, product_ids, **options):
        self.configured.append({'session_id': session_id, 'product_ids': list(product_ids), **options})
        self.value.update(rotation_products=list(product_ids), rotation_completed=0, shift_index=0)
        return self.state()

    def stop(self, session_id):
        if session_id != self.value.get('id'):
            raise ValueError('scene mismatch')
        self.value['status'] = 'stopped'
        return self.state()

    def close(self):
        self.value['status'] = 'stopped'


def add_voice(data, name):
    store = VoiceStore(data)
    voice_id = str(uuid.uuid4())
    directory = store.root / voice_id
    directory.mkdir()
    audio = directory / 'ref_audio.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
        output.writeframes(b'\0\0' * 24000)
    transcript = '这是已授权的浏览器换班验证参考文本。'
    text = directory / 'ref_text.txt'
    text.write_text(transcript, encoding='utf-8')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(store.path) as database, database:
        database.execute('''INSERT INTO voices
            (id,name,transcript,audio_sha256,text_sha256,duration,authorization_type,authorization_reference)
            VALUES(?,?,?,?,?,?,?,?)''',
            (voice_id, name, transcript, digest(audio), digest(text), 1.0, 'self_recorded', '自动化夹具'))
    return voice_id


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    if not args.browser.is_file():
        raise SystemExit('local Chrome is missing')
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    FakeLive.configured.clear()

    with tempfile.TemporaryDirectory(prefix='shift-ui-', ignore_cleanup_errors=True) as temporary:
        data = Path(temporary) / 'data'
        runtime = Path(temporary) / 'runtime'
        runtime.mkdir()
        ConfigStore(data).save({'version': 1, 'runtime_root': str(runtime), 'port': 5158})
        products = ProductStore(data)
        product_ids = []
        for index, title in enumerate(('青瓷杯', '亚麻桌布'), 1):
            product = products.save(title=title, content=title + ' 已核实商品信息。', product_index=index)
            script = products.add_script(product, title + ' 本场讲解稿。')
            products.select_script(product['id'], script)
            product_ids.append(product['id'])
        primary_voice = add_voice(data, '主播甲')
        alternate_voice = add_voice(data, '主播乙')
        VoiceStore(data).select(primary_voice)

        sounddevice = SimpleNamespace(
            query_hostapis=lambda: [{'name': 'Browser Fixture'}],
            query_devices=lambda: [{'name': 'Fixture Output', 'hostapi': 0, 'max_output_channels': 2}],
        )
        with patch.dict(sys.modules, {'sounddevice': sounddevice}), \
                patch('scripts.local_console.ConsoleLive', FakeLive), \
                patch('scripts.local_console.preflight', return_value={'runtime_root': str(runtime)}), \
                patch('scripts.tts_tasks.TTSTasks', FakeTTS):
            server = create_server(ConfigStore(data), port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
                    page = browser.new_page(viewport={'width': 1280, 'height': 1000})
                    page.goto(base, wait_until='networkidle')
                    page.locator('a[href="#live-panel"]').click()
                    page.locator('#live-devices').click()
                    page.locator('#live-audio').select_option('0')
                    page.locator('#live-assistant-voice').select_option(alternate_voice)
                    page.locator('#live-start').click()
                    page.locator('#live-status').filter(has_text='本机输出中').wait_for()
                    page.locator('#live-products').select_option(product_ids)
                    page.locator('#live-shifts-enabled').check()
                    fields = page.locator('#live-shifts fieldset')
                    if fields.count() != 2:
                        raise RuntimeError('shift editor did not render one row per selected product')
                    fields.nth(0).locator('input').fill('0')
                    fields.nth(1).locator('input').fill('2')
                    fields.nth(1).locator('select').select_option(alternate_voice)
                    page.locator('#live-rotation-start').click()
                    page.locator('#live-error').filter(has_text='1 至 86400').wait_for()
                    if FakeLive.configured:
                        raise RuntimeError('invalid shift duration reached the live manager')
                    fields.nth(0).locator('input').fill('1')
                    page.locator('#live-rotation-start').click()
                    page.locator('#live-rotation-status').filter(has_text='第 1 班').wait_for()
                    screenshot = report_dir / 'shift-configuration.png'
                    page.screenshot(path=str(screenshot), full_page=True)
                    browser.close()
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=5)

    configured, = FakeLive.configured
    if configured['product_ids'] != product_ids or configured['shift_durations'] != [1, 2]:
        raise RuntimeError('browser shift values did not reach the live manager')
    if configured['shift_voice_ids'] != [None, alternate_voice]:
        raise RuntimeError('browser shift voice binding did not reach the live manager')
    result = {
        'passed': True, 'products': product_ids, 'primary_voice': primary_voice,
        'assistant_voice': alternate_voice, 'shift_durations': configured['shift_durations'],
        'shift_voice_ids': configured['shift_voice_ids'], 'invalid_duration_rejected_before_api': True,
        'screenshot': str(screenshot), 'scope': 'browser-to-service configuration; no physical audio output',
    }
    (report_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
