"""Build and verify immutable TTS model identity manifests outside the source package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


VERSION=1
ENGINES={
    'indextts':('indextts','recovered-voice-infer-v3'),
    'zipvoice':('zipvoice_distill','recovered-zipvoice'),
    'omnivoice':('omnivoice','recovered-omnivoice'),
}
LICENSE_STATUSES={'unverified','open_source','commercial','proprietary'}
IDENTITY_DIRECTORY='_internal/assets/model-identities'


def _reparse(path):
    attributes=getattr(path.lstat(),'st_file_attributes',0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def manifest_path(runtime_root,engine):
    if engine not in ENGINES: raise ValueError('不支持的TTS模型引擎')
    root=Path(runtime_root).resolve()
    return root/IDENTITY_DIRECTORY/(engine+'.json')


def _model_files(runtime_root,engine):
    root=Path(runtime_root).resolve();directory_name,_=ENGINES[engine]
    model_root=(root/'_internal/assets/pretrained_models'/directory_name)
    if not model_root.is_dir() or _reparse(model_root): raise ValueError('TTS模型目录不存在或不是普通目录')
    files=[]
    for candidate in sorted(model_root.rglob('*')):
        if not candidate.is_file() or candidate.name.startswith('._'): continue
        if _reparse(candidate) or not candidate.resolve(strict=True).is_relative_to(model_root.resolve()):
            raise ValueError('TTS模型目录包含链接或越界文件')
        files.append(candidate)
    if not files: raise ValueError('TTS模型目录为空')
    return root,model_root,files


def build(runtime_root,engine,license_status='unverified',license_reference=None):
    if engine not in ENGINES: raise ValueError('不支持的TTS模型引擎')
    if license_status not in LICENSE_STATUSES: raise ValueError('模型许可状态无效')
    if license_reference is not None and (not isinstance(license_reference,str) or not license_reference.strip()
                                           or len(license_reference.strip())>1000):
        raise ValueError('模型许可依据须为1至1000字')
    root,model_root,files=_model_files(runtime_root,engine)
    records=[]
    for path in files:
        records.append({'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':_digest(path)})
    canonical=json.dumps(records,sort_keys=True,separators=(',',':')).encode()
    manifest={'version':VERSION,'engine':engine,'provider':ENGINES[engine][1],
              'model_root':model_root.relative_to(root).as_posix(),'files':records,
              'aggregate_sha256':hashlib.sha256(canonical).hexdigest(),
              'license':{'status':license_status,'reference':license_reference.strip() if license_reference else None}}
    target=manifest_path(root,engine);target.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=target.parent,
                                         prefix=engine+'-',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name);json.dump(manifest,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);temporary=None
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return manifest


def load(runtime_root,engine):
    path=manifest_path(runtime_root,engine)
    try: manifest=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError): return None
    required={'version','engine','provider','model_root','files','aggregate_sha256','license'}
    if (not isinstance(manifest,dict) or set(manifest)!=required or manifest.get('version')!=VERSION
            or manifest.get('engine')!=engine or manifest.get('provider')!=ENGINES[engine][1]
            or not isinstance(manifest.get('files'),list) or not manifest['files']):
        raise ValueError('TTS模型身份清单格式无效')
    root=Path(runtime_root).resolve();expected_root=(root/'_internal/assets/pretrained_models'/ENGINES[engine][0]).resolve()
    names=[]
    for record in manifest['files']:
        if (not isinstance(record,dict) or set(record)!={'path','bytes','sha256'}
                or not isinstance(record['path'],str) or type(record['bytes']) is not int or record['bytes']<0
                or not isinstance(record['sha256'],str) or len(record['sha256'])!=64
                or any(char not in '0123456789abcdef' for char in record['sha256'])):
            raise ValueError('TTS模型身份文件记录无效')
        candidate=(root/record['path']).resolve()
        if not candidate.is_relative_to(expected_root) or candidate==expected_root:
            raise ValueError('TTS模型身份文件路径越界')
        names.append(record['path'])
    if names!=sorted(names) or len(names)!=len(set(names)) or manifest['model_root']!=expected_root.relative_to(root).as_posix():
        raise ValueError('TTS模型身份文件清单顺序或根目录无效')
    canonical=json.dumps(manifest['files'],sort_keys=True,separators=(',',':')).encode()
    if hashlib.sha256(canonical).hexdigest()!=manifest['aggregate_sha256']:
        raise ValueError('TTS模型身份清单摘要无效')
    license_record=manifest.get('license')
    if (not isinstance(license_record,dict) or set(license_record)!={'status','reference'}
            or license_record.get('status') not in LICENSE_STATUSES
            or (license_record.get('reference') is not None and (
                not isinstance(license_record['reference'],str) or not license_record['reference'].strip()
                or len(license_record['reference'])>1000))):
        raise ValueError('TTS模型许可记录无效')
    manifest['manifest_sha256']=_digest(path)
    return manifest


def verify(runtime_root,engine):
    root,model_root,files=_model_files(runtime_root,engine);manifest=load(root,engine)
    if manifest is None: raise ValueError('缺少TTS模型身份清单')
    actual=[]
    for path in files:
        actual.append({'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':_digest(path)})
    mismatches=[]
    expected={item['path']:(item['bytes'],item['sha256']) for item in manifest['files']}
    measured={item['path']:(item['bytes'],item['sha256']) for item in actual}
    for name in sorted(expected.keys()|measured.keys()):
        if expected.get(name)!=measured.get(name): mismatches.append(name)
    return {'verified':not mismatches,'engine':engine,'files':len(actual),'mismatches':mismatches,
            'aggregate_sha256':manifest['aggregate_sha256'],'license':manifest['license']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('build','verify'))
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--engine',required=True,choices=tuple(ENGINES))
    parser.add_argument('--license-status',choices=tuple(sorted(LICENSE_STATUSES)),default='unverified')
    parser.add_argument('--license-reference')
    args=parser.parse_args(argv)
    result=(build(args.runtime_root,args.engine,args.license_status,args.license_reference)
            if args.command=='build' else verify(args.runtime_root,args.engine))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if args.command=='build' or result['verified'] else 1


if __name__=='__main__': raise SystemExit(main())
