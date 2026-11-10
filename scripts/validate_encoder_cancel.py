"""Own local API validation: cancel only after the actual FFmpeg child is live."""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import Request,urlopen
import psutil


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True)
    parser.add_argument('--data-directory',type=Path,required=True);args=parser.parse_args()
    base=args.url.rstrip('/');parsed=urlparse(base)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.path:raise ValueError('Own loopback console URL required')
    root=args.data_directory.resolve();report={'status':'failed'};task=None
    with urlopen(base+'/api/session',timeout=10) as response:token=json.load(response)['token']
    def call(path,value=None):
        request=Request(base+path,data=json.dumps(value).encode() if value is not None else None,
            headers={'Content-Type':'application/json','Origin':base,'X-Console-Token':token})
        with urlopen(request,timeout=30) as response:return json.load(response)
    try:
        state=call('/api/render/state')['task']
        if not state or state['status']!='succeeded':raise ValueError('Requires an existing successful isolated validation task')
        task=call('/api/render/start',{'tts_task_id':state['tts_task_id'],'avatar_id':state['avatar_id'],'render_profile':'trt-nvenc'})['task']
        output=(root/'render-jobs'/task['id']/'output.mp4').resolve();deadline=time.monotonic()+90;encoder=None
        while time.monotonic()<deadline and encoder is None:
            for process in psutil.process_iter(['cmdline']):
                command=process.info['cmdline'] or []
                if 'scripts.render_worker' not in command or str(output) not in command:continue
                try:
                    encoder=next((child for child in process.children(recursive=True) if child.name().lower()=='ffmpeg.exe' and child.is_running()),None)
                except psutil.NoSuchProcess:continue
                if encoder:break
            if encoder:break
            if call('/api/render/state')['task']['status']!='running':raise RuntimeError('Render ended before an encoder child was observed')
            time.sleep(.03)
        if encoder is None:raise TimeoutError('No live encoder observed; do not claim encoder cancellation')
        report['observed_encoder_pid']=encoder.pid;report['encoder_created']=encoder.create_time()
        started=time.perf_counter();cancelled=call('/api/render/cancel',{'task_id':task['id']})['task']
        report['cancel_seconds']=time.perf_counter()-started
        if cancelled['status']!='cancelled' or 'result' in cancelled or output.exists() or encoder.is_running():
            raise RuntimeError('Cancellation left a process, file or accepted result')
        report.update(status='passed',task_id=task['id'],encoder_exited=True,output_removed=True,accepted_result=False)
    except Exception as error:
        report.update(error_type=type(error).__name__,error=str(error))
        if task:
            try:call('/api/render/cancel',{'task_id':task['id']})
            except Exception:pass
    (root/'encoder-cancel-proof.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
