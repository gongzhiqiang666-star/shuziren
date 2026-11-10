"""Real restored offline avatar generation through the shared product renderer."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import uuid
from scripts.avatar_render import render


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--avatar-directory',required=True,type=Path)
    parser.add_argument('--audio',required=True,type=Path)
    parser.add_argument('--report-directory',required=True,type=Path)
    parser.add_argument('--backend',choices=['cuda','tensorrt'],default='cuda')
    parser.add_argument('--engine-cache',type=Path)
    parser.add_argument('--profile',action='store_true')
    args=parser.parse_args()
    root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    result={'status':'failed','live_tested':False,'visual_quality_verified':False}
    with (root/'generation.log').open('w',encoding='utf-8') as log,redirect_stdout(log),redirect_stderr(log):
        try:
            result.update(render(args.runtime_root,args.avatar_directory,args.audio,root/'output.mp4',
                                 args.backend,args.engine_cache,args.profile),status='passed')
        except Exception as error:result.update(error_type=type(error).__name__,error=str(error))
        (root/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'report':str(root/'result.json'),'error':result.get('error')},ensure_ascii=False))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
