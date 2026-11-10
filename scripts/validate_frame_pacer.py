"""Windows host-deadline diagnostic, deliberately no model/device/live claim."""
import argparse
import json
from pathlib import Path
import time
import uuid
import zlib
import numpy as np
from scripts.sample_timeline import FramePacer
from scripts.v122_acceleration import windows_timer_precision


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-directory',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=100);args=parser.parse_args()
    if args.frames<2:raise ValueError('At least two frames required')
    root=(args.report_directory/('pacer-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    fixture=bytes(720*1280*3);rows=[]
    with windows_timer_precision():
        pacer=FramePacer(str(uuid.uuid4()),time.perf_counter_ns())
        for index in range(args.frames):
            deadline=pacer.wait_for(pacer.session_id,index)
            checksum=zlib.crc32(fixture)
            rows.append({**pacer.presented(deadline),'fixture_crc32':checksum})
        pacer.stop()
    late=[row['late_ns']/1000000 for row in rows];p95=float(np.percentile(late,95));p99=float(np.percentile(late,99))
    above=sum(value>5 for value in late)/len(late)
    result={'scope':'host-counter checksum sink only','device_output_tested':False,'model_synthesis_tested':False,
        'repeated_frame_fixture':True,'frames':len(rows),'p95_ms':p95,'p99_ms':p99,'max_ms':max(late),
        'above_5ms_ratio':above,'observed_host_budget_met':p95<=5 and p99<=20 and max(late)<=40 and above<=.01,
        'full_v05_acceptance':False,'rows':rows}
    (root/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({**{key:value for key,value in result.items() if key!='rows'},'report':str(root/'result.json')}),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
