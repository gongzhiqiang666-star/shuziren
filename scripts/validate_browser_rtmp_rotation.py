"""Run the real browser RTMP/rotation/receiver validation with owned media processes."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from recovered.srs_runtime import start_bundled_srs, stop_srs_process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--fixture-directory', type=Path, required=True)
    parser.add_argument('--source-video', type=Path, required=True)
    parser.add_argument('--report-directory', type=Path, required=True)
    parser.add_argument('--capture-seconds', type=int, default=35)
    args = parser.parse_args()

    internal = args.runtime_root.resolve() / '_internal'
    ffmpeg = internal / 'env/ffmpeg/bin/ffmpeg.exe'
    python = internal / 'env/python.exe'
    for path in (ffmpeg, python, args.source_video.resolve()):
        if not path.is_file():
            parser.error(f'missing required file: {path}')
    srs = start_bundled_srs(internal)
    if srs is None:
        raise SystemExit('bundled SRS did not start')
    publisher = None
    stream = 'rtmp://127.0.0.1/live/browser-rotation'
    try:
        publisher = subprocess.Popen([
            str(ffmpeg), '-hide_banner', '-loglevel', 'warning', '-re', '-stream_loop', '-1',
            '-i', str(args.source_video.resolve()), '-c:v', 'libx264', '-preset', 'ultrafast',
            '-tune', 'zerolatency', '-an', '-f', 'flv', stream,
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        time.sleep(2)
        if publisher.poll() is not None:
            error = publisher.stderr.read().decode('utf-8', 'replace')
            raise RuntimeError(f'RTMP publisher exited before validation: {error}')
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        command = [
            str(python), str(Path(__file__).with_name('validate_live_orchestration.py')),
            '--runtime-root', str(args.runtime_root.resolve()),
            '--fixture-directory', str(args.fixture_directory.resolve()),
            '--report-directory', str(args.report_directory.resolve()),
            '--cycles', '1', '--interactions', '1', '--capture-seconds', str(args.capture_seconds),
            '--rtmp-url', stream, '--browser-actions',
        ]
        completed = subprocess.run(command, env=environment, check=False)
        if completed.returncode:
            raise SystemExit(completed.returncode)
    finally:
        if publisher is not None and publisher.poll() is None:
            publisher.terminate()
            try:
                publisher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                publisher.kill()
                publisher.wait(timeout=5)
        if publisher is not None and publisher.stderr is not None:
            publisher.stderr.close()
        stop_srs_process(srs)


if __name__ == '__main__':
    main()
