"""Explicit GPU avatar warm readiness; intermediate frame latency, no device claim."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import time
import uuid
import wave
from scripts.avatar_store import AvatarStore,digest
from scripts.live_avatar_client import LiveAvatarClient
from scripts.sample_timeline import SampleTimeline


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','source-run','report-directory','seed-cache']:parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    repo=Path(__file__).resolve().parents[1];files=['scripts/resident_avatar.py','scripts/live_avatar_worker.py','scripts/live_avatar_client.py','scripts/validate_avatar_prepare.py']
    report={'status':'failed','checks':{},'device_output_tested':False,'new_tts_tested':False,'source_sha256':{file:digest(repo/file) for file in files}};client=None
    def save():(root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        previous=json.loads((args.source_run/'result.json').read_text(encoding='utf-8'))
        audio=root/'input.wav';shutil.copyfile(previous['audios'][0]['path'],audio)
        with wave.open(str(audio),'rb') as sound:samples=sound.getnframes();pcm_hash=hashlib.sha256(sound.readframes(samples)).hexdigest()
        if pcm_hash!=previous['results'][0]['pcm_sha256']:raise ValueError('Source speech PCM changed')
        store=AvatarStore(args.source_run);avatar=store.directory(store.selected_id());shutil.copytree(args.seed_cache,root/'engine-cache')
        client=LiveAvatarClient(args.runtime_root,avatar,root,root/'engine-cache');session=str(uuid.uuid4())
        initial=client.request('start',session_id=session)
        if initial['model_ready']:raise RuntimeError('Cold start falsely declared model readiness')
        warm=client.request('prepare');again=client.request('prepare')
        if not warm['model_ready'] or warm['reused'] or warm['warmed_batch_sizes']!=[1,2,3,4] or warm['output_generated']:raise RuntimeError('Warmup readiness proof incomplete')
        if not again['reused'] or again['wenet_identity']!=warm['wenet_identity']:raise RuntimeError('Warmup repeated/reloaded model')
        if warm['frame_offset'] or warm['sample_offset']:raise RuntimeError('Warmup advanced timeline')
        if list(root.glob('*.mp4')):raise RuntimeError('Warmup published test media')
        if not client.request('start',session_id=session)['model_ready']:raise RuntimeError('Prepared model was lost on session start')
        clock=SampleTimeline(session);results=[]
        for index in range(2):
            span=clock.reserve(session,samples);events=[];started=time.perf_counter()
            result=client.request('render',session_id=session,task_id='prepared-'+str(index),audio=str(audio),output=str(root/f'clip{index}.mp4'),pcm_sha256=pcm_hash,timing=asdict(span),progress=lambda event:events.append({'at':time.perf_counter(),'event':event}))
            if not events or result['wenet_load_count']!=1 or result['wenet_identity']!=warm['wenet_identity'] or result['unet_session_identity']!=warm['unet_session_identity']:raise RuntimeError('Prepared model was reloaded')
            if result['synthesized_frames']!=span.frames or not result['audio_complete']:raise RuntimeError('Warm frames leaked or audio lost')
            if index==0 and result['source_first']!=0:raise RuntimeError('Warmup changed source frame position')
            results.append({**result,'request_to_encoder_input_seconds':events[0]['at']-started})
        if any(digest(repo/file)!=value for file,value in report['source_sha256'].items()):raise RuntimeError('Code changed during validation')
        report.update(status='passed',warmup=warm,results=results,cache_seeded_from=str(args.seed_cache.resolve()))
        report['checks'].update(cold_start_not_ready=True,warm_model_ready=True,all_batch_sizes_warmed=True,warmup_idempotent=True,no_warm_media=True,no_time_advance=True,actual_model_reuse=True,complete_media=True)
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        if client:client.close()
        report['worker_closed']=client is None or client.process.poll() is not None;save()
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
