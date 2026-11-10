"""Real model cache/uncached/tempo and reference-integrity validation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid
import wave
import threading

from scripts.voice_store import VoiceStore


def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime-root',required=True,type=Path)
    p.add_argument('--source-data',required=True,type=Path);p.add_argument('--report-directory',required=True,type=Path)
    a=p.parse_args();root=(a.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    result={'task':'V03-04','status':'failed','checks':{},'outputs':[],'listening_verified':False}
    process=None;watchdog=None
    with (root/'worker.log').open('w',encoding='utf-8') as log:
        try:
            source=VoiceStore(a.source_data);voice=source.get(source.selected());store=VoiceStore(root)
            imported=store.import_audio(source.audio_path(voice['id']),voice['transcript'],'缓存验证参考',
                a.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe');store.select(imported['id'])
            command=[sys.executable,'-X','utf8','-m','scripts.tts_worker','--runtime-root',str(a.runtime_root.resolve()),'--data-directory',str(root)]
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',bufsize=1)
            watchdog=threading.Timer(180,lambda:process.kill() if process.poll() is None else None);watchdog.daemon=True;watchdog.start()
            assert json.loads(process.stdout.readline())['event']=='ready'
            def call(request):
                process.stdin.write(json.dumps(request,ensure_ascii=False)+'\n');process.stdin.flush()
                return json.loads(process.stdout.readline())
            request={'voice_id':imported['id'],'text':'现在验证语音缓存，重复请求应复用正确的音频。','speed':1.0,'language':'zh-CN','use_cache':True}
            first=call(request);assert first['ok'],first
            second=call(request);assert second['ok'] and second['result']['cache_hit']
            assert first['result']['sha256']==second['result']['sha256']
            assert first['result']['inference_calls']==second['result']['inference_calls']==1
            result['checks']['repeat_hits_without_new_inference']=True
            uncached=call({**request,'use_cache':False});assert uncached['ok'] and not uncached['result']['cache_hit']
            assert uncached['result']['inference_calls']==2;result['checks']['disabled_cache_runs_inference']=True
            fast=call({**request,'speed':1.5});assert fast['ok'] and not fast['result']['cache_hit']
            result['checks']['different_speed_misses_cache']=True
            text_path=store.audio_path(imported['id']).parent/'ref_text.txt';original=text_path.read_bytes()
            try:
                text_path.write_text('参考文字被替换',encoding='utf-8');invalid=call(request);assert invalid['ok'] is False
            finally: text_path.write_bytes(original)
            restored=call(request);assert restored['ok'] and restored['result']['cache_hit']
            result['checks']['reference_change_rejected_and_restoration_recovers']=True
            ffmpeg=a.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe'
            tempo=root/'tempo-1.5.wav'
            subprocess.run([str(ffmpeg),'-nostdin','-y','-v','error','-i',first['result']['output'],'-filter:a','atempo=1.5',str(tempo)],check=True,timeout=30)
            with wave.open(str(tempo)) as reader: duration=reader.getnframes()/reader.getframerate()
            assert abs(duration/first['result']['duration']-1/1.5)<.05
            result['checks']['tempo_duration_ratio']=True
            for event in [first,second,uncached,fast,restored]:
                subprocess.run([str(ffmpeg),'-nostdin','-v','error','-i',event['result']['output'],'-f','null','-'],check=True,capture_output=True,timeout=30)
                result['outputs'].append(event['result'])
            process.stdin.write('{"action":"close"}\n');process.stdin.flush();assert process.wait(timeout=15)==0
            process.stdin.close();process.stdout.close()
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',bufsize=1)
            assert json.loads(process.stdout.readline())['event']=='ready'
            cold=call(request)
            assert cold['ok'] and cold['result']['cache_hit'] and cold['result']['model_load_count']==0 and cold['result']['inference_calls']==0
            result['checks']['cold_worker_cache_hit_without_model_load']=True
            result['outputs'].append(cold['result'])
            subprocess.run([str(ffmpeg),'-nostdin','-v','error','-i',cold['result']['output'],'-f','null','-'],check=True,capture_output=True,timeout=30)
            process.stdin.write('{"action":"close"}\n');process.stdin.flush();assert process.wait(timeout=15)==0
            result.update(status='passed',worker_exit_code=0)
        except Exception as error: result['error']=str(error)
        finally:
            if watchdog: watchdog.cancel()
            if process and process.poll() is None: process.kill();process.wait(timeout=10)
            (root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'report':str(root/'result.json'),'error':result.get('error')},ensure_ascii=False))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
