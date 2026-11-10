"""One product render; only JSON on stdout, model diagnostics in the job log."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import traceback

from scripts.avatar_render import render
from scripts.render_profiles import PROFILES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--avatar-directory',required=True,type=Path)
    parser.add_argument('--audio',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--render-profile',choices=PROFILES,default='standard')
    parser.add_argument('--engine-cache',type=Path)
    args=parser.parse_args()
    try:
        with redirect_stdout(sys.stderr):
            settings=PROFILES[args.render_profile]
            result=render(args.runtime_root,args.avatar_directory,args.audio,args.output,
                cache=args.engine_cache,backend=settings['backend'],encoder=settings['encoder'],strict_precision=settings['strict_precision'])
            result['render_profile']=args.render_profile
        response={'ok':True,'result':result}
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        response={'ok':False,'error':'视频合成失败，请检查形象、语音及任务日志','error_type':type(error).__name__}
    print(json.dumps(response,ensure_ascii=False),flush=True)
    return 0 if response['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
