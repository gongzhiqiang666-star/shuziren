"""Summarize recorded live-soak resource trends without touching the running scene."""
import argparse
import json
from pathlib import Path
from statistics import median


METRICS = ('pending', 'process_tree_rss_bytes', 'process_tree_cpu_percent',
           'tts_wav_count', 'tts_wav_bytes')


def metric(values):
    known = [value for value in values if value is not None]
    if not known:
        return {'count': 0, 'median': None, 'max': None}
    return {'count': len(known), 'median': median(known), 'max': max(known)}


def summarize(rows, window_seconds=60):
    if not rows:
        raise ValueError('No complete live-soak samples')
    if window_seconds<=0:
        raise ValueError('Window duration must be positive')
    windows={}
    last_elapsed=-1
    for row in rows:
        elapsed=row['elapsed_seconds']
        if elapsed<0 or elapsed<=last_elapsed:
            raise ValueError('Live-soak sample time is not increasing')
        windows.setdefault(int(elapsed//window_seconds),[]).append(row)
        last_elapsed=elapsed
    gpu_indices=sorted({gpu['index'] for row in rows for gpu in row.get('gpu') or []})
    summaries=[]
    for index,samples in windows.items():
        first,last=samples[0],samples[-1]
        span=last['elapsed_seconds']-first['elapsed_seconds']
        values={key:metric([row.get(key) for row in samples]) for key in METRICS}
        values.update({f'gpu_{gpu_index}_used_mib':metric([
            next((gpu['used_mib'] for gpu in row.get('gpu') or [] if gpu['index']==gpu_index),None)
            for row in samples]) for gpu_index in gpu_indices})
        summaries.append({'window':index,'count':len(samples),'first_seconds':first['elapsed_seconds'],
            'last_seconds':last['elapsed_seconds'],'submitted_fps':(last['frames']-first['frames'])/span if span else None,
            'completed_delta':last['completed']-first['completed'] if last.get('completed') is not None and first.get('completed') is not None else None,
            'metrics':values})
    trends={}
    for key in summaries[0]['metrics']:
        medians=[window['metrics'][key]['median'] for window in summaries[:-1]
                 if window['metrics'][key]['median'] is not None]
        trends[key]={'windows_with_data':len(medians),'median_change':medians[-1]-medians[0] if len(medians)>1 else None,
            'all_medians_increasing':all(right>left for left,right in zip(medians,medians[1:])) if len(medians)>1 else None}
    return {'samples':len(rows),'elapsed_seconds':last_elapsed,'window_seconds':window_seconds,
            'latest_window_excluded_from_trends':True,'trends':trends,'windows':summaries}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples',type=Path)
    parser.add_argument('--window-seconds',type=int,default=60)
    args=parser.parse_args()
    with args.samples.open(encoding='utf-8') as stream:
        rows=[json.loads(line) for line in stream if line.endswith('\n')]
    print(json.dumps(summarize(rows,args.window_seconds),indent=2))


if __name__=='__main__':
    main()
