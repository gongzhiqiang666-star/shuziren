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
import psutil
from scripts.avatar_render import verify_media
from scripts.avatar_store import AvatarStore
from scripts.continuous_av_sink import ContinuousAVSink
from scripts.live_av_device_sink import AVDeviceSink
from scripts.received_voice_audit import CounterDeviceSink,DeviceCapture,audit_device_deadlines,audit_received_voice
from scripts.continuous_session import ContinuousSession
from scripts.live_avatar_client import LiveAvatarClient
from scripts.live_frame_channel import FrameReceiver
from scripts.live_speech_ingress import LiveSpeechIngress
from scripts.validate_live_soak import gpu_resources
from scripts.product_store import ProductStore
from scripts.speech_assembler import SpeechAssembler
from scripts.tts_tasks import TTSTasks
from scripts.validate_render_tasks import wait
from scripts.voice_store import VoiceStore


def load_first_output_corpus(path):
    raw=path.read_bytes()
    corpus=json.loads(raw)
    items=corpus['items']
    texts=[item['text'] for item in items]
    ids=[item['id'] for item in items]
    if (corpus['version']!='V05-T1-first-output-v1' or len(items)!=50
            or len(set(ids))!=50 or len(set(texts))!=50
            or any(not isinstance(text,str) or not text.strip() or len(text)>60 for text in texts)):
        raise ValueError('Expected 50 unique short V05-T1 utterances')
    return items,hashlib.sha256(raw).hexdigest()


