"""Validate push/pull against an already-owned local SRS without stopping it."""

import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    ffmpeg = args.ffmpeg.resolve(strict=True)
    with urllib.request.urlopen('http://127.0.0.1:1985/api/v1/versions', timeout=3) as response:
        api = json.load(response)
    stream = 'supplement-' + uuid.uuid4().hex
    publisher = subprocess.Popen([
        str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-re',
        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=25',
        '-f', 'lavfi', '-i', 'sine=frequency=1000:sample_rate=44100',
        '-t', '5', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-c:a', 'aac', '-f', 'flv', f'rtmp://127.0.0.1/live/{stream}',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        time.sleep(1.5)
        pull = subprocess.run([
            str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-rw_timeout', '5000000',
            '-i', f'http://127.0.0.1:8080/live/{stream}.flv', '-t', '1',
            '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', 'NUL',
        ], capture_output=True, timeout=10)
        if pull.returncode:
            raise RuntimeError(pull.stderr.decode('utf-8', 'replace')[-1000:])
    finally:
        if publisher.poll() is None:
            publisher.terminate()
            try:
                publisher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                publisher.kill()
                publisher.wait(timeout=5)
        if publisher.stderr:
            publisher.stderr.close()
    report = {
        'passed': True, 'scope': 'existing owned SRS; lifecycle stop not exercised',
        'api_code': api.get('code'), 'stream': stream,
        'rtmp_publish': True, 'http_flv_pull': True, 'audio_video_decode': True,
        'publisher_exit': publisher.returncode,
    }
    destination = args.report.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
