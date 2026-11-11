"""Actual GPU task-binding/cancel/restart check; no listening claim."""
import argparse
import json
import subprocess
from pathlib import Path
import time
import uuid

from scripts.product_store import ProductStore,Conflict
from scripts.tts_tasks import TTSTasks
from scripts.voice_store import VoiceStore


def wait(tasks):
    deadline=time.monotonic()+195
    while time.monotonic()<deadline:
        state=tasks.state()
        if state['status']!='running': return state
        time.sleep(.1)
    raise RuntimeError('Task manager failed to reach terminal state')


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--source-data',required=True,type=Path)
    parser.add_argument('--report-directory',required=True,type=Path)
    parser.add_argument('--engine',choices=('indextts','zipvoice','omnivoice'),default='indextts')
    parser.add_argument('--model-root',type=Path)
    args=parser.parse_args(argv)
    root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    report={'task':'V03-03b' if args.engine=='indextts' else 'A01-02',
            'engine':args.engine,'status':'failed','checks':{},'listening_verified':False}
    tasks=None
    try:
        source=VoiceStore(args.source_data);selected=source.selected()
        if not selected: raise ValueError('No selected reference voice')
        reference=source.get(selected);voices=VoiceStore(root)
        voice=voices.import_audio(source.audio_path(selected),reference['transcript'],'任务验证参考',
            args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe')
        voices.select(voice['id']);products=ProductStore(root)
        p=products.save(title='任务验证商品',content='合成验证用商品，不直播',product_index=8)
        script=products.add_script(p,'这是第一段绑定商品和音色的语音验证。');products.select_script(p['id'],script)
        tasks=TTSTasks(args.runtime_root,root,engine=args.engine,model_root=args.model_root)
        tasks.start(p['id'],script,voice['id']);first=wait(tasks)
        assert first['status']=='succeeded',first
        assert first['result']['provider']=={
            'indextts':'recovered-voice-infer-v3','zipvoice':'recovered-zipvoice',
            'omnivoice':'recovered-omnivoice'}[args.engine]
        pid=tasks.process.pid
        second_script=products.add_script(p,'这是第二段全新的文本，请确认常驻工作进程继续生成。');products.select_script(p['id'],second_script)
        tasks.start(p['id'],second_script,voice['id']);second=wait(tasks)
        assert second['status']=='succeeded',second
        assert tasks.process.pid==pid and second['result']['model_loaded'] is False
        assert second['result']['model_load_count']==1
        report['checks']['persistent_pid_and_model']=True
        report['successes']=[first,second]
        task=tasks.start(p['id'],second_script,voice['id']);old_process=tasks.process
        try: tasks.start(p['id'],second_script,voice['id']);raise AssertionError('duplicate accepted')
        except Conflict: pass
        time.sleep(.1)
        cancelled=tasks.cancel(task['id']);assert cancelled['status']=='cancelled' and 'result' not in cancelled
        assert old_process.poll() is not None
        report['checks']['cancel_terminates_and_no_accepted_audio']=True
        tasks.start(p['id'],second_script,voice['id']);recovered=wait(tasks)
        assert recovered['status']=='succeeded',recovered
        assert tasks.process.pid!=pid
        report['checks']['restart_after_cancel']=True
        tasks.start(p['id'],second_script,voice['id'])
        products.save(title=p['title'],content='商品已在合成中修改',product_index=p['product_index'],product_id=p['id'],version=p['version'])
        stale=wait(tasks);assert stale['status']=='failed' and 'result' not in stale
        report['checks']['product_edit_rejects_late_audio']=True
        process=tasks.process;tasks.close();assert process.poll() is not None
        report['checks']['close_reclaims_worker']=True
        for success in report['successes']:
            decoded=subprocess.run([str(args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe'),'-nostdin',
                '-v','error','-i',success['result']['output'],'-f','null','-'],capture_output=True,timeout=30)
            if decoded.returncode!=0: raise ValueError('成功结果的音频完整解码失败')
        report['checks']['successful_outputs_full_decode']=True
        report['status']='passed'
    except Exception as error:
        report['error']=str(error)
    finally:
        if tasks: tasks.close()
        (root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(root/'result.json'),'error':report.get('error')},ensure_ascii=False))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__': raise SystemExit(main())
