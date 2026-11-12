"""Two genuinely new GPU utterances handed off while one consumer is running."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
import wave

from scripts.avatar_store import AvatarStore
from scripts.live_speech_ingress import LiveSpeechIngress
from scripts.live_speech_queue import LiveSpeechQueue,StaleSession
from scripts.product_store import ProductStore
from scripts.tts_tasks import TTSTasks
from scripts.voice_store import VoiceStore


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','source-voice-data','source-avatar-directory','report-directory']:
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    report={'status':'failed','checks':{},'device_output_tested':False,'live_avatar_tested':False};tts=ingress=consumer=None
    stop=threading.Event();first_received=threading.Event();resume_consumer=threading.Event();errors=[];received={};order=[]
    def save():
        (root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def wait_tts():
        deadline=time.monotonic()+195
        while time.monotonic()<deadline:
            state=tts.state()
            if state['status']!='running':
                tts.monitor.join(timeout=10)
                if state['status']!='succeeded':raise RuntimeError('Real TTS failed: '+str(state))
                return state
            time.sleep(.1)
        raise TimeoutError('Real TTS timed out')
    try:
        source=VoiceStore(args.source_voice_data);reference=source.get(source.selected());voices=VoiceStore(root)
        voice=voices.import_audio(source.audio_path(reference['id']),reference['transcript'],'交接实测音色',args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe');voices.select(voice['id'])
        avatars=AvatarStore(root);avatar=avatars.import_prepared(args.source_avatar_directory.resolve(),'交接实测形象');avatars.select(avatar['id'])
        products=ProductStore(root);product=products.save(title='V05真实交接验证',content='仅本机，不开播',product_index=10);products.select(product['id'])
        tts=TTSTasks(args.runtime_root,root)
        ingress=LiveSpeechIngress(tts,avatars,root,LiveSpeechQueue(max_items=1,max_seconds=1,max_utterance_seconds=1));session=ingress.start()
        def consume():
            try:
                with wave.open(str(root/'consumed.wav'),'wb') as output:
                    output.setparams((1,2,24000,0,'NONE','not compressed'))
                    while not stop.is_set():
                        try:packet=ingress.take(timeout=.2)
                        except TimeoutError:continue
                        if not ingress.queue.is_current(packet.session):raise RuntimeError('Stale packet delivered')
                        origin=packet.origin;entry=received.setdefault(origin.task_id,{'samples':0,'sha256':hashlib.sha256(),'segments':0,'first_received':time.monotonic()})
                        if origin.start_sample!=entry['samples']:raise RuntimeError('Dropped or repeated sample range')
                        if order and order[-1]!=origin.task_id and origin.task_id in order:raise RuntimeError('Interleaved utterances')
                        if not order or order[-1]!=origin.task_id:order.append(origin.task_id)
                        entry['sha256'].update(packet.pcm);entry['samples']+=packet.samples;entry['segments']+=1
                        output.writeframesraw(packet.pcm)
                        if not first_received.is_set():
                            first_received.set()
                            while not stop.is_set() and not resume_consumer.wait(.1):
                                pass
            except BaseException as error:errors.append(str(error))
        expected=[];pids=[]
        for index,text in enumerate(['这是第一条真实语音，现在开始验证逐句交接。','这是运行中新增的第二条语音，请按顺序接上。']):
            script=products.add_script(product,text);products.select_script(product['id'],script)
            started=time.monotonic();tts.start(product['id'],script,voice['id'],use_cache=False);pids.append(tts.process.pid)
            audio=wait_tts();result=audio['result']
            if result['cache_hit'] or result['model_load_count']!=1:raise RuntimeError('Expected uncached resident real TTS')
            with wave.open(result['output'],'rb') as sound:
                pcm=sound.readframes(sound.getnframes());samples=sound.getnframes()
            expected.append({'task_id':audio['id'],'samples':samples,'pcm_sha256':hashlib.sha256(pcm).hexdigest(),'generation_started':started})
            if index == 1:
                if ingress.state(validate=False)['pending_task_id'] != expected[0]['task_id']:
                    raise RuntimeError('First source did not fill the queue for the backpressure check')
                report['checks']['observed_pending_source_before_resume'] = True
                resume_consumer.set()
            capacity_deadline=time.monotonic()+30;waited=False
            while ingress.state(validate=False)['pending_task_id'] is not None:
                waited=True
                if errors or not consumer.is_alive():raise RuntimeError('Consumer stopped during backpressure: '+str(errors))
                if time.monotonic()>capacity_deadline:raise TimeoutError('Consumer made insufficient room for the next source')
                with ingress.queue.condition:ingress.queue.condition.wait(timeout=.1)
            if waited:report['checks']['producer_waited_for_backpressure']=True
            receipt=ingress.capture(audio['id']);report.setdefault('receipts',[]).append(receipt)
            if index==0:
                consumer=threading.Thread(target=consume,name='live-speech-real-consumer');consumer.start()
                if not first_received.wait(10):raise TimeoutError('No first packet received')
            save()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if errors:raise RuntimeError(errors[0])
            if all(received.get(item['task_id'],{}).get('samples')==item['samples'] for item in expected):break
            time.sleep(.05)
        stop.set();consumer.join(timeout=5)
        if consumer.is_alive() or errors:raise RuntimeError('Consumer did not stop cleanly: '+str(errors))
        for item in expected:
            actual=received[item['task_id']]
            if actual['samples']!=item['samples'] or actual['sha256'].hexdigest()!=item['pcm_sha256']:raise RuntimeError('PCM handoff incomplete')
        if order!=[item['task_id'] for item in expected] or len(set(pids))!=1:raise RuntimeError('Order/model process reuse failed')
        if expected[1]['generation_started']<=received[expected[0]['task_id']]['first_received']:raise RuntimeError('Second speech was pre-generated')
        report['checks'].update(real_uncached_tts=True,resident_worker_reused=True,dynamic_second_utterance=True,ordered_pcm_exact=True)
        try:ingress.capture(expected[-1]['task_id']);raise AssertionError('Duplicate accepted')
        except ValueError:report['checks']['duplicate_rejected']=True
        ingress.stop()
        if ingress.queue.is_current(session) or list(ingress.root.rglob('*.wav')):raise RuntimeError('Stop retained a session or snapshot')
        try:ingress.capture(expected[-1]['task_id']);raise AssertionError('Late result accepted')
        except StaleSession:report['checks']['stopped_late_result_rejected']=True
        ingress.start();ingress.capture(expected[-1]['task_id'])
        products.save(title=product['title'],content='验证改版后停止',product_index=10,product_id=product['id'],version=1)
        state=ingress.state()
        if state['status']!='stopped' or state['queued_items'] or list(ingress.root.rglob('*.wav')):raise RuntimeError('Changed product retained speech')
        report['checks']['changed_product_flushes_pending']=True
        report['expected']=expected;report['received']={key:{**value,'sha256':value['sha256'].hexdigest()} for key,value in received.items()}
        tts.close();report.update(status='passed',worker_pid=pids[0],workers_closed=tts.process is None)
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        stop.set()
        if ingress:ingress.stop()
        if consumer:consumer.join(timeout=5)
        if tts:tts.close()
        save()
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
