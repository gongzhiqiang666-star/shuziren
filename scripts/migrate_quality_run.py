"""Carry verified unchanged speech/scoring into a new, explicitly amended experiment."""
import argparse
import json
from pathlib import Path
import shutil
import uuid

from scripts.avatar_store import AvatarStore,digest
from scripts.voice_store import VoiceStore
from scripts.validate_quality_corpus import ROOT,CORPUS,PROTOCOL,write


def migrate(source,report_directory,reason):
    source=Path(source).resolve(strict=True)
    old=json.loads((source/'config.json').read_text(encoding='utf-8'))
    known={relative.replace('\\','/'):value for relative,value in old['source_sha256'].items()}
    before=json.loads((source/'corpus.json').read_text(encoding='utf-8'))
    after=json.loads(CORPUS.read_text(encoding='utf-8'))
    if before['items']!=after['items'] or before['thresholds']!=after['thresholds']:
        raise ValueError('语料/速度/等价形式/门槛变化，禁止复用本迁移路径')
    for relative in ['scripts/tts_worker.py','recovered/voice_infer_v3.py','scripts/quality_metrics.py']:
        if digest(ROOT/relative)!=known[relative]:
            raise ValueError('语音或评分实现变化，不能把旧阶段当新实现通过')
    if json.loads((source/'tts/stage.json').read_text())['execution_status']!='completed':
        raise ValueError('源语音阶段未完成')
    target=(Path(report_directory)/('run-'+uuid.uuid4().hex)).resolve();target.mkdir(parents=True)
    for name in ['voices','avatars','tts']:shutil.copytree(source/name,target/name)
    hashes={}
    for item in before['items']:
        path=target/'tts'/(item['id']+'.json');value=json.loads(path.read_text(encoding='utf-8'))
        original=Path(value['result']['output']);copied=target/'tts'/original.name
        if digest(original)!=value['result']['sha256'] or digest(copied)!=value['result']['sha256']:
            raise ValueError('携带语音指纹不符')
        if value['result']['cache_hit'] or value['result']['use_cache']:
            raise ValueError('源语音不是禁缓存生成证据')
        hashes[item['id']]=value['result']['sha256'];value['result']['output']=str(copied);write(path,value)
    preserved=['tts']
    asr=source/'asr/stage.json'
    if asr.exists() and json.loads(asr.read_text())['execution_status']=='completed':
        if not all((source/'asr'/(item['id']+'.json')).is_file() for item in before['items']):
            raise ValueError('源ASR项目不完整')
        shutil.copytree(source/'asr',target/'asr');preserved.append('asr')
    (target/'corpus.json').write_bytes(CORPUS.read_bytes());(target/'protocol.md').write_bytes(PROTOCOL.read_bytes())
    write(target/'config.json',{**old,'corpus_sha256':digest(target/'corpus.json'),'protocol_sha256':digest(PROTOCOL),
        'engine_cache':str(target/'engine-cache'),'source_sha256':{relative:digest(ROOT/relative) for relative in known}})
    for name in preserved:
        stage=json.loads((target/name/'stage.json').read_text());stage['carried_from']=str(source);write(target/name/'stage.json',stage)
    write(target/'migration.json',{'from':str(source),'reason':reason,'preserved_stages':preserved,
        'source_config_sha256':digest(source/'config.json'),'same_case_items':True,'same_thresholds':True,'verified_wav_sha256':hashes})
    VoiceStore(target).get(old['voice_id']);AvatarStore(target).get(old['avatar_id'])
    return target


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--report-directory',required=True,type=Path);parser.add_argument('--reason',required=True)
    args=parser.parse_args();target=migrate(args.source,args.report_directory,args.reason)
    print(json.dumps({'run_directory':str(target)},ensure_ascii=False))


if __name__=='__main__':main()
