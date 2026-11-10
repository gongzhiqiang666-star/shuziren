"""Encoded-picture compatibility screen, separate from FP16 model precision."""
import argparse
import json
from pathlib import Path
from scripts.avatar_store import AvatarStore,digest
from scripts.quality_metrics import compare_videos
from scripts.validate_quality_corpus import write


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--candidate',required=True,type=Path)
    args=parser.parse_args();old=args.baseline.resolve();new=args.candidate.resolve()
    corpus=json.loads((new/'corpus.json').read_text(encoding='utf-8'))
    if corpus!=json.loads((old/'corpus.json').read_text(encoding='utf-8')):raise ValueError('Corpus changed')
    config=json.loads((new/'config.json').read_text(encoding='utf-8'))
    avatar=AvatarStore(new).directory(config['avatar_id']);rows=[]
    for item in corpus['items']:
        case=item['id'];records=[json.loads((root/'cuda'/(case+'.json')).read_text(encoding='utf-8')) for root in [old,new]]
        if records[0]['audio_sha256']!=records[1]['audio_sha256']:raise ValueError('Audio changed')
        for record in records:
            if not record['audio_complete'] or digest(record['output'])!=record['output_sha256']:raise ValueError('Media changed')
        comparison=compare_videos(records[0]['output'],records[1]['output'],avatar,corpus['thresholds'])
        rows.append({'id':case,**comparison})
        write(new/'encoder-comparison-progress.json',{'checked':len(rows),'item':case})
    result={'comparison':'legacy CUDA FP32 vs direct-encoded CUDA FP32','cases':rows,
        'numeric_screen_passed':all(row['passed'] for row in rows),
        'failed_cases':[row['id'] for row in rows if not row['passed']],
        'manual_quality_verified':False,'uses_existing_roi_screen':True}
    write(new/'encoder-comparison.json',result)
    print(json.dumps({key:value for key,value in result.items() if key!='cases'}),flush=True)


if __name__=='__main__':main()
