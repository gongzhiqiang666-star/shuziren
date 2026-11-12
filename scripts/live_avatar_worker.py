"""JSON-lines resident worker; image batches stay inside this process."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import traceback
from scripts.resident_avatar import ResidentAvatar


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-root','avatar-directory','engine-cache']:parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();engine=None;sender=None
    def emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)
    try:
        with redirect_stdout(sys.stderr):engine=ResidentAvatar(args.runtime_root,args.avatar_directory,args.engine_cache)
        for line in sys.stdin:
            request=json.loads(line)
            try:
                if request['operation']=='start':
                    engine.start(request['session_id']);result={'session_id':engine.session,'model_ready':engine.prepared}
                elif request['operation']=='prepare':
                    with redirect_stdout(sys.stderr):result=engine.prepare()
                elif request['operation']=='attach_rtmp':
                    with redirect_stdout(sys.stderr):
                        engine.attach_rtmp(request['url'], request['width'], request['height'])
                    result={'attached':True}
                elif request['operation']=='attach_frames':
                    from scripts.live_frame_channel import FrameSender
                    if sender:sender.close()
                    sender=FrameSender(request['channel']);result={'attached':True}
                elif request['operation']=='idle':
                    if sender is None:raise ValueError('Attach frame receiver before idle output')
                    stdout=sys.stdout
                    def idle_progress(value):stdout.write(json.dumps(value)+'\n');stdout.flush()
                    with redirect_stdout(sys.stderr):result=engine.idle(request['session_id'],request['task_id'],request['timing'],sender,idle_progress)
                elif request['operation']=='inspect':
                    with redirect_stdout(sys.stderr):features,fingerprint=engine.features(request['audio'])
                    result={'frames':len(features),'features_sha256':fingerprint}
                elif request['operation'] in {'render','stream'}:
                    streaming=request['operation']=='stream'
                    if streaming and sender is None:raise ValueError('Attach frame receiver before streaming')
                    # Preserve structured progress on stdout while model prints go to stderr.
                    stdout=sys.stdout
                    def progress(value):stdout.write(json.dumps(value)+'\n');stdout.flush()
                    with redirect_stdout(sys.stderr):result=engine.render(request['session_id'],request['task_id'],request['audio'],request.get('output'),request['pcm_sha256'],progress,timing=request.get('timing'),frame_channel=sender if streaming else None)
                else:raise ValueError('Unknown worker operation')
                emit({'ok':True,'result':result})
            except Exception as error:
                traceback.print_exc(file=sys.stderr);emit({'ok':False,'error_type':type(error).__name__,'error':str(error)})
                # A failed rendering sequence cannot resume without an explicit new worker.
                return 1
    finally:
        if sender:sender.close()
        if engine:
            with redirect_stdout(sys.stderr):engine.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
