"""Bounded real GPU A/B/A reference switching check; no listening claim."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from scripts.voice_store import VoiceStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--source-data', required=True, type=Path)
    parser.add_argument('--second-reference', required=True, type=Path)
    parser.add_argument('--report-directory', required=True, type=Path)
    args = parser.parse_args()
    args.second_reference = args.second_reference.resolve()
    root = (args.report_directory / ('run-' + uuid.uuid4().hex)).resolve()
    root.mkdir(parents=True)
    report = {'status': 'failed', 'outputs': [], 'listening_verified': False,
              'distinct_speaker_verified': False}
    process = None
    timer = None
    with (root / 'worker.log').open('w', encoding='utf-8') as log:
        try:
            ffmpeg = args.runtime_root / '_internal/env/ffmpeg/bin/ffmpeg.exe'
            source = VoiceStore(args.source_data)
            first = source.get(source.selected())
            store = VoiceStore(root)
            a = store.import_audio(source.audio_path(first['id']), first['transcript'], '参考A', ffmpeg)
            b = store.import_audio(args.second_reference,
                args.second_reference.with_name('ref_text.txt').read_text(encoding='utf-8-sig'), '参考B', ffmpeg)
            assert a['audio_sha256'] != b['audio_sha256']
            process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'scripts.tts_worker',
                '--runtime-root', str(args.runtime_root.resolve()), '--data-directory', str(root)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                text=True, encoding='utf-8', bufsize=1)
            timer = threading.Timer(180, process.kill)
            timer.daemon = True
            timer.start()
            assert json.loads(process.stdout.readline())['event'] == 'ready'
            for index, voice in enumerate([a, b, a]):
                request = {'voice_id': voice['id'], 'text': '这是主播的声音测试，请确认这段话清晰完整。',
                           'speed': 1.0, 'language': 'zh-CN', 'use_cache': False}
                process.stdin.write(json.dumps(request, ensure_ascii=False) + '\n')
                process.stdin.flush()
                event = json.loads(process.stdout.readline())
                assert event['ok'], event
                result = event['result']
                assert result['model_load_count'] == 1
                assert result['reference_switch_count'] == index
                assert result['inference_calls'] == index + 1 and not result['cache_hit']
                assert result['voice_id'] == voice['id']
                subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-i', result['output'],
                                '-f', 'null', '-'], check=True, capture_output=True, timeout=30)
                report['outputs'].append(result)
            process.stdin.write('{"action":"close"}\n')
            process.stdin.flush()
            assert process.wait(timeout=15) == 0
            report.update(status='passed', model_load_count=1, reference_order='A/B/A', worker_exit_code=0)
        except Exception as error:
            report['error'] = str(error)
        finally:
            if timer:
                timer.cancel()
            if process and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if process:
                process.stdin.close()
                process.stdout.close()
            (root / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(root / 'result.json'), 'error': report.get('error')}, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
