"""Run sustained product rotation against Windows virtual devices and sample resources."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

import psutil

from scripts.console_live import ConsoleLive
from scripts.product_store import Conflict, ProductStore
from scripts.tts_tasks import TTSTasks


def gpu_resources():
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,utilization.gpu',
                                 '--format=csv,noheader,nounits'], capture_output=True, text=True,
                                check=True, timeout=1, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return [{'index': int(index), 'used_mib': int(memory), 'utilization_percent': int(usage)}
                for index, memory, usage in (line.split(',') for line in result.stdout.splitlines())]
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--fixture-directory', type=Path, required=True)
    parser.add_argument('--report-directory', type=Path, required=True)
    parser.add_argument('--audio-device', type=int, required=True)
    parser.add_argument('--seconds', type=int, default=28800)
    parser.add_argument('--device-buffer-frames', type=int, choices=(2, 4), default=2)
    parser.add_argument('--verify-worker-recovery', action='store_true',
                        help='Terminate this run’s avatar worker and restart the scene before sampling')
    args = parser.parse_args()
    if args.seconds < 1:
        parser.error('Duration must be positive')

    directory = args.report_directory.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    for source, target in [('avatars', 'avatars'), ('voices', 'voices'), ('engine-cache', 'live-avatar-cache')]:
        shutil.copytree(args.fixture_directory / source, directory / target)
    shutil.copy2(args.fixture_directory / 'products.sqlite3', directory / 'products.sqlite3')
    products = ProductStore(directory)
    primary_id = products.selected()
    primary = products.get(primary_id)
    primary_script = products.add_script(primary, '这是第一件商品，现在测试持续直播中的语音和数字人画面。')
    products.select_script(primary_id, primary_script)
    second = products.save(title='长稳验证商品', content='仅用于本机测试', product_index=999)
    second_script = products.add_script(second, '这是第二件商品。场次将按顺序继续轮播。')
    products.select_script(second['id'], second_script)

    tts = TTSTasks(args.runtime_root, directory)
    live = ConsoleLive(tts, directory, device_buffer_frames=args.device_buffer_frames)
    process = psutil.Process()
    process_cache = {}
    report = {'status': 'preparing', 'runner_pid': process.pid, 'requested_seconds': args.seconds, 'workload': 'two-product cached rotation',
              'capture_verified': False, 'faults_tested': False, 'samples': 0,
              'device_buffer_frames': args.device_buffer_frames}

    def save():
        temp = directory / 'result.tmp'
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(directory / 'result.json')

    def resources():
        processes = {item.pid: process_cache.get(item.pid, item) for item in [process, *process.children(recursive=True)]}
        process_cache.clear()
        process_cache.update(processes)
        rss, cpu = 0, 0.
        for item in processes.values():
            try:
                rss += item.memory_info().rss
                cpu += item.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return {'process_count': len(processes), 'process_tree_rss_bytes': rss, 'process_tree_cpu_percent': cpu}

    def wait_for(status, timeout):
        deadline = time.monotonic() + timeout
        while True:
            current = live.state()
            if current['status'] == status:
                return current
            if current['status'] in {'failed', 'stopped'} or time.monotonic() >= deadline:
                raise RuntimeError(f'Live session did not reach {status}: {current}')
            time.sleep(.1)

    def recover_worker(session):
        with live.lock:
            if live.client is None or live.client.process.poll() is not None:
                raise RuntimeError('No active avatar worker owned by this scene')
            worker = live.client.process
            injected = time.monotonic()
            worker.terminate()
        worker.wait(timeout=10)
        failed = wait_for('failed', 30)
        failure_seconds = time.monotonic() - injected
        replacement = live.start(args.audio_device)
        recovered = wait_for('running', 360)
        if replacement['id'] == session['id'] or recovered['id'] != replacement['id']:
            raise RuntimeError('Restart did not create a new scene')
        try:
            live.stop(session['id'])
        except Conflict:
            pass
        else:
            raise RuntimeError('Previous scene control survived restart')
        report['worker_recovery'] = {'terminated_pid': worker.pid, 'exit_code': worker.returncode,
                                     'failed': failed, 'recovered': recovered, 'failure_seconds': failure_seconds,
                                     'total_recovery_seconds': time.monotonic() - injected}
        report['faults_tested'] = True
        save()
        return replacement, recovered

    try:
        session = live.start(args.audio_device)
        save()
        state = wait_for('running', 360)
        if args.verify_worker_recovery:
            session, state = recover_worker(session)
        live.configure_rotation(session['id'], [primary_id, second['id']])
        started = time.monotonic()
        deadline = started + args.seconds
        tick = started
        last_frames = state['frames']
        last_progress = started
        report['status'] = 'running'
        with (directory / 'samples.jsonl').open('w', encoding='utf-8', buffering=1) as trace:
            while True:
                time.sleep(max(0, tick - time.monotonic()))
                now = time.monotonic()
                state = live.state()
                report['last_state'] = state
                if state['status'] != 'running' or state.get('rotation_error'):
                    raise RuntimeError(f'Live output interrupted: {state}')
                if state['frames'] > last_frames:
                    last_frames = state['frames']
                    last_progress = now
                if now - last_progress > 5:
                    report['stall'] = {
                        'seconds_without_progress': now - last_progress,
                        'last_frame': last_frames,
                        **live.stall_snapshot(),
                    }
                    raise RuntimeError('No output frame progress for five seconds')
                wavs = list((directory / 'tts').glob('*.wav'))
                wav_sizes = []
                for wav in wavs:
                    try:
                        wav_sizes.append(wav.stat().st_size)
                    except FileNotFoundError:
                        continue
                sample = {'elapsed_seconds': now - started, 'frames': state['frames'],
                          'pending': state.get('pending'), 'completed': state.get('rotation_completed'),
                          'tts_wav_count': len(wav_sizes), 'tts_wav_bytes': sum(wav_sizes),
                          **resources(), 'gpu': gpu_resources()}
                trace.write(json.dumps(sample, ensure_ascii=False) + '\n')
                report['samples'] += 1
                report['last_sample'] = sample
                if report['samples'] % 10 == 1:
                    save()
                if now >= deadline:
                    break
                tick = min(deadline, max(tick + 1, time.monotonic()))
        if not state.get('rotation_completed'):
            raise RuntimeError('No spoken item completed')
        live.stop(session['id'])
        live.close()
        report['last_state'] = live.state()
        if report['last_state']['status'] != 'stopped':
            raise RuntimeError('Live output did not stop cleanly')
        report['status'] = 'completed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        save()
        raise
    finally:
        try:
            live.close()
            tts.close()
        finally:
            save()


if __name__ == '__main__':
    main()
