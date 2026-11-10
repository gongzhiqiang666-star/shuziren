"""V04-Q1 offline 50-case speech/CUDA/FP16/ASR comparison, resumable by stage."""
import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from scripts.avatar_store import AvatarStore,digest
from scripts.avatar_tasks import AvatarTasks

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/'scripts/fixtures/v04-quality-corpus.json'
PROTOCOL=ROOT/'docs/V04_QUALITY_PROTOCOL.md'


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)


def progress(root,stage,phase,item=None):
    write(root/'progress.json',{'stage':stage,'phase':phase,'item':item,'utc':time.time()})


class Resources:
    def __init__(self):
        self.stop=threading.Event();self.values={'rss_peak_bytes':None,'cpu_percent_peak':None,
            'whole_gpu_peak_mb':None,'process_gpu_peak_mb':None,'gpu_scope':'whole GPU includes other applications; process VRAM unavailable'}
    def start(self):
        self.thread=threading.Thread(target=self._sample,daemon=True);self.thread.start()
    def _sample(self):
        import psutil
        process=psutil.Process();last_gpu=0
        while not self.stop.is_set():
            try:
                rss=process.memory_info().rss;cpu=process.cpu_percent()
                for child in process.children(recursive=True):
                    try:rss+=child.memory_info().rss
                    except psutil.NoSuchProcess:pass
                self.values['rss_peak_bytes']=max(self.values['rss_peak_bytes'] or 0,rss)
                self.values['cpu_percent_peak']=max(self.values['cpu_percent_peak'] or 0,cpu)
                if time.monotonic()-last_gpu>=2:
                    last_gpu=time.monotonic()
                    result=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],
                        capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if result.returncode==0:
                        used=int(result.stdout.splitlines()[0].strip())
                        self.values['whole_gpu_peak_mb']=max(self.values['whole_gpu_peak_mb'] or 0,used)
            except (OSError,ValueError,subprocess.TimeoutExpired,psutil.Error):pass
            self.stop.wait(.5)
    def close(self):
        self.stop.set();self.thread.join(timeout=6)
        return self.values


