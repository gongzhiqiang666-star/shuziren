"""Real restored offline avatar generation; separate from native and live proofs."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

from scripts.v122_acceleration import configure_runtime, accelerated_unet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--avatar-directory', required=True, type=Path)
    parser.add_argument('--audio', required=True, type=Path)
    parser.add_argument('--report-directory', required=True, type=Path)
    parser.add_argument('--backend', choices=['cuda', 'tensorrt'], default='cuda')
    args = parser.parse_args()
    audio = args.audio.resolve(strict=True)
    avatar = args.avatar_directory.resolve(strict=True)
    root = (args.report_directory/('run-'+uuid.uuid4().hex)).resolve()
    root.mkdir(parents=True)
    result = {'status': 'failed', 'provider': 'restored-offline-avatar', 'backend': args.backend,
              'live_tested': False, 'visual_quality_verified': False}
    with (root/'generation.log').open('w', encoding='utf-8') as log, redirect_stdout(log), redirect_stderr(log):
        try:
            internal = configure_runtime(args.runtime_root)
            from recovered.image_clone_video_synthesizer import VideoSynthesizer
            before = hashlib.sha256(audio.read_bytes()).hexdigest()
            models = internal/'assets/pretrained_models'
            output = root/'output.mp4'
            started = time.perf_counter()
            with accelerated_unet(root/'engine-cache', backend=args.backend) as sessions:
                with VideoSynthesizer(avatar, models/'image_infer_v2/unet_v2.onnx',
                    models/'wenet/conf/train_conformer_multi_cn.yaml',
                    models/'wenet/exp/conformer/wenetmodel.pt', device='cuda:0', batch_size=4) as synth:
                    initialized = time.perf_counter()
                    synth.process_single_file(audio, output)
                    stats = synth.engine.perf_stats
                    providers = [session.get_providers() for session in sessions]
            result.update(initialization_seconds=initialized-started, total_seconds=time.perf_counter()-started,
                          providers=providers, synthesis_batches=stats['batches'], synthesized_frames=stats['frames'])
            assert providers and stats['frames'] > 0, 'No actual model inference'
            ffmpeg = internal/'env/ffmpeg/bin/ffmpeg.exe'
            probe = json.loads(subprocess.check_output([str(ffmpeg.with_name('ffprobe.exe')), '-v', 'error',
                '-show_streams', '-show_format', '-of', 'json', str(output)], text=True, timeout=30))
            video = next(item for item in probe['streams'] if item['codec_type']=='video')
            sound = next(item for item in probe['streams'] if item['codec_type']=='audio')
            assert video['avg_frame_rate']=='25/1'
            assert abs(float(video['duration'])-float(sound['duration'])) <= .08
            subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-i', str(output), '-f', 'null', '-'],
                           capture_output=True, check=True, timeout=60)
            assert hashlib.sha256(audio.read_bytes()).hexdigest()==before
            result.update(status='passed', output=str(output), audio_sha256=before,
                frames=int(video['nb_frames']), width=video['width'], height=video['height'],
                video_duration=float(video['duration']), audio_duration=float(sound['duration']),
                full_decode_passed=True, output_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        except Exception as error:
            result.update(error_type=type(error).__name__, error=str(error))
        (root/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'report': str(root/'result.json'), 'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
