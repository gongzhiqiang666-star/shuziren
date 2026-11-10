"""Real new TTS -> packet assembly -> resident WeNet/UNet, per-utterance media only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import threading
import time
import uuid

from scripts.avatar_store import AvatarStore
from scripts.live_avatar_client import LiveAvatarClient
from scripts.live_speech_ingress import LiveSpeechIngress
from scripts.live_speech_queue import LiveSpeechQueue
from scripts.product_store import ProductStore
from scripts.speech_assembler import SpeechAssembler
from scripts.tts_tasks import TTSTasks
from scripts.validate_render_tasks import wait
from scripts.voice_store import VoiceStore


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','source-voice-data','source-avatar-directory','report-directory']:parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--seed-cache',type=Path)
    args=parser.parse_args();root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    report={'status':'failed','checks':{},'device_output_tested':False,'continuous_output_tested':False};tts=ingress=assembler=client=thread=None
    def save():(root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        if args.seed_cache:shutil.copytree(args.seed_cache,root/'engine-cache');report['cache_seeded_from']=str(args.seed_cache.resolve())
        source=VoiceStore(args.source_voice_data);reference=source.get(source.selected());voices=VoiceStore(root)
        voice=voices.import_audio(source.audio_path(reference['id']),reference['transcript'],'常驻驱动实测',args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe');voices.select(voice['id'])
        avatars=AvatarStore(root);avatar=avatars.import_prepared(args.source_avatar_directory.resolve(),'常驻驱动形象');avatars.select(avatar['id'])
        products=ProductStore(root);product=products.save(title='V05常驻帧驱动',content='仅本机，不开播',product_index=11);products.select(product['id'])
        tts=TTSTasks(args.runtime_root,root);ingress=LiveSpeechIngress(tts,avatars,root,LiveSpeechQueue(max_items=1,max_seconds=1,max_utterance_seconds=1))
        session=ingress.start();assembler=SpeechAssembler(root/'assembled')
        client=LiveAvatarClient(args.runtime_root,avatars.directory(avatar['id']),root,root/'engine-cache')
        client.request('start',session_id=session.id)
        texts=['这是第一条新语音，现在用常驻模型驱动形象。','这是画面生成中新增的第二句话，继续保持动作顺序。']
        results=[];audios=[];first_frame=threading.Event();failures=[];first_frame_at=[]
        def render_first(utterance):
            try:
                def progress(value):first_frame_at.append(time.monotonic());first_frame.set()
                results.append(client.request('render',session_id=session.id,task_id=utterance.task_id,audio=str(utterance.path),
                    output=str(root/'first.mp4'),pcm_sha256=utterance.pcm_sha256,progress=progress))
            except BaseException as error:failures.append(str(error));first_frame.set()
        for index,text in enumerate(texts):
            script=products.add_script(product,text);products.select_script(product['id'],script)
            started=time.monotonic();tts.start(product['id'],script,voice['id'],use_cache=False)
            audio=wait(tts,195)
            if audio['status']!='succeeded' or audio['result']['cache_hit'] or audio['result']['model_load_count']!=1:raise RuntimeError('Real resident TTS failed')
            audios.append({'task_id':audio['id'],'path':audio['result']['output'],'generation_started':started,'worker_pid':tts.process.pid})
            ingress.capture(audio['id']);utterance=None
            while utterance is None:utterance=assembler.push(ingress.take(timeout=2))
            if index==0:
                thread=threading.Thread(target=render_first,args=(utterance,),name='resident-first-render');thread.start()
                if not first_frame.wait(360) or failures:raise RuntimeError('No first frame: '+str(failures))
            else:
                thread.join(timeout=360)
                if thread.is_alive() or failures:raise RuntimeError('First render failed: '+str(failures))
                results.append(client.request('render',session_id=session.id,task_id=utterance.task_id,audio=str(utterance.path),output=str(root/'second.mp4'),pcm_sha256=utterance.pcm_sha256))
            save()
        if audios[1]['generation_started']<=first_frame_at[0]:raise RuntimeError('Second speech was pre-generated')
        if results[0]['wenet_identity']!=results[1]['wenet_identity'] or results[0]['unet_session_identity']!=results[1]['unet_session_identity']:
            raise RuntimeError('Models were recreated')
        if any(result['wenet_load_count']!=1 or result['peak_returned_batch']>4 or result['frames']!=result['synthesized_frames'] for result in results):raise RuntimeError('Resident/batch invariant failed')
        frame_offset=0
        for result,audio in zip(results,audios):
            sequence=[]
            for index in range(frame_offset,frame_offset+result['frames']):
                period=max(1,2*avatar['frames']-2);position=index%period
                sequence.append(position if position<avatar['frames'] else period-position)
            expected=hashlib.sha256(struct.pack('<'+'I'*len(sequence),*sequence)).hexdigest()
            if result['frame_offset']!=frame_offset or result['source_sequence_sha256']!=expected:raise RuntimeError('Avatar sequence reset or reordered')
            original=client.request('inspect',audio=audio['path'])
            if original['features_sha256']!=result['features_sha256']:raise RuntimeError('Segmentation changed whole-utterance features')
            frame_offset+=result['frames']
        report['results']=results;report['audios']=audios
        report['checks'].update(dynamic_new_tts_after_first_frame=True,tts_worker_reused=len({x['worker_pid'] for x in audios})==1,
            wenet_loaded_once=True,unet_session_reused=True,bounded_batch_four=True,continuous_avatar_sequence=True,
            assembled_features_match_original=True,complete_media=True)
        client.close();tts.close();ingress.stop();assembler.close()
        for path in (root/'assembled').glob('*.wav'):path.unlink()
        if client.process.poll() is None or tts.process is not None:raise RuntimeError('Worker not reaped')
        report.update(status='passed',workers_closed=True,worker_pid=client.process.pid)
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        if client:client.close()
        if thread:thread.join(timeout=5)
        if assembler:assembler.close()
        if ingress:ingress.stop()
        if tts:tts.close()
        save()
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
