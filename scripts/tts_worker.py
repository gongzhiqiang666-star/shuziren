"""Persistent recovered IndexTTS provider, JSON-lines stdin/stdout, diagnostics stderr."""
import argparse
from contextlib import redirect_stdout
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import wave

from recovered.voice_infer_v3 import VoiceSynthesizer
from scripts.voice_store import VoiceStore
from scripts.v122_acceleration import configure_runtime
from scripts.tts_cache import AudioCache,file_hash,key_for


class OwnedSynthesizer(VoiceSynthesizer):
    def _get_temp_path(self):
        self.output_directory.mkdir(parents=True,exist_ok=True)
        return str(self.output_directory)


def normalize_task_wav(path):
    """Keep readable PCM intact and normalize other WAV encodings for playback."""
    try:
        with wave.open(str(path), 'rb'):
            return
    except wave.Error:
        pass
    normalized = path.with_name(f'{uuid.uuid4()}.wav')
    try:
        subprocess.run(
            ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
             '-map', '0:a:0', '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le',
             str(normalized)],
            check=True, timeout=60,
        )
        normalized.replace(path)
    finally:
        normalized.unlink(missing_ok=True)


class TTSProvider:
    def __init__(self, runtime_root, data_directory):
        self.data_directory=Path(data_directory).resolve()
        self.voices=VoiceStore(self.data_directory)
        self.outputs=self.data_directory/'tts'
        self.outputs.mkdir(parents=True,exist_ok=True)
        self.internal=configure_runtime(Path(runtime_root).resolve())
        self.synth=None;self.identity=None;self.loads=0;self.inference_calls=0;self.reference_switches=0
        self.cache=AudioCache(self.outputs/'content-cache');self.engine_stamp=None

    def _engine_stamp(self):
        if self.engine_stamp is None:
            import yaml
            model=self.internal/'assets/pretrained_models/indextts'
            config=yaml.safe_load((model/'config.yaml').read_text(encoding='utf-8'))
            files=[model/'config.yaml',model/config['gpt_checkpoint'],model/config['bigvgan_checkpoint'],model/'bpe.model',
                   Path(__file__),Path(sys.modules[VoiceSynthesizer.__module__].__file__)]
            files.extend(p for p in (self.internal/'bin/voice_infer_v3/indextts').rglob('*.py') if not p.name.startswith('._'))
            self.engine_stamp=hashlib.sha256(json.dumps([(str(p),file_hash(p)) for p in sorted(files)],sort_keys=True).encode()).hexdigest()
        return self.engine_stamp

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
        validation_started=time.perf_counter()
        voice=self.voices.get(request['voice_id'])
        cache_key=key_for(self._engine_stamp(),voice,request)
        cached=self.cache.get(cache_key) if request['use_cache'] else None
        validation_seconds=time.perf_counter()-validation_started
        identity=(voice['id'],voice['audio_sha256'],voice['text_sha256'])
        started=time.perf_counter();cold=False
        if cached is None and self.synth is None:
            synth=OwnedSynthesizer.from_voice_dir(str(self.internal/'assets/pretrained_models'),
                str(self.voices.root),voice['id'],device='cuda',voice_infer_version='v3')
            synth.output_directory=self.outputs/'cache'
            self.synth=synth;self.identity=identity;self.loads+=1;cold=True
        elif cached is None and identity!=self.identity:
            # IndexTTS refreshes prompt conditioning when its audio_prompt path changes.
            # VoiceStore references are immutable and each imported voice has its own path.
            self.synth.reference_audio=str(self.voices.audio_path(voice['id']))
            self.synth.reference_text=voice['transcript'];self.synth.voice_id=voice['id']
            self.identity=identity;self.reference_switches+=1
        initialization=time.perf_counter()-started
        started=time.perf_counter()
        if cached is None:
            self.inference_calls+=1
            path=self.synth.synthesize(request['text'],speed=speed,language=request['language'],use_cache=False)
        else: path=cached
        if not path or not Path(path).is_file(): raise ValueError('TTS未生成有效文件')
        path=Path(path).resolve()
        if path.parent not in {(self.outputs/'cache').resolve(),self.cache.root}: raise ValueError('TTS输出越界')
        if cached is None:
            normalize_task_wav(path)
        with wave.open(str(path),'rb') as reader:
            duration=reader.getnframes()/reader.getframerate()
            if duration<=0: raise ValueError('TTS输出为空')
            rate=reader.getframerate()
        if cached is None: self.cache.put(cache_key,path)
        target=self.outputs/(str(uuid.uuid4())+'.wav');shutil.copy2(path,target)
        if cached is None: path.unlink(missing_ok=True)  # Only this request's owned scratch output.
        return {'output':str(target),'duration':duration,'sample_rate':rate,'seconds':time.perf_counter()-started,
                'initialization_seconds':initialization,'model_loaded':cold,'model_load_count':self.loads,
                'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'voice_id':voice['id'],
                'provider':'recovered-voice-infer-v3','use_cache':request['use_cache'],
                'device':self.synth.device if self.synth is not None else 'cache',
                'cache_hit':cached is not None,'cache_key':cache_key,'inference_calls':self.inference_calls,
                'reference_switch_count':self.reference_switches,
                'validation_seconds':validation_seconds,'request_seconds':time.perf_counter()-validation_started}


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
