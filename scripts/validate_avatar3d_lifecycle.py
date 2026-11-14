"""Validate that the 3D preview follows the owned live session epoch."""

import argparse
from array import array
import json
import math
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
import wave

from playwright.sync_api import sync_playwright

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore


class FakeTTS:
    def __init__(self, runtime, *_args, **_kwargs): self.runtime = Path(runtime).resolve()
    def state(self): return {'status': 'idle'}
    def close(self): pass


class FakeLive:
    active_states = {'preparing', 'running', 'stopping'}
    instance = None

    def __init__(self, _tts, _directory):
        self.value = {'status': 'idle'}
        FakeLive.instance = self

    def start(self, audio_device, **_options):
        self.value = {'id': 'avatar-scene-1', 'status': 'running', 'lifecycle_epoch': 1,
                      'audio_device': audio_device, 'frames': 1}
        return self.state()

    def state(self): return dict(self.value)
    def close(self): self.value['status'] = 'stopped'


def make_audio(path, seconds=6, sample_rate=24000):
    samples = array('h', (round(7000 * math.sin(2 * math.pi * 260 * index / sample_rate))
                          for index in range(seconds * sample_rate)))
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args(argv)
    report_dir = args.report_dir.resolve(); report_dir.mkdir(parents=True, exist_ok=False)
    runtime = args.runtime_root.resolve()
    with tempfile.TemporaryDirectory(prefix='avatar3d-lifecycle-', ignore_cleanup_errors=True) as temporary:
        root = Path(temporary); data = root / 'data'; audio = root / 'binding.wav'; make_audio(audio)
        ConfigStore(data).save({'version': 1, 'runtime_root': str(runtime), 'port': 5158})
        with patch('scripts.local_console.ConsoleLive', FakeLive), \
                patch('scripts.local_console.preflight', return_value={'runtime_root': str(runtime)}), \
                patch('scripts.tts_tasks.TTSTasks', FakeTTS):
            server = create_server(ConfigStore(data), port=0)
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True,
                        args=['--autoplay-policy=no-user-gesture-required'])
                    page = browser.new_page(viewport={'width': 1280, 'height': 1000})
                    page.goto(base, wait_until='networkidle')
                    token = page.evaluate("fetch('/api/session').then(r=>r.json()).then(v=>v.token)")
                    start = page.evaluate("""async ({token}) => (await fetch('/api/live/start', {
                        method:'POST', headers:{'Content-Type':'application/json','X-Console-Token':token},
                        body:JSON.stringify({audio_device:0})})).json()""", {'token': token})
                    if start.get('session', {}).get('lifecycle_epoch') != 1:
                        raise RuntimeError('live start did not expose lifecycle epoch')
                    page.goto(base + '/avatar3d/', wait_until='domcontentloaded')
                    page.get_by_text('三维人物已载入', exact=True).wait_for(timeout=90_000)
                    page.get_by_label('跟随主直播场次').check()
                    page.get_by_text('状态：running', exact=False).wait_for(timeout=10_000)
                    page.get_by_label('选择测试音频', exact=True).set_input_files(str(audio))
                    play = page.get_by_role('button', name='播放音频与口型', exact=True)
                    play.wait_for(timeout=90_000); page.wait_for_timeout(200)
                    if not play.is_enabled(): raise RuntimeError('bound running session did not allow playback')
                    play.click()
                    for _ in range(100):
                        if page.locator('audio').evaluate('audio => audio.currentTime') > 0.2: break
                        page.wait_for_timeout(100)
                    else: raise RuntimeError('bound preview audio did not start')
                    FakeLive.instance.value.update(status='stopped')
                    page.get_by_text('状态：stopped', exact=False).wait_for(timeout=10_000)
                    stopped = page.locator('audio').evaluate("audio => ({paused:audio.paused,time:audio.currentTime})")
                    if not stopped['paused'] or stopped['time'] != 0 or play.is_enabled():
                        raise RuntimeError('stopped main session did not stop and gate 3D playback')
                    FakeLive.instance.value = {'id': 'avatar-scene-2', 'status': 'running',
                                               'lifecycle_epoch': 2, 'audio_device': 0, 'frames': 1}
                    page.get_by_text('epoch 2', exact=False).wait_for(timeout=10_000)
                    if not play.is_enabled(): raise RuntimeError('new live epoch did not re-enable prepared preview')
                    screenshot = report_dir / 'avatar3d-live-epoch.png'
                    page.screenshot(path=str(screenshot), full_page=True)
                    browser.close()
            finally:
                server.shutdown(); server.server_close(); worker.join(timeout=5)
    result = {'passed': True, 'first_epoch': 1, 'stopped_playback': stopped,
              'replacement_epoch': 2, 'rebind_enabled': True, 'screenshot': str(screenshot),
              'scope': '3D preview lifecycle binding; not production virtual-camera output or OBS acceptance'}
    (report_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
