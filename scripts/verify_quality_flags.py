"""Independent local Whisper check of flagged cases; primary gates remain unchanged."""
import argparse
import json
from pathlib import Path
import time

from scripts.avatar_store import digest
from scripts.quality_metrics import content_score
from scripts.validate_quality_corpus import write


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-directory',required=True,type=Path)
    args=parser.parse_args();root=args.run_directory.resolve(strict=True)
    config=json.loads((root/'config.json').read_text(encoding='utf-8'))
    corpus=json.loads((root/'corpus.json').read_text(encoding='utf-8'))
    flagged=[item for item in corpus['items'] if not json.loads((root/'asr'/(item['id']+'.json')).read_text(encoding='utf-8'))['passed']]
    from scripts.v122_acceleration import configure_runtime
    internal=configure_runtime(config['runtime_root'])
    model_path=internal/'assets/pretrained_models/asr/whisper/large-v3.pt'
    if not model_path.is_file():raise FileNotFoundError('本地Whisper权重缺失；本工具不会自动下载')
    import torch
    import whisper
    from recovered.whisper_runtime import transcribe_with_whisper
    # Load on CPU first to avoid simultaneously holding a CUDA checkpoint and FP32 model.
    model=whisper.load_model(str(model_path),device='cpu')
    # Whisper's custom LayerNorm retains FP32 parameters even when decoding is FP16.
    if torch.cuda.is_available():model=model.to('cuda')
    report={'model':'local-whisper-large-v3','model_sha256':digest(model_path),'cases':[],
            'primary_thresholds_changed':False,'manual_listening_verified':False}
    try:
        for item in flagged:
            primary=json.loads((root/'asr'/(item['id']+'.json')).read_text(encoding='utf-8'))
            audio=json.loads((root/'tts'/(item['id']+'.json')).read_text(encoding='utf-8'))['result']
            delivered=json.loads((root/'tensorrt'/(item['id']+'.json')).read_text(encoding='utf-8'))
            if digest(audio['output'])!=audio['sha256'] or digest(delivered['output'])!=delivered['output_sha256']:
                raise ValueError('复核媒体指纹不符')
            value={'id':item['id'],'primary_asr':primary,'secondary':{}}
            for kind,path in [('input',audio['output']),('delivered',delivered['output'])]:
                start=time.perf_counter();result=transcribe_with_whisper(model,path,word_timestamps=False)
                text=result.get('text','')
                value['secondary'][kind]={'transcript':text,'seconds':time.perf_counter()-start,
                    **content_score(text,item,corpus['thresholds']['max_normalized_cer'])}
            report['cases'].append(value);write(root/'secondary-asr.json',report)
        print(json.dumps({'checked':len(flagged),'report':str(root/'secondary-asr.json')},ensure_ascii=False))
    finally:
        del model
        if torch.cuda.is_available():torch.cuda.empty_cache()


if __name__=='__main__':main()