def worker(root,stage):
    if stage in {'cuda','tensorrt'}:os.environ['NVIDIA_TF32_OVERRIDE']='0'
    config=json.loads((root/'config.json').read_text(encoding='utf-8'))
    corpus=json.loads((root/'corpus.json').read_text(encoding='utf-8'));items=corpus['items']
    if digest(root/'corpus.json')!=config['corpus_sha256'] or digest(PROTOCOL)!=config['protocol_sha256']:
        raise ValueError('语料/协议已变化，需新建实验版本')
    runtime=Path(config['runtime_root']);avatar=AvatarStore(root).directory(config['avatar_id'])
    destination=root/stage;destination.mkdir(exist_ok=True);resource=Resources();resource.start()
    stage_report={'stage':stage,'execution_status':'failed','driver_sha256':digest(__file__)}
    try:
        if stage=='tts':
            from scripts.tts_worker import TTSProvider
            provider=TTSProvider(runtime,root)
            try:
                for item in items:
                    progress(root,stage,'case',item['id'])
                    result=provider.synthesize({'voice_id':config['voice_id'],'text':item['text'],
                        'speed':item['speed'],'language':'zh-CN','use_cache':False})
                    if result['cache_hit'] or result['model_load_count']!=1:raise ValueError('禁缓存/模型复用验证失败')
                    write(destination/(item['id']+'.json'),{'status':'passed','item':item['id'],'result':result})
            finally:provider.close()
        elif stage in {'cuda','tensorrt'}:
            from scripts.v122_acceleration import configure_runtime,accelerated_unet
            internal=configure_runtime(runtime)
            from recovered.image_clone_video_synthesizer import VideoSynthesizer
            from scripts.avatar_render import verify_media
            import numpy as np
            import onnxruntime as ort
            models=internal/'assets/pretrained_models';initialized=time.perf_counter()
            stage_report['arena_limit_gb']=8 if stage=='cuda' else 4
            stage_report['model_sha256']={str(path.relative_to(internal)):digest(path) for path in [
                models/'image_infer_v2/unet_v2.onnx',models/'wenet/exp/conformer/wenetmodel.pt',
                models/'wenet/conf/train_conformer_multi_cn.yaml']}
            with accelerated_unet(config['engine_cache'],backend=stage,memory_gb=stage_report['arena_limit_gb'],profile_directory=destination/'profiles',strict_fp32=True) as sessions:
                with VideoSynthesizer(avatar,models/'image_infer_v2/unet_v2.onnx',models/'wenet/conf/train_conformer_multi_cn.yaml',
                    models/'wenet/exp/conformer/wenetmodel.pt',device='cuda:0',batch_size=4) as synth:
                    encoder=config.get('video_encoder','legacy')
                    if encoder not in {'legacy','libx264','h264_nvenc'}:raise ValueError('未知视频编码方案')
                    stage_report['video_encoder']=encoder
                    if encoder!='legacy':
                        from scripts.raw_video_writer import RawVideoWriter
                        synth.frame_writer_factory=lambda target,audio,width,height:RawVideoWriter(internal/'env/ffmpeg/bin/ffmpeg.exe',target,audio,width,height,encoder)
                    stage_report['initialization_seconds']=time.perf_counter()-initialized
                    stage_report['ort_version']=ort.__version__
                    options=sessions[0].get_provider_options()
                    stage_report['provider_options']=options
                    stage_report['tf32_control']={'NVIDIA_TF32_OVERRIDE':os.environ.get('NVIDIA_TF32_OVERRIDE'),
                        'provider_option':options.get('CUDAExecutionProvider',{}).get('use_tf32'),
                        'method':'NVIDIA process-start override; provider option additionally set where supported'}
                    if os.environ.get('NVIDIA_TF32_OVERRIDE')!='0' or options.get('CUDAExecutionProvider',{}).get('use_tf32','0')!='0':
                        raise RuntimeError('本机未确认禁用TF32，不能声称严格FP32基线')
                    for index,item in enumerate(items):
                        progress(root,stage,'cold_case' if index==0 else 'case',item['id'])
                        source=json.loads((root/'tts'/(item['id']+'.json')).read_text(encoding='utf-8'))['result']
                        audio=Path(source['output']);output=destination/(item['id']+'.mp4')
                        if digest(audio)!=source['sha256']:raise ValueError('输入音频已变化')
                        synth.current_frame_position=0;synth.is_forward=True
                        stats=synth.engine.perf_stats;before={key:len(stats[key]) for key in ['inference_ms','prepare_ms','paste_ms']}
                        start=time.perf_counter();synth.process_single_file(audio,output);seconds=time.perf_counter()-start
                        verify_started=time.perf_counter();media=verify_media(audio,output,internal/'env/ffmpeg/bin/ffmpeg.exe')
                        result={'status':'passed','item':item['id'],'backend':stage,'video_encoder':encoder,'cold':index==0,
                            'audio_sha256':source['sha256'],'output':str(output),'output_sha256':digest(output),
                            'process_seconds':seconds,'pipeline_timings':synth.last_process_timings,
                            'verification_seconds':time.perf_counter()-verify_started,**media,
                            **{key:sum(stats[key][before[key]:]) for key in before}}
                        write(destination/(item['id']+'.json'),result)
                        if index==0:
                            progress(root,stage,'warming_profiles',item['id'])
                            features=synth.extract_audio_features(audio)
                            warm_started=time.perf_counter()
                            for size in [1,2,3,4]:
                                progress(root,stage,'warming_profiles',str(size))
                                images,metadata=synth._load_batch_frames(list(range(size)))
                                synth._process_batch(images,metadata,features[:size])
                            stage_report['warm_profiles_seconds']=time.perf_counter()-warm_started
                            counts={}
                            for session in sessions:
                                events=json.loads(Path(session.end_profiling()).read_text(encoding='utf-8'))
                                for event in events:
                                    provider=event.get('args',{}).get('provider')
                                    if provider:counts[provider]=counts.get(provider,0)+1
                            stage_report['executed_node_provider_counts']=counts
                            expected='CUDAExecutionProvider' if stage=='cuda' else 'TensorrtExecutionProvider'
                            if not counts.get(expected):raise RuntimeError('所选后端未执行模型节点')
                    stage_report['providers']=[session.get_providers() for session in sessions]
        elif stage=='asr':
            os.environ['HF_HUB_OFFLINE']='1';os.environ['MODELSCOPE_OFFLINE']='1'
            os.environ['PATH']=str(runtime/'_internal/env/ffmpeg/bin')+os.pathsep+os.environ.get('PATH','')
            from recovered.funasr_runtime import load_funasr_model,transcribe_with_funasr,funasr_result_to_text
            from scripts.quality_metrics import content_score
            model=load_funasr_model(str(runtime/'_internal/assets/pretrained_models/asr'),prefer_fallback=True)
            for item in items:
                progress(root,stage,'case',item['id'])
                source=json.loads((root/'tts'/(item['id']+'.json')).read_text(encoding='utf-8'))['result']
                if digest(source['output'])!=source['sha256']:raise ValueError('ASR输入音频已变化')
                text=funasr_result_to_text(transcribe_with_funasr(model,source['output'],sentence_timestamp=False))
                write(destination/(item['id']+'.json'),{'item':item['id'],'transcript':text,
                    **content_score(text,item,corpus['thresholds']['max_normalized_cer'])})
        elif stage=='compare':
            from scripts.quality_metrics import compare_videos
            for item in items:
                progress(root,stage,'case',item['id'])
                value=compare_videos(root/'cuda'/(item['id']+'.mp4'),root/'tensorrt'/(item['id']+'.mp4'),avatar,corpus['thresholds'])
                write(destination/(item['id']+'.json'),{'item':item['id'],**value})
        else:raise ValueError('Unknown stage')
        stage_report['execution_status']='completed'
    except Exception as error:
        stage_report.update(error_type=type(error).__name__,error=str(error));raise
    finally:
        stage_report['resources']=resource.close();write(destination/'stage.json',stage_report)
        progress(root,stage,stage_report['execution_status'])


