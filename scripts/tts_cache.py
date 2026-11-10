"""Content-verified non-executable audio cache for the console provider."""
import hashlib
import json
from pathlib import Path
import shutil
import uuid


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    return digest.hexdigest()


def key_for(engine,voice,request):
    payload={'format':1,'engine':engine,'voice_id':voice['id'],'audio':voice['audio_sha256'],
             'reference_text':voice['text_sha256'],'text':request['text'],'speed':float(request['speed']),
             'language':request['language']}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class AudioCache:
    def __init__(self,root,max_entries=128,max_bytes=256*1024*1024):
        self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.max_entries=max_entries;self.max_bytes=max_bytes

    def paths(self,key):
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key): raise ValueError('Invalid cache key')
        audio=self.root/(key+'.wav');meta=self.root/(key+'.json')
        if audio.resolve().parent!=self.root or meta.resolve().parent!=self.root: raise ValueError('Cache path escapes root')
        return audio,meta

    def get(self,key):
        audio,meta=self.paths(key)
        try:
            record=json.loads(meta.read_text(encoding='utf-8'))
            if record.get('key')==key and record.get('sha256')==file_hash(audio): return audio
        except (OSError,ValueError,AttributeError): pass
        return None

    def put(self,key,source):
        audio,meta=self.paths(key)
        temporary=self.root/(uuid.uuid4().hex+'.tmp')
        try:
            shutil.copy2(source,temporary);digest=file_hash(temporary);temporary.replace(audio)
            temporary.write_text(json.dumps({'key':key,'sha256':digest}),encoding='utf-8');temporary.replace(meta)
            self.prune()
        finally:
            temporary.unlink(missing_ok=True)

    def prune(self):
        entries=[]
        for meta in self.root.glob('*.json'):
            try:
                audio,owned_meta=self.paths(meta.stem)
                if audio.is_file(): entries.append((owned_meta.stat().st_mtime_ns,audio,owned_meta,audio.stat().st_size))
            except (OSError,ValueError): continue
        total=sum(entry[3] for entry in entries)
        count=len(entries)
        for _,audio,meta,size in sorted(entries):
            if count<=self.max_entries and total<=self.max_bytes: break
            audio.unlink(missing_ok=True);meta.unlink(missing_ok=True);total-=size;count-=1