def main():
    launched_ns=time.perf_counter_ns()
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','source-voice-data','source-avatar-directory','report-directory']:parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--seed-cache',type=Path,help='Copy an existing engine cache before startup')
    parser.add_argument('--seconds',type=int,default=20)
    parser.add_argument('--device-audio-output',type=int)
    parser.add_argument('--capture-devices',action='store_true')
    parser.add_argument('--dshow-video-clock',action='store_true')
    parser.add_argument('--smooth-device-clock',action='store_true')
    parser.add_argument('--device-buffer-frames',type=int,choices=(2,4,8),default=2)
    parser.add_argument('--camera-i420',action='store_true')
    parser.add_argument('--idle-frames',type=int,choices=(4,8),default=8)
    parser.add_argument('--speech-interval-seconds',type=int,
                        help='Add a distinct uncached utterance at each interval, reserving the last 20 seconds for completion')
    parser.add_argument('--first-output-corpus',type=Path,help='Run the 50-utterance receiver latency cohort')
    parser.add_argument('--video-delay-ms',type=float,default=0);args=parser.parse_args()
    if args.capture_devices and args.device_audio_output is None:parser.error('--capture-devices requires --device-audio-output')
    if args.dshow_video_clock and not args.capture_devices:parser.error('--dshow-video-clock requires --capture-devices')
    if args.dshow_video_clock and args.first_output_corpus:parser.error('DirectShow clock has no calibrated absolute capture origin')
    if args.device_buffer_frames != 2 and args.device_audio_output is None:
        parser.error('--device-buffer-frames requires --device-audio-output')
    if args.camera_i420 and args.device_audio_output is None:
        parser.error('--camera-i420 requires --device-audio-output')
    if args.capture_devices and args.seconds * 25 > 65536:
        parser.error('--capture-devices supports at most 2621 seconds at 25 fps (16-bit frame counter)')
    if args.speech_interval_seconds is not None and not 0<args.speech_interval_seconds<args.seconds-20:
        parser.error('--speech-interval-seconds requires room for an additional utterance before the final 20 seconds')
    schedule=[(0,None,'这是连续输出开始后新生成的第一条语音。'),
              (0,None,'这是运行中新生成的第二句话，前后保持音画连续。')]
    corpus_hash=None
    if args.first_output_corpus is not None:
        if not args.capture_devices or args.seconds<1840 or args.speech_interval_seconds is not None:
            parser.error('--first-output-corpus requires device capture, at least 1840 seconds and the fixed cohort cadence')
        items,corpus_hash=load_first_output_corpus(args.first_output_corpus)
        schedule=[(37*index,item['id'],item['text']) for index,item in enumerate(items)]
    elif args.speech_interval_seconds:
        interval=args.speech_interval_seconds
        schedule.extend((offset,None,f'持续输出第{offset}秒，验证这一条新语音和对应画面。')
                        for offset in range(interval,args.seconds-20,interval))
    root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    report={'status':'preparing','phase':'preparing','checks':{},'physical_device_tested':False,'platform_tested':False,
            'device_buffer_frames':args.device_buffer_frames if args.device_audio_output is not None else None,
            'scheduled_speech_count':len(schedule),'speech_interval_seconds':args.speech_interval_seconds,
            'first_output_corpus_sha256':corpus_hash,'camera_pixel_format':'I420' if args.camera_i420 else 'BGR'}
    report['startup']={'engine_cache_seeded':args.seed_cache is not None}
    report['idle_frames']=args.idle_frames
    report['dshow_video_clock']=args.dshow_video_clock
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
        if args.device_audio_output is not None:
            def record_device(row):
                device_trace.append(row)
                if row['event']=='audio_callback':
                    report['startup'].setdefault('first_audio_callback_seconds',(row['callback_ns']-launched_ns)/1e9)
                if row['event']=='video_sent' and not first_device_frame.is_set():
                    report['startup']['first_camera_send_seconds']=(row['camera_sent_ns']-launched_ns)/1e9
                    first_device_frame.set()
            device_sink=CounterDeviceSink if args.capture_devices else AVDeviceSink
            sink=device_sink(avatar['width'],avatar['height'],args.device_audio_output,on_present=record_device,
                             video_delay_ms=args.video_delay_ms,smooth_clock=args.smooth_device_clock,
                             buffer_frames=args.device_buffer_frames,camera_i420=args.camera_i420)
        products=ProductStore(root);product=products.save(title='V05连续输出验证',content='仅本机，不开播',product_index=12);products.select(product['id'])
        tts=TTSTasks(args.runtime_root,root)
        warm_script=products.add_script(product,'这是准备阶段的语音模型预热。');products.select_script(product['id'],warm_script)
        tts.start(product['id'],warm_script,voice['id'],use_cache=False);warm=wait(tts,195)
        if warm['status']!='succeeded':raise RuntimeError('TTS preparation failed')
        ingress=LiveSpeechIngress(tts,avatars,root);speech_session=ingress.start();assembler=SpeechAssembler(root/'assembled')
        if args.seed_cache is not None:
            shutil.copytree(args.seed_cache,root/'engine-cache')
        client=LiveAvatarClient(args.runtime_root,avatars.directory(avatar['id']),root,root/'engine-cache')
        client.request('start',session_id=speech_session.id);report['avatar_prepare']=client.request('prepare');save()
        receiver=FrameReceiver(speech_session.id,avatar['width'],avatar['height']);client.request('attach_frames',channel=receiver.descriptor())
        if sink is None:
            sink=ContinuousAVSink(ffmpeg,root/'live.ts',avatar['width'],avatar['height'])
        trace=(root/'presented.jsonl').open('w',encoding='utf-8')
        first_queued_ns={}
        def on_present(row):
            report['startup'].setdefault('first_submission_seconds',(row['presented_ns']-launched_ns)/1e9)
            trace.write(json.dumps(row)+'\n')
            task_id=row.get('task_id')
            if task_id in expected:
                first_queued_ns.setdefault(task_id,row['presented_ns'])
            if 'late_ns' in row:
                presented.append(row['late_ns']/1000000);offsets.append(row['offset_ns']/1000000)
            submit_costs.append(row['submit_ns']/1000000)
        speech_end_samples={}
        def source_complete(event):
            completed.append(event)
            if not event['source_id'].startswith('idle-'):
                speech_end_samples[event['source_id']]=session.pcm.read_samples
        session=ContinuousSession(speech_session.id,client,receiver,sink,root/'assembled',on_source_complete=source_complete,on_present=on_present,idle_frames=args.idle_frames)
        if isinstance(sink, AVDeviceSink):
            sink.underrun_context = session.stall_context
        def inject():
            nonlocal capture
            try:
                if not session.started.wait(30):raise TimeoutError('Continuous output did not start')
                schedule_start=time.monotonic()
                if args.capture_devices:
                    if not first_device_frame.wait(2):raise TimeoutError('Camera did not send its first frame')
                    if session.stop_event.is_set():return
                    capture=DeviceCapture(ffmpeg,root,max(1,args.seconds-2),dshow_video_clock=args.dshow_video_clock)
                previous=None
                for offset,case_id,text in schedule:
                    if session.stop_event.wait(max(0,schedule_start+offset-time.monotonic())):return
                    if corpus_hash and previous is not None:
                        while previous not in speech_end_samples or sink.presented*960<speech_end_samples[previous]:
                            if session.stop_event.wait(.01):return
                    script=products.add_script(product,text);products.select_script(product['id'],script)
                    generation_started=time.perf_counter();tts.start(product['id'],script,voice['id'],use_cache=False)
                    audio=wait(tts,195)
                    if audio['status']!='succeeded' or audio['result']['cache_hit'] or audio['result']['model_load_count']!=1:raise RuntimeError('New resident TTS failed')
                    ingress_started_ns=time.time_ns()
                    ingress.capture(audio['id']);utterance=None
                    while utterance is None:utterance=assembler.push(ingress.take(timeout=2))
                    expected[utterance.task_id]={'path':audio['result']['output'],'samples':utterance.samples,
                        'pcm_sha256':utterance.pcm_sha256,'generation_started':generation_started,
                        'wav_ready_unix_ns':audio['result']['wav_ready_unix_ns'],'case_id':case_id,
                        'ingress_started_unix_ns':ingress_started_ns,
                        'queue_requested_ns':time.perf_counter_ns()}
                    session.submit(utterance)
                    previous=utterance.task_id
            except BaseException as error:
                if not session.stop_event.is_set():errors.append(str(error))
        injector=threading.Thread(target=inject,name='new-tts-during-output');injector.start()
        report.update(status='running',phase='running')
        save()
        started=time.perf_counter()
        sampling_stop=threading.Event()
        resource_report={'samples':0,'error':None,'queue_peaks':{}}
        report['resource_sampling']=resource_report
        def sample_resources():
            process=psutil.Process()
            previous_cpu={}
            with (root/'resources.jsonl').open('w',encoding='utf-8',buffering=1) as samples:
                while not sampling_stop.is_set():
                    now=time.perf_counter()
                    rss=0
                    current_cpu={}
                    cpu_percent=0.0
                    for child in [process,*process.children(recursive=True)]:
                        try:
                            times=child.cpu_times()
                            rss+=child.memory_info().rss
                            current_cpu[child.pid]=(now,times.user+times.system)
                            if child.pid in previous_cpu:
                                last_time,last_cpu=previous_cpu[child.pid]
                                cpu_percent+=max(0,times.user+times.system-last_cpu)/(now-last_time)*100
                        except (psutil.NoSuchProcess,psutil.AccessDenied):
                            continue
                    row={'elapsed_seconds':now-started,'frames':session.frames_written,
                         'pending':session.ready.qsize(),'process_tree_rss_bytes':rss,
                         'process_tree_cpu_percent':cpu_percent if previous_cpu else None,
                         'device_queue_frames':sink.queue.qsize() if isinstance(sink,AVDeviceSink) else None,
                         'video_queue_frames':sink.video_queue.qsize() if isinstance(sink,AVDeviceSink) else None,
                         'gpu':gpu_resources()}
                    samples.write(json.dumps(row)+'\n')
                    resource_report.setdefault('first_sample_seconds',row['elapsed_seconds'])
                    resource_report['last_sample']=row
                    resource_report['samples']+=1
                    for name in ('pending','device_queue_frames','video_queue_frames'):
                        if row[name] is not None:
                            peaks=resource_report['queue_peaks']
                            peaks[name]=max(peaks.get(name,0),row[name])
                    previous_cpu=current_cpu
                    sampling_stop.wait(max(0,now+1-time.perf_counter()))

        def collect_resources():
            try:
                sample_resources()
            except (OSError, psutil.Error) as error:
                resource_report['error']=str(error)

        sampler=threading.Thread(target=collect_resources,name='receiver-resource-samples')
        sampler.start()
        try:session.run(frames=args.seconds*25)
        finally:
            sampling_stop.set()
            sampler.join()
            trace.close()
        if args.first_output_corpus is not None and (resource_report['error'] is not None or not resource_report['samples']):
            raise RuntimeError('Formal receiver validation requires resource samples')
        report['wall_seconds']=time.perf_counter()-started;injector.join(timeout=5)
        if injector.is_alive() or errors:raise RuntimeError('New speech injection failed: '+str(errors))
        done={event['source_id']:event for event in completed if not event['source_id'].startswith('idle-')}
        report['speech_handoff_timings']={
            task_id:{
                'wav_ready_to_ingress_ms':(source['ingress_started_unix_ns']-source['wav_ready_unix_ns'])/1e6,
                'queue_request_to_first_frame_ms':(first_queued_ns[task_id]-source['queue_requested_ns'])/1e6
                if task_id in first_queued_ns else None,
            }
            for task_id,source in expected.items()
        }
        if len(expected)!=len(schedule) or set(done)!=set(expected):
            raise RuntimeError('Continuous output ended before all scheduled real utterances completed')
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
            report['checks'].update(all_scheduled_utterances_completed=True,source_pcm_exact=True,device_callbacks_complete=True)
            report['device_submission_deadlines']=audit_device_deadlines(device_trace)
            if capture:
                capture.wait()
                report['receiver']=audit_received_voice(capture.path,completed,expected,capture.timestamp_origin())
                report['receiver']['submitted_frame_range'] = [0, session.frames_written - 1]
                report['receiver_sync_tested']=True
                report['checks'].update(receiver_voice_sync=report['receiver']['voice_sync_passed'],
                    receiver_speech_continuity=report['receiver']['speech_frame_continuity_passed'])
                if corpus_hash:
                    latency=report['receiver']['receiver_latency_calibration']
                    report['checks']['first_output_cohort_within_budget']=all(
                        metric['count']==50 and metric['p95_ms']<=1000 for metric in latency.values())
                if args.seconds>=1840:
                    report['checks']['receiver_full_capture_continuity'] = report['receiver']['frame_continuity_passed']
                    span=report['receiver']['speech_measurement_span_seconds']
                    drift=report['receiver']['speech_av_drift_ms']
                    report['checks']['receiver_drift_within_budget']=(
                        span is not None and span>=1800 and drift is not None and drift<=40
                        and report['receiver']['received_video_span_seconds']>=1800)
                    report['checks']['device_submission_within_budget']=report['device_submission_deadlines']['passed']
                    peaks=resource_report['queue_peaks']
                    report['checks']['sampled_queues_within_budget']=(
                        peaks.get('pending',5)<=4
                        and peaks.get('device_queue_frames',args.device_buffer_frames+1)<=args.device_buffer_frames
                        and peaks.get('video_queue_frames',sink.video_queue.maxsize+1)<=sink.video_queue.maxsize
                    )
                    failed=[check for check,value in report['checks'].items() if not value]
                    if failed:
                        report['status']='failed';raise RuntimeError('V05-T1 measurement failed: '+', '.join(failed))
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
        report['checks'].update(all_scheduled_utterances_completed=True,idle_speech_idle_one_mux=True,source_pcm_exact=True,one_video_audio_clock=True,complete_media=True)
    except Exception as error:report.update(status='failed',error_type=type(error).__name__,error=str(error))
    finally:
        report.update(expected_sources=expected,completed_sources=completed,injection_errors=errors)
        if session:session.stop()
        elif receiver:receiver.close()
        if client:client.close()
        if tts:tts.close()
        if injector:injector.join(timeout=5)
        if capture:
            capture.close()
            report['receiver_buffer_drop_reported'] = capture.reported_buffer_drop()
        if assembler:assembler.close()
        if ingress:ingress.stop()
        if sink and not sink.closed:sink.abort()
        if args.device_audio_output is not None:
            (root/'device-presented.json').write_text(json.dumps(device_trace),encoding='utf-8')
            report['device_error']=getattr(sink,'error',None)
            if getattr(sink,'underrun',None) is not None:
                report['device_underrun'] = sink.underrun
        save()
        if args.device_audio_output is not None:
            print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