def prepare(args):
    from scripts.voice_store import VoiceStore
    root=(args.report_directory/('run-'+uuid.uuid4().hex)).resolve();root.mkdir(parents=True)
    source=VoiceStore(args.source_voice_data);reference=source.get(source.selected());voices=VoiceStore(root)
    voice=voices.import_audio(source.audio_path(reference['id']),reference['transcript'],'固定质量验收参考',
                             args.runtime_root/'_internal/env/ffmpeg/bin/ffmpeg.exe')
    voices.select(voice['id']);avatars=AvatarStore(root)
    avatar=avatars.import_prepared(args.avatar_directory.resolve(),'固定质量验收形象');avatars.select(avatar['id'])
    (root/'corpus.json').write_bytes(CORPUS.read_bytes())
    (root/'protocol.md').write_bytes(PROTOCOL.read_bytes())
    write(root/'config.json',{'runtime_root':str(args.runtime_root.resolve()),'voice_id':voice['id'],'avatar_id':avatar['id'],
        'corpus_sha256':digest(root/'corpus.json'),'protocol_sha256':digest(PROTOCOL),
        'engine_cache':str(args.engine_cache.resolve() if args.engine_cache else root/'engine-cache'),
        'source_sha256':{str(path.relative_to(ROOT)):digest(path) for path in [ROOT/'scripts/tts_worker.py',
            ROOT/'recovered/voice_infer_v3.py',ROOT/'recovered/image_clone_video_synthesizer.py',
            ROOT/'recovered/image_frame_synthesizer_runtime.py',ROOT/'scripts/v122_acceleration.py',
            ROOT/'scripts/avatar_render.py',ROOT/'scripts/quality_metrics.py',ROOT/'scripts/raw_video_writer.py',Path(__file__)]}})
    return root


