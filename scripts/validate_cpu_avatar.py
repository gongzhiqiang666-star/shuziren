"""Run a short real WeNet + ONNX avatar render on one explicit device."""

import argparse
import json
from pathlib import Path
import subprocess
import time

from scripts.v122_acceleration import configure_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--avatar', required=True, type=Path)
    parser.add_argument('--audio', required=True, type=Path)
    parser.add_argument('--report-dir', required=True, type=Path)
    parser.add_argument('--device', choices=('cpu', 'cuda:0'), default='cpu')
    parser.add_argument('--batch-size', type=int, default=1)
    args = parser.parse_args()
    runtime = args.runtime_root.resolve(strict=True)
    avatar = args.avatar.resolve(strict=True)
    audio = args.audio.resolve(strict=True)
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=False)
    if args.batch_size < 1 or args.batch_size > 16:
        raise ValueError('batch size must be between 1 and 16')
    internal = configure_runtime(runtime)

    from recovered.image_clone_video_synthesizer import VideoSynthesizer

    models = internal / 'assets/pretrained_models'
    output = report_dir / 'device-avatar.mp4'
    started = time.perf_counter()
    with VideoSynthesizer(
        avatar, models / 'image_infer_v2/unet_v2.onnx',
        models / 'wenet/conf/train_conformer_multi_cn.yaml',
        models / 'wenet/exp/conformer/wenetmodel.pt',
        device=args.device, batch_size=args.batch_size,
    ) as synthesizer:
        synthesizer.process_single_file(audio, output)
        timings = synthesizer.last_process_timings
        providers = synthesizer.engine.session.get_providers()
    elapsed = time.perf_counter() - started
    ffmpeg = internal / 'env/ffmpeg/bin/ffmpeg.exe'
    ffprobe = internal / 'env/ffmpeg/bin/ffprobe.exe'
    probe = subprocess.run([
        str(ffprobe), '-v', 'error', '-show_entries',
        'stream=index,codec_type,codec_name,width,height,avg_frame_rate,duration',
        '-of', 'json', str(output),
    ], check=True, capture_output=True, text=True, timeout=30)
    decode = subprocess.run([
        str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(output),
        '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-',
    ], capture_output=True, text=True, timeout=max(60, int(elapsed * 2)))
    if decode.returncode:
        raise RuntimeError(decode.stderr[-1000:])
    streams = json.loads(probe.stdout)['streams']
    if {stream['codec_type'] for stream in streams} != {'video', 'audio'}:
        raise RuntimeError('CPU avatar output does not contain video and audio')
    video = next(stream for stream in streams if stream['codec_type'] == 'video')
    report = {
        'passed': True,
        'scope': 'short explicit-device compatibility render; not long-run release evidence',
        'device': args.device,
        'batch_size': args.batch_size,
        'providers': providers,
        'elapsed_seconds': elapsed,
        'media': streams,
        'video_fps': video['avg_frame_rate'],
        'timings': timings,
        'complete_decode': True,
        'output': str(output),
    }
    (report_dir / 'result.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
