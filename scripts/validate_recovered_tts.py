"""Real recovered-provider smoke test; not listening/identity acceptance."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from scripts.voice_store import VoiceStore


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--data-directory',required=True,type=Path)
    parser.add_argument('--report-directory',required=True,type=Path)
    args=parser.parse_args(argv)
    runtime=args.runtime_root.resolve();data=args.data_directory.resolve();report=args.report_directory.resolve()
    report.mkdir(parents=True,exist_ok=True)
    voice=VoiceStore(data).selected()
    if not voice: raise ValueError('请先选择参考音色')
    marker=str(uuid.uuid4().int)[:6]
    requests=[{'voice_id':voice,'text':text+marker+'。','speed':1.0,'language':'zh-CN','use_cache':False}
              for text in ['这是重建源码的第一段语音测试，本次编号','第二段文字与前一段不同，用于验证模型常驻，本次编号']]
    command=[sys.executable,'-X','utf8','-m','scripts.tts_worker','--runtime-root',str(runtime),'--data-directory',str(data)]
    outcome={'task':'V03-03a','provider':'recovered-voice-infer-v3','status':'failed',
             'scope':'real-synthesis-decode-and-reuse-only','listening_verified':False,'requests':requests}
    with (report/'worker.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8')
        try:
            output,_=process.communicate('\n'.join(json.dumps(r,ensure_ascii=False) for r in [*requests,{'action':'close'}])+'\n',timeout=180)
            events=[json.loads(line) for line in output.splitlines() if line.strip()]
            results=[e['result'] for e in events if e.get('ok')]
            if process.returncode!=0 or len(results)!=2 or any(e.get('ok') is False for e in events):
                raise ValueError('重建TTS未完成两次真实合成')
            if [r['model_loaded'] for r in results]!=[True,False] or any(r['model_load_count']!=1 for r in results):
                raise ValueError('模型未在两句间正确复用')
            if len({r['sha256'] for r in results})!=2: raise ValueError('两段音频相同')
            ffmpeg=runtime/'_internal/env/ffmpeg/bin/ffmpeg.exe'
            for result in results:
                decoded=subprocess.run([str(ffmpeg),'-nostdin','-v','error','-i',result['output'],'-f','null','-'],capture_output=True,timeout=30)
                if decoded.returncode!=0: raise ValueError('音频完整解码失败')
            outcome.update(status='passed',results=results,worker_exit_code=process.returncode)
        except Exception as error:
            if process.poll() is None: process.kill();process.wait(timeout=10)
            outcome['error']=str(error)
        finally:
            (report/'result.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':outcome['status'],'report':str(report/'result.json'),'error':outcome.get('error')},ensure_ascii=False))
    return 0 if outcome['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