def run_stage(root,stage):
    config=json.loads((root/'config.json').read_text(encoding='utf-8'))
    for relative,expected in config['source_sha256'].items():
        if digest(ROOT/relative)!=expected:raise ValueError('推理源码已变化，需要新实验或明确迁移已有音频')
    progress(root,stage,'starting')
    with (root/(stage+'-worker.log')).open('wb') as log:
        process=subprocess.Popen([str(Path(config['runtime_root'])/'_internal/env/python.exe'),'-X','utf8',
            '-m','scripts.validate_quality_corpus','--run-directory',str(root),'--worker-stage',stage],
            cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=os.name!='nt')
        last=None;changed=time.monotonic()
        try:
            while process.poll() is None:
                value=json.loads((root/'progress.json').read_text(encoding='utf-8'))
                if value!=last:last=value;changed=time.monotonic()
                limit=360 if value['phase'] in {'starting','cold_case','warming_profiles'} else 180
                if time.monotonic()-changed>limit:raise TimeoutError('阶段无进展超时，终止本次自有进程树')
                time.sleep(.5)
            if process.returncode:raise RuntimeError(f'{stage}阶段失败，见{stage}-worker.log')
        finally:AvatarTasks._terminate(process)


def summarize(root):
    import numpy as np
    corpus=json.loads((root/'corpus.json').read_text(encoding='utf-8'));thresholds=corpus['thresholds']
    result={'execution_status':'completed','protocol':corpus['version'],'candidate_backend':'tensorrt','manual_quality_status':'pending','cases':[],'backend_capacity':{}}
    for item in corpus['items']:
        asr=json.loads((root/'asr'/(item['id']+'.json')).read_text(encoding='utf-8'))
        comparison=json.loads((root/'compare'/(item['id']+'.json')).read_text(encoding='utf-8'))
        result['cases'].append({'id':item['id'],'category':item['category'],'asr':asr,'comparison':comparison,'manual_pass':None})
    for backend in ['cuda','tensorrt']:
        values=[json.loads((root/backend/(item['id']+'.json')).read_text(encoding='utf-8')) for item in corpus['items']]
        warm=[item for item in values if not item['cold']]
        fps=sum(item['frames'] for item in warm)/sum(item['process_seconds'] for item in warm)
        p95=float(np.percentile([item['process_seconds']*1000/item['frames'] for item in warm],95))
        result['backend_capacity'][backend]={'warm_frames_per_second':fps,'frame_ms_p95':p95,
            'passed':fps>=thresholds['min_warm_render_capacity_fps'] and p95<=thresholds['warm_frame_ms_p95_max']}
    result['content_failures']=[item['id'] for item in result['cases'] if not item['asr']['passed']]
    result['precision_failures']=[item['id'] for item in result['cases'] if not item['comparison']['passed']]
    result['automatic_pass']=not result['content_failures'] and not result['precision_failures'] and result['backend_capacity']['tensorrt']['passed']
    result['acceptance_status']='pending_manual' if result['automatic_pass'] else 'failed_automatic'
    write(root/'result.json',result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runtime-root',type=Path);parser.add_argument('--source-voice-data',type=Path)
    parser.add_argument('--avatar-directory',type=Path);parser.add_argument('--report-directory',type=Path)
    parser.add_argument('--engine-cache',type=Path);parser.add_argument('--run-directory',type=Path)
    parser.add_argument('--stage',choices=['all','tts','cuda','tensorrt','asr','compare'],default='all')
    parser.add_argument('--worker-stage',choices=['tts','cuda','tensorrt','asr','compare'])
    args=parser.parse_args()
    if args.worker_stage:
        with redirect_stdout(sys.stderr):worker(args.run_directory.resolve(),args.worker_stage)
        return 0
    if args.run_directory is None and not all([args.runtime_root,args.source_voice_data,args.avatar_directory,args.report_directory]):
        parser.error('新实验需要runtime-root/source-voice-data/avatar-directory/report-directory')
    root=args.run_directory.resolve() if args.run_directory else prepare(args)
    print(json.dumps({'run_directory':str(root)},ensure_ascii=False),flush=True)
    try:
        for stage in ['tts','cuda','tensorrt','asr','compare'] if args.stage=='all' else [args.stage]:
            run_stage(root,stage)
        if args.stage in {'all','compare'}:
            result=summarize(root);print(json.dumps({'acceptance_status':result['acceptance_status'],'report':str(root/'result.json')},ensure_ascii=False))
        return 0
    except Exception as error:
        write(root/'failure.json',{'error_type':type(error).__name__,'error':str(error)})
        print(json.dumps({'execution_status':'failed','error':str(error),'run_directory':str(root)},ensure_ascii=False),flush=True)
        return 1


if __name__=='__main__':raise SystemExit(main())
