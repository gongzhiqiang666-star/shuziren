"""Verify a scheduling-only change against every baseline encoded frame."""
import argparse
import json
from pathlib import Path
import numpy as np

from scripts.avatar_store import AvatarStore,digest
from scripts.quality_metrics import compare_videos
from scripts.validate_quality_corpus import write


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True)
    args=parser.parse_args();old=args.baseline.resolve();new=args.candidate.resolve()
    corpus=json.loads((new/'corpus.json').read_text(encoding='utf-8'))
    original=json.loads((old/'corpus.json').read_text(encoding='utf-8'))
    if corpus!=original:raise ValueError('Corpus changed')
    config=json.loads((new/'config.json').read_text(encoding='utf-8'))
    if json.loads((new/'tensorrt/stage.json').read_text())['execution_status']!='completed':
        raise ValueError('Candidate stage incomplete')
    avatar=AvatarStore(new).directory(config['avatar_id']);rows=[];warm=[]
    for item in corpus['items']:
        case=item['id'];records=[json.loads((root/'tensorrt'/(case+'.json')).read_text(encoding='utf-8')) for root in [old,new]]
        a,b=records
        if a['audio_sha256']!=b['audio_sha256'] or not b['audio_complete']:raise ValueError('Audio mismatch')
        videos=[Path(record['output']) for record in records]
        if any(digest(path)!=record['output_sha256'] for path,record in zip(videos,records)):raise ValueError('Video changed')
        comparison=compare_videos(*videos,avatar,corpus['thresholds'])
        rows.append({'id':case,**comparison})
        if not b['cold']:warm.append(b)
        write(new/'prefetch-comparison-progress.json',{'checked':len(rows),'item':case})
    fps=sum(row['frames'] for row in warm)/sum(row['process_seconds'] for row in warm)
    p95=float(np.percentile([row['process_seconds']*1000/row['frames'] for row in warm],95))
    result={'baseline':str(old),'candidate':str(new),'cases':rows,
        'all_decoded_frames_identical':all(row['whole_frame_mae_mean']==0 for row in rows),
        'warm_frames_per_second':fps,'frame_ms_p95':p95,
        'capacity_passed':fps>=corpus['thresholds']['min_warm_render_capacity_fps'] and p95<=corpus['thresholds']['warm_frame_ms_p95_max'],
        'manual_quality_verified':False,'full_stage_acceptance':False}
    write(new/'prefetch-comparison.json',result)
    print(json.dumps({key:value for key,value in result.items() if key!='cases'}),flush=True)


if __name__=='__main__':main()
