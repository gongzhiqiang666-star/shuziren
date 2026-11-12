"""Isolate real 720p portrait mux costs; synthetic frames are not avatar evidence."""
import argparse
from collections import deque
import json
from pathlib import Path
import statistics
import time
import uuid
import numpy as np
from scripts.continuous_av_sink import ContinuousAVSink
from scripts.sample_timeline import FramePacer
from scripts.v122_acceleration import windows_timer_precision


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ffmpeg',required=True,type=Path)
    parser.add_argument('--report-directory',required=True,type=Path);args=parser.parse_args()
    root=args.report_directory/('run-'+uuid.uuid4().hex);root.mkdir(parents=True)
    sink=ContinuousAVSink(args.ffmpeg,root/'sink.ts',720,1280)
    image=np.zeros((1280,720,3),np.uint8);rows=[]
    submit_costs = deque(maxlen=64)
    try:
        for index in range(8):
            started = time.perf_counter_ns()
            sink.submit(index, image, bytes(1920))
            if index >= 2:
                submit_costs.append(time.perf_counter_ns() - started)
        with windows_timer_precision():
            pacer=FramePacer('probe',time.perf_counter_ns()-8*40000000,start_frame=8)
            for index in range(8,108):
                lead = min(20_000_000, int(statistics.median(submit_costs))) if submit_costs else 0
                deadline=pacer.wait_for('probe',index,submit_lead_ns=lead);started=time.perf_counter_ns()
                timing=sink.submit(index,image,bytes(1920));stamp=pacer.presented(deadline)
                submit_ns = stamp['presented_ns'] - started
                submit_costs.append(submit_ns)
                rows.append({**stamp,**timing,'submit_ns':submit_ns,'submit_lead_ns':lead})
        sink.close()
    finally:
        if not sink.closed:sink.abort()
    report={key:{'p50_ms':float(np.percentile([r[key] for r in rows],50))/1e6,
        'p95_ms':float(np.percentile([r[key] for r in rows],95))/1e6} for key in
        ['prepare_ns','video_mux_ns','audio_mux_ns','submit_ns','submit_lead_ns','late_ns','early_ns']}
    report['late_over_5ms_ratio'] = sum(row['late_ns'] > 5_000_000 for row in rows) / len(rows)
    (root/'trace.json').write_text(json.dumps(rows),encoding='utf-8')
    (root/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(root);print(json.dumps(report))


if __name__=='__main__':main()
