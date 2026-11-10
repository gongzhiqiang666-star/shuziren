"""Actual GPU raw-frame handoff before whole-utterance completion, no device claim."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import threading
import time
import uuid
import wave
from scripts.avatar_render import verify_media
from scripts.avatar_store import AvatarStore,digest
from scripts.live_avatar_client import LiveAvatarClient
from scripts.live_frame_channel import FrameReceiver
from scripts.raw_video_writer import RawVideoWriter
from scripts.sample_timeline import SampleTimeline


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','source-run','report-directory','seed-cache']:parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    report={'status':'failed','checks':{},'device_output_tested':False,'new_tts_tested':False,'results':[],'phase':'starting'}
    client=receiver=thread=writer=None
    def save():(root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        source=args.source_run.resolve();previous=json.loads((source/'result.json').read_text(encoding='utf-8'))
        audio=root/'input.wav';shutil.copyfile(previous['audios'][0]['path'],audio)
        with wave.open(str(audio),'rb') as sound:samples=sound.getnframes();pcm_hash=hashlib.sha256(sound.readframes(samples)).hexdigest()
        if pcm_hash!=previous['results'][0]['pcm_sha256']:raise ValueError('Source PCM changed')
        avatars=AvatarStore(source);avatar_id=avatars.selected_id();avatar=avatars.get(avatar_id)
        shutil.copytree(args.seed_cache,root/'engine-cache');client=LiveAvatarClient(args.runtime_root,avatars.directory(avatar_id),root,root/'engine-cache')
        clock=SampleTimeline(str(uuid.uuid4()));client.request('start',session_id=clock.session_id)
        report['phase']='preparing';save();report['warmup']=client.request('prepare')
        receiver=FrameReceiver(clock.session_id,avatar['width'],avatar['height'])
        client.request('attach_frames',channel=receiver.descriptor());report['phase']='streaming';save()
        ffmpeg=args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe'
        for index in range(2):
            span=clock.reserve(clock.session_id,samples);done=threading.Event();answers=[];errors=[]
            def request():
                try:answers.append(client.request('stream',session_id=clock.session_id,task_id='raw-'+str(index),audio=str(audio),pcm_sha256=pcm_hash,timing=asdict(span)))
                except BaseException as error:errors.append(str(error))
                finally:done.set()
            writer=RawVideoWriter(ffmpeg,root/f'received{index}.mp4',audio,avatar['width'],avatar['height'])
            started=time.perf_counter();thread=threading.Thread(target=request,name='raw-frame-model-request');thread.start()
            first_seconds=None;first_before_done=None
            for frame_index in range(span.frame_start,span.frame_end):
                frame=receiver.take(timeout=10)
                if frame.frame_index!=frame_index or frame.task_id!='raw-'+str(index):raise RuntimeError('Frame packet crossed task or timing')
                if first_seconds is None:
                    first_seconds=time.perf_counter()-started;first_before_done=not done.is_set()
                    if not first_before_done or not frame.image.any():raise RuntimeError('No real frame before utterance completion')
                writer.write(frame.image)
            writer.release();writer=None;thread.join(timeout=30)
            if thread.is_alive() or errors or len(answers)!=1:raise RuntimeError('Raw worker failed: '+str(errors))
            media=verify_media(audio,root/f'received{index}.mp4',ffmpeg)
            if media['frames']!=span.frames:raise RuntimeError('Received frame count mismatch')
            report['results'].append({'first_raw_frame_seconds':first_seconds,'first_before_utterance_done':first_before_done,'worker':answers[0],'received_media':media});save()
        tiny=root/'tiny.wav'
        with wave.open(str(tiny),'wb') as sound:sound.setparams((1,2,24000,0,'NONE','not compressed'));sound.writeframes(bytes(200))
        span=clock.reserve(clock.session_id,100)
        audio_only=client.request('stream',session_id=clock.session_id,task_id='audio-only',audio=str(tiny),pcm_sha256=hashlib.sha256(bytes(200)).hexdigest(),timing=asdict(span))
        if audio_only['frames'] or not audio_only['audio_only']:raise RuntimeError('Audio-only span fabricated a frame')
        report['audio_only']=audio_only
        # Deliberately stop consumption: the worker must stop at eight credits.
        receiver.full.clear();span=clock.reserve(clock.session_id,samples);failures=[];accepted=[]
        def blocked():
            try:accepted.append(client.request('stream',session_id=clock.session_id,task_id='cancel-raw',audio=str(audio),pcm_sha256=pcm_hash,timing=asdict(span)))
            except BaseException as error:failures.append(str(error))
        thread=threading.Thread(target=blocked,name='raw-credit-backpressure');thread.start()
        if not receiver.full.wait(30):raise TimeoutError('Receiver never reached its bounded credit limit')
        if receiver.frames.qsize()!=8 or not thread.is_alive():raise RuntimeError('Frame credit bound failed')
        stopped=time.perf_counter();receiver.close();thread.join(timeout=15)
        if thread.is_alive() or accepted or not failures:raise RuntimeError('Stopped stream returned a usable result')
        client.close()
        report.update(status='passed',phase='completed',stop_seconds=time.perf_counter()-stopped,
            observed_queue_peak=receiver.peak,worker_closed=client.process.poll() is not None)
        report['checks'].update(raw_pixels_before_file_completion=True,two_utterance_sequence=True,complete_received_media=True,
            queue_credit_limit_eight=True,stop_releases_blocked_worker=True,no_cancelled_result=True,audio_only_has_no_fake_frame=True)
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        if receiver:receiver.close()
        if client:client.close()
        if thread:thread.join(timeout=5)
        if writer:writer.abort()
        save()
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
