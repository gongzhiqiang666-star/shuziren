"""Exercise V06 controls against a real Windows console and virtual devices."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.local_console import create_server
from scripts.local_console_config import ConfigStore
from scripts.product_store import ProductStore
from scripts.received_voice_audit import DeviceCapture
from scripts.voice_store import VoiceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--fixture-directory', type=Path, required=True)
    parser.add_argument('--report-directory', type=Path, required=True)
    parser.add_argument('--tts-engine', choices=('indextts', 'zipvoice', 'omnivoice'), default='indextts')
    parser.add_argument('--tts-model-root', type=Path)
    parser.add_argument('--assistant-voice-data', type=Path, help='Data directory containing a selected co-host reference')
    parser.add_argument('--assistant-voice-id', help='Use this reference instead of the selection in that directory')
    parser.add_argument('--legacy-assistant-script', action='store_true')
    parser.add_argument('--revise-legacy-assistant', action='store_true')
    parser.add_argument('--timed-shifts', action='store_true', help='Exercise timed host shifts after manual takeover')
    parser.add_argument('--shift-count', type=int, default=2, help='Number of timed transitions to verify')
    parser.add_argument('--rotation-language', choices=('zh-CN', 'ms-MY', 'vi-VN'), default='zh-CN')
    parser.add_argument('--cycles', type=int, default=20)
    parser.add_argument('--interactions', type=int, default=None, help='Set to 0 to exercise start/stop only')
    parser.add_argument('--capture-seconds', type=int, default=35)
    parser.add_argument('--capture-buffer-mb', type=int, default=16)
    parser.add_argument('--camera-device', help='Require this explicit virtual camera for rotation')
    parser.add_argument('--camera-input', default='C920', help='Exact DirectShow video input name')
    parser.add_argument('--rtmp-url', help='Use an RTMP driving source matching the fixture dimensions')
    parser.add_argument('--browser-actions', action='store_true',
                        help='Start the first scene, configure its first rotation, and stop it through Chrome')
    parser.add_argument('--browser', type=Path,
                        default=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe'))
    args = parser.parse_args()
    if args.capture_buffer_mb < 1:
        parser.error('--capture-buffer-mb must be positive')
    interactions = args.cycles if args.interactions is None else args.interactions
    if args.cycles < 1 or interactions < 0 or args.capture_seconds < 1:
        parser.error('Cycle and capture lengths must be positive')
    if args.rotation_language != 'zh-CN' and args.tts_engine != 'omnivoice':
        parser.error('Multilingual rotation requires OmniVoice')
    if args.assistant_voice_data and args.rotation_language != 'zh-CN':
        parser.error('The co-host test fixture uses Chinese scripts')
    if args.assistant_voice_id and not args.assistant_voice_data:
        parser.error('--assistant-voice-id requires --assistant-voice-data')
    if args.revise_legacy_assistant and not args.legacy_assistant_script:
        parser.error('--revise-legacy-assistant requires --legacy-assistant-script')
    if args.legacy_assistant_script and (not args.assistant_voice_data or not interactions or args.timed_shifts):
        parser.error('--legacy-assistant-script requires a co-host, interactions and untimed rotation')
    if args.timed_shifts and (not args.assistant_voice_data or not interactions):
        parser.error('--timed-shifts requires a second reference and at least one interaction')
    if args.shift_count < 1:
        parser.error('--shift-count must be positive')
    if args.browser_actions and not args.browser.is_file():
        parser.error('Chrome executable is missing')

    directory = args.report_directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    fixture = args.fixture_directory
    for source, target in [('avatars', 'avatars'), ('voices', 'voices'), ('engine-cache', 'live-avatar-cache')]:
        source_path = fixture / source
        if source == 'engine-cache' and not source_path.is_dir():
            source_path = fixture / target
        shutil.copytree(source_path, directory / target)
    shutil.copy2(fixture / 'products.sqlite3', directory / 'products.sqlite3')
    products = ProductStore(directory)
    product_id = products.selected()
    product = products.get(product_id)
    first_text, second_text = {
        'zh-CN': ('优先播报验证。', '第二件商品，轮播验证。'),
        'ms-MY': ('Selamat datang. Ini produk pertama.', 'Ini produk kedua.'),
        'vi-VN': ('Xin chào, đây là sản phẩm thứ nhất.', 'Đây là sản phẩm thứ hai.'),
    }[args.rotation_language]
    first_script = products.add_script(product, first_text)
    previous_script = products.add_script(product, '准备包审核切换验证。')
    products.select_script(product_id, previous_script)
    existing_indices = {item['product_index'] for item in products.list()}
    second_index = next(index for index in range(1, len(existing_indices) + 2) if index not in existing_indices)
    if args.legacy_assistant_script:
        from scripts.console_data_migration import import_v122_products

        template = directory / 'legacy-assistant-fixture.json'
        template.write_text(json.dumps({'product_scripts': [{
            'product_index': second_index, 'title': '轮播验收商品',
            'scripts': [{'type': 'assistant', 'text': second_text}],
        }]}), encoding='utf-8')
        imported, = import_v122_products(directory, template)
        second = products.get(imported['product_id'])
        second_script, = imported['script_ids']
        if args.revise_legacy_assistant:
            second_text += '以上是助播更新的商品介绍。'
            second_script = products.add_script(second, second_text, parent_script_id=second_script)
    else:
        second = products.save(title='轮播验收商品', content='本机验收使用', product_index=second_index)
        if args.assistant_voice_data:
            second_text += '{停:1}{助:大家好，我是助播。}'
        second_script = products.add_script(second, second_text)
    products.select_script(second['id'], second_script)
    products.save_live_preparation(product_ids=[product_id, second['id']])
    voices = VoiceStore(directory)
    voice = voices.selected()
    assistant = None
    if args.assistant_voice_data:
        source = VoiceStore(args.assistant_voice_data)
        reference_id = args.assistant_voice_id or source.selected()
        reference = source.get(reference_id)
        if reference['audio_sha256'] == voices.get(voice)['audio_sha256']:
            parser.error('Host and co-host must have distinct reference audio')
        ffmpeg = args.runtime_root / '_internal/env/ffmpeg/bin/ffmpeg.exe'
        assistant = voices.import_audio(source.audio_path(reference_id), reference['transcript'], '助播验收音色', ffmpeg)['id']

    store = ConfigStore(directory)
    store.save({'version': 1, 'port': 5158, 'runtime_root': str(args.runtime_root.resolve())})
    server = create_server(store, port=0, tts_engine=args.tts_engine, tts_model_root=args.tts_model_root)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    address = f'http://127.0.0.1:{server.server_port}'
    token = None
    capture = None
    playwright = browser = page = None
    report = {'status': 'running', 'requested_starts': args.cycles, 'requested_interactions': interactions,
              'tts_engine': args.tts_engine, 'rotation_language': args.rotation_language,
              'assistant_voice_configured': assistant is not None,
              'starts': [], 'interactions': [], 'rotation': []}

    def save():
        (directory / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    def call(path, data=None, expected=200):
        headers = {'Origin': address, 'Content-Type': 'application/json', 'X-Console-Token': token} if data is not None else {}
        request = Request(address + path, headers=headers, data=json.dumps(data).encode() if data is not None else None)
        try:
            response = urlopen(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            result = json.load(response)
            if response.code != expected:
                raise RuntimeError(f'{path}: HTTP {response.code}: {result}')
            return result

    def wait(path, key, predicate):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = call(path)[key]
            if state and (state['status'] == 'failed' or state.get('rotation_error')):
                raise RuntimeError(str(state))
            if state and predicate(state):
                return state
            time.sleep(.1)
        raise TimeoutError(path)

    def live(predicate):
        return wait('/api/live/state', 'session', predicate)

    def speech():
        task = call('/api/tts/generate', {'product_id': product_id, 'script_id': first_script,
            'voice_id': voice, 'speed': 1, 'language': args.rotation_language, 'use_cache': True}, 202)['task']
        wait('/api/tts/state', 'task', lambda state: state['id'] == task['id'] and state['status'] == 'succeeded')
        return task['id']

    def rotate(session_id, *, exercise_pause=False, through_browser=False):
        prepared = call('/api/live/preparation/rotation', {'revision': preparation_revision})
        items = [{key: item[key] for key in ('product_id', 'product_version', 'script_id')}
                 for item in prepared['items']]
        if through_browser:
            page.locator('#live-products').select_option([product_id, second['id']])
            page.locator('#live-rotation-start').click()
            live(lambda value: value.get('rotation_products') == [product_id, second['id']])
            page.screenshot(path=str(directory / 'browser-rtmp-rotation.png'), full_page=True)
            report['browser_rotation_configured'] = True
        else:
            call('/api/live/rotation', {'session_id': session_id, 'product_ids': [product_id, second['id']],
                                        'preparation': {'revision': prepared['revision'], 'items': items}})
        sequence = [product_id, second['id']]
        for count, product in enumerate(sequence, 1):
            state = live(lambda value: value.get('rotation_completed', 0) >= count)
            if state['last_rotation_product_id'] != product:
                raise RuntimeError('Rotation order changed')
            report['rotation'].append(state)
            if count == 1 and exercise_pause:
                manual = call('/api/live/control', {'session_id': session_id, 'manual': True,
                    'revision': state['control_revision']})['session']
                wait('/api/tts/state', 'task', lambda value: value['status'] != 'running')
                task_id = speech()
                call('/api/live/speak', {'session_id': session_id, 'task_id': task_id,
                    'revision': manual['control_revision']}, 202)
                paused = live(lambda value: value.get('last_completed_task_id') == task_id)
                completed = paused['rotation_completed']
                if not paused['manual'] or completed not in {1, 2}:
                    raise RuntimeError('Rotation continued scheduling during manual takeover')
                call('/api/live/control', {'session_id': session_id, 'manual': False,
                    'revision': manual['control_revision']})
                resumed = live(lambda value: value.get('rotation_completed', 0) > completed)
                if resumed['last_rotation_product_id'] != sequence[completed % len(sequence)]:
                    raise RuntimeError('Rotation cursor changed during takeover')
                report['rotation_resume'] = {'paused': paused, 'resumed': resumed}
                break
        call('/api/live/rotation', {'session_id': session_id, 'product_ids': []})
        # A synthesis already started by rotation may finish after it is disabled.
        wait('/api/tts/state', 'task', lambda value: value['status'] != 'running')

    try:
        token = call('/api/session')['token']
        route = '/api/live/preparation'
        previous_revision = call(route + '/package')['revision']
        call(route + '/review', {'revision': previous_revision, 'review': '旧话术验收'})
        products.select_script(product_id, first_script)
        call(route + '/rotation', {'revision': previous_revision}, expected=409)
        preparation_revision = call(route + '/package')['revision']
        call(route + '/rotation', {'revision': preparation_revision}, expected=409)
        review_text = '本机轮播验收'
        call(route + '/review', {'revision': preparation_revision, 'review': review_text})
        review_digest = hashlib.sha256(review_text.encode('utf-8')).hexdigest()
        report['preparation_review_refresh_verified'] = True
        device = next(item for item in call('/api/live/devices')['devices']
                      if 'CABLE Input' in item['name'] and 'WASAPI' in item['host'])
        report['device'] = device
        if args.browser_actions:
            from playwright.sync_api import sync_playwright
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(executable_path=str(args.browser), headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.goto(address, wait_until='networkidle')
            page.locator('a[href="#live-panel"]').click()
            page.locator('#live-devices').click()
            page.locator('#live-audio').select_option(str(device['id']))
            if args.rtmp_url:
                page.locator('#live-rtmp-url').fill(args.rtmp_url)
        old_session = None
        for cycle in range(args.cycles):
            if args.browser_actions and cycle == 0:
                page.locator('#live-start').click()
                running = live(lambda state: state['status'] == 'running')
                session_id = running['id']
                report['browser_start_verified'] = running.get('input_mode') == ('rtmp' if args.rtmp_url else 'camera')
            else:
                session_id = call('/api/live/start', {
                    'audio_device': device['id'], 'rotation_language': args.rotation_language,
                    'assistant_voice_id': assistant,
                    **({'rtmp_url': args.rtmp_url} if args.rtmp_url else {}),
                    **({'camera_device': args.camera_device} if args.camera_device else {}),
                }, 202)['session']['id']
            running = live(lambda state: state['id'] == session_id and state['status'] == 'running')
            if args.camera_device:
                assert running['requested_camera_device'] == running['camera_device'] == args.camera_device
                report['camera_device'] = running['camera_device']
            if old_session:
                call('/api/live/stop', {'session_id': old_session}, 409)
            if cycle == 0 and interactions:
                live(lambda state: state['id'] == session_id and state.get('camera_frames', 0) > 0)
                ffmpeg = args.runtime_root / '_internal/env/ffmpeg/bin/ffmpeg.exe'
                report['capture_buffer_mb'] = args.capture_buffer_mb
                capture = DeviceCapture(ffmpeg, directory, args.capture_seconds, dshow_video_clock=True,
                                        buffer_mb=args.capture_buffer_mb,camera_input=args.camera_input)
                rotate(session_id, exercise_pause=True, through_browser=args.browser_actions and cycle == 0)
                for interaction in range(interactions):
                    urgent = speech()
                    call('/api/live/insert', {'session_id': session_id, 'task_id': urgent}, 202)
                    state = live(lambda value: value.get('last_completed_task_id') == urgent)
                    manual = call('/api/live/control', {'session_id': session_id, 'manual': True,
                        'revision': state['control_revision']})['session']
                    task_id = speech()
                    payload = {'session_id': session_id, 'task_id': task_id, 'revision': manual['control_revision']}
                    call('/api/live/speak', payload, 202)
                    live(lambda value: value.get('last_completed_task_id') == task_id)
                    resumed = call('/api/live/control', {'session_id': session_id, 'manual': False,
                        'revision': manual['control_revision']})['session']
                    if resumed['manual'] or resumed['id'] != session_id:
                        raise RuntimeError('Resume changed the live session')
                    call('/api/live/speak', payload, 409)
                    report['interactions'].append({'cycle': interaction + 1, 'urgent': urgent, 'manual': task_id,
                                                   'resumed_revision': resumed['control_revision']})
                    save()
                    print(f'V06 interaction {interaction + 1}/{interactions}', flush=True)
                if args.timed_shifts:
                    call('/api/live/rotation', {
                        'session_id': session_id, 'product_ids': [product_id, second['id']],
                        'shift_durations': [12, 12], 'shift_voice_ids': [None, assistant],
                    })
                    report['timed_shifts'] = []
                    report['requested_shift_transitions'] = args.shift_count
                    for step in range(args.shift_count + 1):
                        index = step % 2
                        expected_product = (product_id, second['id'])[index]
                        completed = live(lambda value: value.get('shift_index') == index
                                         and value.get('last_rotation_product_id') == expected_product)
                        report['timed_shifts'].append(completed)
                        save()
                    call('/api/live/rotation', {'session_id': session_id, 'product_ids': []})
                else:
                    rotate(session_id)
                capture.process.wait(timeout=args.capture_seconds + 10)
                capture.wait()
                report['capture'] = str(capture.path)
                report['capture_buffer_drop_reported'] = capture.reported_buffer_drop()
                subprocess.run([
                    str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(capture.path),
                    '-map', '0:v:0', '-map', '0:a:0', '-fps_mode', 'passthrough',
                    '-enc_time_base:v', '1:1000', '-f', 'null', '-',
                ], check=True, timeout=max(30, args.capture_seconds + 10))
                report['capture_decode_verified'] = True
            if args.browser_actions and cycle == 0:
                page.locator('#live-stop').click()
                report['browser_stop_dispatched'] = True
            else:
                call('/api/live/stop', {'session_id': session_id})
            stopped = live(lambda state: state['id'] == session_id and state['status'] == 'stopped')
            if cycle == 0 and interactions:
                controls = call(f'/api/live/control/events?session_id={session_id}')['events']
                if (stopped.get('session_event_error')
                        or [event['manual'] for event in controls] != [True, False] * (interactions + 1)
                        or [event['revision'] for event in controls] != list(range(1, len(controls) + 1))):
                    raise RuntimeError('Control event history did not match manual takeover and resume')
                report['control_event_count'] = len(controls)
                events = []
                cursor = 0
                while True:
                    page = call(f'/api/live/rotation/events?session_id={session_id}&after={cursor}')
                    history = page['session']
                    if (not history or history['status'] != 'stopped' or history['frames'] != stopped['frames']
                            or not history['requested_at'] <= history['started_at'] <= history['ended_at']):
                        raise RuntimeError('Persisted live session did not match stopped session')
                    if not page['events']:
                        break
                    if page['next_cursor'] <= cursor:
                        raise RuntimeError('Rotation event cursor did not advance')
                    cursor = page['next_cursor']
                    events.extend(page['events'])
                expected_scripts = {
                    product_id: (product['version'], first_script),
                    second['id']: (second['version'], second_script),
                }
                if (stopped.get('rotation_event_error')
                        or {event['product_id'] for event in events} != expected_scripts.keys()
                        or len({event['task_id'] for event in events}) != len(events)
                        or any(event['session_id'] != session_id or not event['completed_at']
                               or (event['product_version'], event['script_id']) != expected_scripts[event['product_id']]
                               for event in events)):
                    raise RuntimeError('Rotation event history did not match completed playback')
                previous_end = 0
                for event in events:
                    start, end = event['sample_start'], event['sample_end']
                    if type(start) is not int or type(end) is not int or not previous_end <= start < end:
                        raise RuntimeError('Rotation event PCM intervals are missing or out of order')
                    previous_end = end
                report['rotation_event_count'] = len(events)
                report['rotation_event_last_sample'] = previous_end
                scene_report = call(f'/api/live/report?session_id={session_id}')
                reported_scripts = {
                    row['product_id']: (row['product_version'], row['script_id'])
                    for row in scene_report['products']
                }
                if reported_scripts != expected_scripts:
                    raise RuntimeError('Session report did not match the reviewed rotation scripts')
                applications = scene_report['preparation_applications']
                if not any(
                    entry['revision'] == preparation_revision
                    and entry.get('review_digest') == review_digest
                    and {item['product_id']: (item['product_version'], item['script_id'])
                         for item in entry['items']} == expected_scripts
                    for entry in applications
                ):
                    raise RuntimeError('Session report did not match the applied preparation revision and review')
                report['session_report_verified'] = True
                if args.legacy_assistant_script:
                    for event in events:
                        source = call(f"/api/live/content-source?session_id={session_id}&task_id={event['task_id']}")['source']
                        expected_voice = assistant if event['product_id'] == second['id'] else voice
                        if source['voice_id'] != expected_voice:
                            raise RuntimeError('Legacy assistant role did not use the assigned reference')
                        if args.revise_legacy_assistant and event['product_id'] == second['id']:
                            if (source['script_id'] != second_script or source['segment']['type'] != 'assistant'
                                    or source['segment']['content'] != second_text):
                                raise RuntimeError('Revised co-host script did not match playback provenance')
                    report['legacy_assistant_voice_verified'] = True
                    if args.revise_legacy_assistant:
                        report['revised_legacy_assistant_verified'] = True
            report['starts'].append({'cycle': cycle + 1, 'session': session_id, 'frames': stopped['frames']})
            old_session = session_id
            save()
            print(f'V06 start/stop {cycle + 1}/{args.cycles}', flush=True)
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        save()
        if capture:
            capture.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
