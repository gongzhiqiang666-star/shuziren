"""One product render; only JSON on stdout, model diagnostics in the job log."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import traceback

from scripts.avatar_render import render


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--avatar-directory',required=True,type=Path)
    parser.add_argument('--audio',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        with redirect_stdout(sys.stderr):
            result=render(args.runtime_root,args.avatar_directory,args.audio,args.output)
        response={'ok':True,'result':result}
    except Exception as error:
        traceback.print_exc(file=sys.stderr)
        response={'ok':False,'error':'视频合成失败，请检查形象、语音及任务日志','error_type':type(error).__name__}
    print(json.dumps(response,ensure_ascii=False),flush=True)
    return 0 if response['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
