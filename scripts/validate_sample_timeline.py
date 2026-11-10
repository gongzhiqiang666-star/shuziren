"""Real GPU/media clock accounting; repeated known speech, not live output acceptance."""
import argparse
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid
import wave
from scripts.avatar_render import verify_media
from scripts.avatar_store import AvatarStore,digest
from scripts.live_avatar_client import LiveAvatarClient
from scripts.sample_timeline import SampleTimeline


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','source-run','report-directory','seed-cache']:parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    repo=Path(__file__).resolve().parents[1];files=['scripts/sample_timeline.py','scripts/resident_avatar.py','scripts/live_avatar_worker.py','scripts/live_avatar_client.py','scripts/validate_sample_timeline.py']
    report={'status':'failed','device_output_tested':False,'new_tts_tested':False,'results':[],
        'protocol_sha256':digest(repo/'docs/V05_TIMING_PROTOCOL.md'),'source_sha256':{file:digest(repo/file) for file in files}}
    client=None
    def save():(root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        source=args.source_run.resolve();previous=json.loads((source/'result.json').read_text(encoding='utf-8'))
        audio=root/'input.wav';shutil.copyfile(previous['audios'][0]['path'],audio)
        with wave.open(str(audio),'rb') as sound:samples=sound.getnframes();pcm=sound.readframes(samples)
        pcm_hash=hashlib.sha256(pcm).hexdigest()
        if pcm_hash!=previous['results'][0]['pcm_sha256']:raise ValueError('Source PCM changed')
        store=AvatarStore(source);avatar=store.directory(store.selected_id());shutil.copytree(args.seed_cache,root/'engine-cache')
        clock=SampleTimeline(str(uuid.uuid4()));client=LiveAvatarClient(args.runtime_root,avatar,root,root/'engine-cache');client.request('start',session_id=clock.session_id)
        ffmpeg=args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe'
        def run(arguments):subprocess.run([str(ffmpeg),'-nostdin','-v','error','-y',*map(str,arguments)],check=True,capture_output=True,timeout=60)
        with wave.open(str(root/'all.wav'),'wb') as combined:
            combined.setparams((1,2,24000,0,'NONE','not compressed'))
            for index in range(10):
                span=clock.reserve(clock.session_id,samples)
                result=client.request('render',session_id=clock.session_id,task_id='clock-'+str(index),audio=str(audio),output=str(root/f'clip{index:02}.mp4'),pcm_sha256=pcm_hash,timing=asdict(span))
                if result['frames']!=span.frames or result['frame_offset']!=span.frame_start or result['next_frame_offset']!=span.frame_end:raise RuntimeError('Rendered frame range differs from audio clock')
                if not result['audio_complete']:raise RuntimeError('Audio shortened')
                combined.writeframesraw(pcm);report['results'].append(result);save()
                run(['-i',result['output'],'-map','0:v:0','-c:v','copy','-an',root/f'v{index:02}.mp4'])
        manifest=root/'videos.txt';manifest.write_text(''.join(f"file 'v{index:02}.mp4'\n" for index in range(10)),encoding='utf-8')
        run(['-f','concat','-safe','1','-i',manifest,'-i',root/'all.wav','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-movflags','+faststart',root/'combined.mp4'])
        media=verify_media(root/'all.wav',root/'combined.mp4',ffmpeg)
        frames=json.loads(subprocess.check_output([str(ffmpeg.with_name('ffprobe.exe')),'-v','error','-select_streams','v','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(root/'combined.mp4')],timeout=60))['frames']
        if len(frames)!=clock.frames or media['frames']!=clock.frames:raise RuntimeError('Combined frame count differs')
        if any(abs(Decimal(frame['best_effort_timestamp_time'])-Decimal(index)/25)>Decimal('.000001') for index,frame in enumerate(frames)):raise RuntimeError('Combined PTS gap or duplicate')
        if any(digest(repo/file)!=value for file,value in report['source_sha256'].items()):raise RuntimeError('Source changed during validation')
        error_samples=clock.frames*960-clock.samples
        if abs(error_samples)>480:raise RuntimeError('Global quantization drift')
        report.update(status='passed',combined=media,total_samples=clock.samples,total_frames=clock.frames,
            boundary_error_samples=error_samples,boundary_error_ms=error_samples/24,
            independently_rounded_frames=sum(item['native_feature_frames'] for item in report['results']),
            corrected_utterances=sum(item['native_feature_frames']!=item['frames'] for item in report['results']),
            pts_grid_verified=True,cache_seeded_from=str(args.seed_cache.resolve()),
            combined_sha256=digest(root/'combined.mp4'))
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        if client:client.close()
        report['worker_closed']=client is None or client.process.poll() is not None;save()
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
