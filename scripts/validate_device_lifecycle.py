"""Real virtual-device release/reopen only; does not claim model/platform cycles."""
import argparse
import json
from pathlib import Path
import time
import uuid
import numpy as np
from scripts.live_av_device_sink import AVDeviceSink


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--audio-output',type=int,required=True)
    parser.add_argument('--report-directory',type=Path,required=True);args=parser.parse_args()
    root=args.report_directory/('run-'+uuid.uuid4().hex);root.mkdir(parents=True)
    report={'status':'failed','scope':'virtual_device_release_reopen','cycles':[]};sink=None
    try:
        image=np.full((1280,720,3),96,np.uint8)
        for cycle in range(20):
            started=time.perf_counter();sink=AVDeviceSink(720,1280,args.audio_output,video_delay_ms=100)
            mode=('drain','cancel_active','cancel_before_start')[cycle%3]
            for index in range(10 if mode=='drain' else 4 if mode=='cancel_active' else 0):sink.submit(index,image,bytes(1920))
            if mode=='drain':sink.finish_input();sink.close()
            else:sink.abort()
            if not sink.closed or sink.video_thread.is_alive():raise RuntimeError('Device resources still active')
            if mode=='drain' and (sink.presented!=10 or sink.camera.frames!=10 or sink.underflows):raise RuntimeError('Normal device drain failed')
            report['cycles'].append({'cycle':cycle+1,'mode':mode,'audio_frames':sink.presented,
                'video_frames':sink.camera.frames,'underflows':sink.underflows,'error':sink.error,
                'camera_open_attempts':sink.camera.open_attempts,'camera_open_seconds':sink.camera.open_seconds,
                'closed':sink.closed,'wall_seconds':time.perf_counter()-started})
            sink=None
        report['status']='passed'
    except Exception as error:report.update(error_type=type(error).__name__,error=str(error))
    finally:
        if sink:sink.abort()
        (root/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'report':str(root/'result.json'),'status':report['status'],'cycles':len(report['cycles']),'error':report.get('error')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
