"""Persistent recovered IndexTTS provider, JSON-lines stdin/stdout, diagnostics stderr."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid
import wave

from recovered.voice_infer_v3 import VoiceSynthesizer
from scripts.voice_store import VoiceStore
from scripts.v122_acceleration import configure_runtime


class OwnedSynthesizer(VoiceSynthesizer):
    def _get_temp_path(self):
        self.output_directory.mkdir(parents=True,exist_ok=True)
        return str(self.output_directory)


class TTSProvider:
    def __init__(self, runtime_root, data_directory):
        self.data_directory=Path(data_directory).resolve()
        self.voices=VoiceStore(self.data_directory)
        self.outputs=self.data_directory/'tts'
        self.outputs.mkdir(parents=True,exist_ok=True)
        self.internal=configure_runtime(Path(runtime_root).resolve())
        self.synth=None;self.identity=None;self.loads=0

    def close(self):
        if self.synth is not None:
            self.synth.clear();self.synth=None;self.identity=None

    def synthesize(self, request):
        if not isinstance(request,dict) or set(request)!={'voice_id','text','speed','language','use_cache'}:
            raise ValueError('TTS请求字段无效')
        if not isinstance(request['text'],str) or not 1<=len(request['text'].strip())<=2000:
            raise ValueError('合成文本须为1至2000字')
        speed=request['speed']
        if type(speed) not in (int,float) or not .5<=speed<=2:
            raise ValueError('语速须在0.5至2之间')
        if not isinstance(request['language'],str) or not request['language']:
            raise ValueError('请选择语言')
        if type(request['use_cache']) is not bool: raise ValueError('缓存参数须为布尔值')
        voice=self.voices.get(request['voice_id'])
        identity=(voice['id'],voice['audio_sha256'],voice['text_sha256'])
        started=time.perf_counter();cold=False
        if identity!=self.identity:
            self.close()
            synth=OwnedSynthesizer.from_voice_dir(str(self.internal/'assets/pretrained_models'),
                str(self.voices.root),voice['id'],device='cuda',voice_infer_version='v3')
            synth.output_directory=self.outputs/'cache'
            self.synth=synth;self.identity=identity;self.loads+=1;cold=True
        initialization=time.perf_counter()-started
        started=time.perf_counter()
        path=self.synth.synthesize(request['text'],speed=speed,language=request['language'],use_cache=request['use_cache'])
        if not path or not Path(path).is_file(): raise ValueError('TTS未生成有效文件')
        path=Path(path).resolve()
        if path.parent!=(self.outputs/'cache').resolve(): raise ValueError('TTS输出越界')
        with wave.open(str(path),'rb') as reader:
            duration=reader.getnframes()/reader.getframerate()
            if duration<=0: raise ValueError('TTS输出为空')
            rate=reader.getframerate()
        target=self.outputs/(str(uuid.uuid4())+'.wav');shutil.copy2(path,target)
        return {'output':str(target),'duration':duration,'sample_rate':rate,'seconds':time.perf_counter()-started,
                'initialization_seconds':initialization,'model_loaded':cold,'model_load_count':self.loads,
                'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'voice_id':voice['id'],
                'provider':'recovered-voice-infer-v3','use_cache':request['use_cache'],'device':self.synth.device}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--data-directory',required=True,type=Path)
    args=parser.parse_args(argv)
    with redirect_stdout(sys.stderr): provider=TTSProvider(args.runtime_root,args.data_directory)
    print(json.dumps({'event':'ready','provider':'recovered-voice-infer-v3'}),flush=True)
    try:
        for line in sys.stdin:
            try:
                request=json.loads(line)
                if request=={'action':'close'}: break
                with redirect_stdout(sys.stderr): result=provider.synthesize(request)
                print(json.dumps({'ok':True,'result':result},ensure_ascii=False),flush=True)
            except Exception as error:
                # Detailed model diagnostics stay in the owned stderr log, not success output.
                print(type(error).__name__,str(error),file=sys.stderr,flush=True)
                print(json.dumps({'ok':False,'error':'TTS_FAILED: 请检查输入、参考音、模型和工作进程日志'}),flush=True)
    finally:
        with redirect_stdout(sys.stderr): provider.close()
    return 0


if __name__=='__main__': raise SystemExit(main())
