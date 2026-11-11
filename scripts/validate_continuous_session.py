"""Timed GPU idle -> newly generated speech -> idle in one continuous mux."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
import uuid
import wave
import numpy as np
from scripts.avatar_render import verify_media
from scripts.avatar_store import AvatarStore
from scripts.continuous_av_sink import ContinuousAVSink
from scripts.live_av_device_sink import AVDeviceSink
from scripts.received_voice_audit import CounterDeviceSink,DeviceCapture,audit_received_voice
from scripts.continuous_session import ContinuousSession
from scripts.live_avatar_client import LiveAvatarClient
from scripts.live_frame_channel import FrameReceiver
from scripts.live_speech_ingress import LiveSpeechIngress
from scripts.product_store import ProductStore
from scripts.speech_assembler import SpeechAssembler
from scripts.tts_tasks import TTSTasks
from scripts.validate_render_tasks import wait
from scripts.voice_store import VoiceStore


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','source-voice-data','source-avatar-directory','report-directory','seed-cache']:parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--seconds',type=int,default=20)
    parser.add_argument('--device-audio-output',type=int)
    parser.add_argument('--capture-devices',action='store_true')
    parser.add_argument('--smooth-device-clock',action='store_true')
    parser.add_argument('--device-buffer-frames',type=int,choices=(2,4),default=2)
    parser.add_argument('--video-delay-ms',type=float,default=0);args=parser.parse_args()
    if args.capture_devices and args.device_audio_output is None:parser.error('--capture-devices requires --device-audio-output')
    if args.device_buffer_frames != 2 and args.device_audio_output is None:
        parser.error('--device-buffer-frames requires --device-audio-output')
    root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    report={'status':'failed','phase':'preparing','checks':{},'physical_device_tested':False,'platform_tested':False,
            'device_buffer_frames':args.device_buffer_frames if args.device_audio_output is not None else None}
    tts=client=receiver=sink=session=ingress=assembler=injector=None
    completed=[];expected={};errors=[];presented=[];offsets=[];submit_costs=[];device_trace=[]
    capture=None
    first_device_frame=threading.Event()
    def save():(root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        ffmpeg=args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe'
        source=VoiceStore(args.source_voice_data);reference=source.get(source.selected());voices=VoiceStore(root)
        voice=voices.import_audio(source.audio_path(reference['id']),reference['transcript'],'连续链路验证音色',ffmpeg);voices.select(voice['id'])
        avatars=AvatarStore(root);avatar=avatars.import_prepared(args.source_avatar_directory.resolve(),'连续链路验证形象');avatars.select(avatar['id'])
        products=ProductStore(root);product=products.save(title='V05连续输出验证',content='仅本机，不开播',product_index=12);products.select(product['id'])
        tts=TTSTasks(args.runtime_root,root)
        warm_script=products.add_script(product,'这是准备阶段的语音模型预热。');products.select_script(product['id'],warm_script)
        tts.start(product['id'],warm_script,voice['id'],use_cache=False);warm=wait(tts,195)
        if warm['status']!='succeeded':raise RuntimeError('TTS preparation failed')
        ingress=LiveSpeechIngress(tts,avatars,root);speech_session=ingress.start();assembler=SpeechAssembler(root/'assembled')
        shutil.copytree(args.seed_cache,root/'engine-cache');client=LiveAvatarClient(args.runtime_root,avatars.directory(avatar['id']),root,root/'engine-cache')
        client.request('start',session_id=speech_session.id);report['avatar_prepare']=client.request('prepare');save()
        receiver=FrameReceiver(speech_session.id,avatar['width'],avatar['height']);client.request('attach_frames',channel=receiver.descriptor())
        device_sink=CounterDeviceSink if args.capture_devices else AVDeviceSink
        def record_device(row):
            device_trace.append(row)
            if row['event']=='video_sent' and not first_device_frame.is_set():
                first_device_frame.set()
        sink=(device_sink(avatar['width'],avatar['height'],args.device_audio_output,on_present=record_device,
                          video_delay_ms=args.video_delay_ms,smooth_clock=args.smooth_device_clock,
                          buffer_frames=args.device_buffer_frames)
            if args.device_audio_output is not None else ContinuousAVSink(ffmpeg,root/'live.ts',avatar['width'],avatar['height']))
        trace=(root/'presented.jsonl').open('w',encoding='utf-8')
        def on_present(row):
            trace.write(json.dumps(row)+'\n')
            if 'late_ns' in row:
                presented.append(row['late_ns']/1000000);offsets.append(row['offset_ns']/1000000)
            submit_costs.append(row['submit_ns']/1000000)
        session=ContinuousSession(speech_session.id,client,receiver,sink,root/'assembled',on_source_complete=completed.append,on_present=on_present)
        def inject():
            nonlocal capture
            try:
                if not session.started.wait(30):raise TimeoutError('Continuous output did not start')
                if args.capture_devices:
                    if not first_device_frame.wait(2):raise TimeoutError('Camera did not send its first frame')
                    if session.stop_event.is_set():return
                    capture=DeviceCapture(ffmpeg,root,max(1,args.seconds-2))
                for text in ['这是连续输出开始后新生成的第一条语音。','这是运行中新生成的第二句话，前后保持音画连续。']:
                    if session.stop_event.is_set():return
                    script=products.add_script(product,text);products.select_script(product['id'],script)
                    generation_started=time.perf_counter();tts.start(product['id'],script,voice['id'],use_cache=False)
                    audio=wait(tts,195)
                    if audio['status']!='succeeded' or audio['result']['cache_hit'] or audio['result']['model_load_count']!=1:raise RuntimeError('New resident TTS failed')
                    ingress.capture(audio['id']);utterance=None
                    while utterance is None:utterance=assembler.push(ingress.take(timeout=2))
                    expected[utterance.task_id]={'path':audio['result']['output'],'samples':utterance.samples,'pcm_sha256':utterance.pcm_sha256,'generation_started':generation_started}
                    session.submit(utterance)
            except BaseException as error:
                if not session.stop_event.is_set():errors.append(str(error))
        injector=threading.Thread(target=inject,name='new-tts-during-output');injector.start()
        report['phase']='running';save();started=time.perf_counter()
        try:session.run(frames=args.seconds*25)
        finally:trace.close()
        report['wall_seconds']=time.perf_counter()-started;injector.join(timeout=5)
        if injector.is_alive() or errors:raise RuntimeError('New speech injection failed: '+str(errors))
        done={event['source_id']:event for event in completed if not event['source_id'].startswith('idle-')}
        if len(expected)!=2 or set(done)!=set(expected):raise RuntimeError('Continuous output ended before both real utterances completed')
        for task,source_audio in expected.items():
            if done[task]['samples']!=source_audio['samples'] or done[task]['pcm_sha256']!=source_audio['pcm_sha256']:raise RuntimeError('Continuous speech truncated or changed')
        reference_path=root/'reference.wav';total=0;fingerprint=hashlib.sha256()
        with wave.open(str(reference_path),'wb') as output:
            output.setparams((1,2,24000,0,'NONE','not compressed'))
            for event in completed:
                if event['source_id'].startswith('idle-'):pcm=bytes(event['samples']*2)
                else:
                    with wave.open(expected[event['source_id']]['path'],'rb') as sound:pcm=sound.readframes(sound.getnframes())
                output.writeframesraw(pcm);fingerprint.update(pcm);total+=len(pcm)//2
            if total>sink.samples:raise RuntimeError('PCM completion accounting overflow')
            tail=bytes((sink.samples-total)*2);output.writeframesraw(tail);fingerprint.update(tail)
        if fingerprint.hexdigest()!=sink.pcm_hash.hexdigest():raise RuntimeError('Idle/speech PCM timeline differs from encoder input')
        if args.device_audio_output is not None:
            (root/'device-presented.json').write_text(json.dumps(device_trace),encoding='utf-8')
            if sink.presented!=args.seconds*25 or sink.camera.frames!=sink.presented:raise RuntimeError('Device output incomplete')
            report.update(status='passed',phase='completed',output_mode='virtual_devices',expected_sources=expected,
                completed_speech=done,frames_written=session.frames_written,device_audio_frames=sink.presented,
                device_video_frames=sink.camera.frames,device_queue_peak=sink.peak,underflows=sink.underflows,
                output_closed=sink.closed,avatar_closed=client.process.poll() is not None,video_delay_ms=args.video_delay_ms,
                timing_acceptance=False,receiver_sync_tested=False,smooth_device_clock=args.smooth_device_clock)
            report['checks'].update(two_new_utterances_during_output=True,source_pcm_exact=True,device_callbacks_complete=True)
            if capture:
                capture.wait();report['receiver']=audit_received_voice(capture.path,completed,expected)
                report['receiver_sync_tested']=True
                if not report['receiver']['voice_sync_passed']:
                    report['status']='failed';raise RuntimeError('Real voice receiver correlation or A/V timing failed')
                if not report['receiver']['speech_frame_continuity_passed']:
                    report['status']='failed';raise RuntimeError('Receiver dropped, repeated or reordered speech video frames')
            return 0
        subprocess.run([str(ffmpeg),'-nostdin','-y','-v','error','-i',str(root/'live.ts'),'-map','0:v:0','-map','0:a:0','-c','copy',str(root/'audit.mp4')],capture_output=True,check=True,timeout=60)
        media=verify_media(reference_path,root/'audit.mp4',ffmpeg)
        if media['frames']!=args.seconds*25 or sink.samples!=args.seconds*24000:raise RuntimeError('Continuous frame/sample count mismatch')
        report.update(status='passed',phase='completed',media=media,expected_sources=expected,completed_speech=done,frames_written=session.frames_written,
            encoder_pid=sink.process.pid,encoder_closed=sink.process.poll() is not None,avatar_closed=client.process.poll() is not None,
            observed_frame_queue_peak=receiver.peak,startup_preroll_frames=8,
            submission_late_p95_ms=float(np.percentile(presented,95)),submission_late_p99_ms=float(np.percentile(presented,99)),
            submission_late_max_ms=max(presented),submission_above_5ms_ratio=sum(value>5 for value in presented)/len(presented),
            submission_early_max_ms=max(0,-min(offsets)),submission_abs_offset_p95_ms=float(np.percentile(np.abs(offsets),95)),
            submit_cost_p95_ms=float(np.percentile(submit_costs,95)),
            timing_acceptance=False)
        report['checks'].update(two_new_utterances_during_output=True,idle_speech_idle_one_mux=True,source_pcm_exact=True,one_video_audio_clock=True,complete_media=True)
    except Exception as error:report.update(status='failed',error_type=type(error).__name__,error=str(error))
    finally:
        report.update(expected_sources=expected,completed_sources=completed,injection_errors=errors)
        if session:session.stop()
        elif receiver:receiver.close()
        if client:client.close()
        if tts:tts.close()
        if injector:injector.join(timeout=5)
        if capture:capture.close()
        if assembler:assembler.close()
        if ingress:ingress.stop()
        if sink and not sink.closed:sink.abort()
        if args.device_audio_output is not None:
            (root/'device-presented.json').write_text(json.dumps(device_trace),encoding='utf-8')
            report['device_error']=getattr(sink,'error',None)
        save()
        if args.device_audio_output is not None:
            print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
