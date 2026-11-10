"""Restored offline avatar render shared by the product worker and validation CLI."""
import json
import os
from pathlib import Path
import subprocess
import time
import wave

from scripts.avatar_store import digest
from scripts.v122_acceleration import configure_runtime, accelerated_unet


def verify_media(audio,output,ffmpeg):
    audio=Path(audio);output=Path(output);ffmpeg=Path(ffmpeg)
    probe=json.loads(subprocess.check_output([str(ffmpeg.with_name('ffprobe.exe')),'-v','error',
        '-show_streams','-show_format','-of','json',str(output)],text=True,timeout=30))
    video=next(item for item in probe['streams'] if item['codec_type']=='video')
    sound=next(item for item in probe['streams'] if item['codec_type']=='audio')
    if video['avg_frame_rate']!='25/1' or abs(float(video['duration'])-float(sound['duration']))>.08:
        raise RuntimeError('视频帧率或音轨时长检查未通过')
    subprocess.run([str(ffmpeg),'-nostdin','-v','error','-i',str(output),'-f','null','-'],
                   capture_output=True,check=True,timeout=60)
    def samples(path):
        try:
            with wave.open(str(path)) as reader:
                if reader.getframerate()==24000 and reader.getnchannels()==1 and reader.getsampwidth()==2:
                    return reader.getnframes()
        except wave.Error:pass
        decoded=subprocess.run([str(ffmpeg),'-nostdin','-v','error','-i',str(path),'-vn',
            '-ac','1','-ar','24000','-c:a','pcm_s16le','-f','s16le','pipe:1'],capture_output=True,check=True,timeout=60)
        return len(decoded.stdout)//2
    original=samples(audio);decoded=samples(output)
    if decoded<original:raise RuntimeError(f'视频音轨发生截尾：输入{original}，解码{decoded}采样')
    return {'frames':int(video['nb_frames']),'width':video['width'],'height':video['height'],
        'video_duration':float(video['duration']),'audio_duration':float(sound['duration']),
        'input_audio_samples':original,'decoded_audio_samples':decoded,'audio_complete':True,'full_decode_passed':True}


def render(runtime_root, avatar, audio, output, backend='cuda', cache=None, profile=False,encoder='legacy',strict_precision=False):
    if encoder not in {'legacy','libx264','h264_nvenc'}:raise ValueError('未知视频编码方案')
    if strict_precision:os.environ['NVIDIA_TF32_OVERRIDE']='0'
    avatar=Path(avatar).resolve(strict=True);audio=Path(audio).resolve(strict=True)
    output=Path(output).resolve()
    if output.exists():
        raise ValueError('视频输出必须是新文件')
    output.parent.mkdir(parents=True,exist_ok=True)
    cache=Path(cache).resolve() if cache else output.parent/'engine-cache'
    internal=configure_runtime(runtime_root)
    from recovered.image_clone_video_synthesizer import VideoSynthesizer
    before=digest(audio);models=internal/'assets/pretrained_models';started=time.perf_counter()
    counts={}
    with accelerated_unet(cache,backend=backend,profile_directory=output.parent/'profiles' if profile else None,strict_fp32=strict_precision) as sessions:
        with VideoSynthesizer(avatar,models/'image_infer_v2/unet_v2.onnx',
            models/'wenet/conf/train_conformer_multi_cn.yaml',models/'wenet/exp/conformer/wenetmodel.pt',
            device='cuda:0',batch_size=4) as synth:
            if encoder!='legacy':
                from scripts.raw_video_writer import RawVideoWriter
                synth.frame_writer_factory=lambda target,sound,width,height:RawVideoWriter(internal/'env/ffmpeg/bin/ffmpeg.exe',target,sound,width,height,encoder)
            initialized=time.perf_counter()
            synth.process_single_file(audio,output)
            stats=synth.engine.perf_stats
            providers=[session.get_providers() for session in sessions]
            if profile:
                for session in sessions:
                    events=json.loads(Path(session.end_profiling()).read_text(encoding='utf-8'))
                    for event in events:
                        provider=event.get('args',{}).get('provider')
                        if provider:counts[provider]=counts.get(provider,0)+1
                expected='TensorrtExecutionProvider' if backend=='tensorrt' else 'CUDAExecutionProvider'
                if not counts.get(expected):raise RuntimeError('所选推理后端未执行模型节点')
    elapsed=time.perf_counter()-started
    if not providers or stats['frames']<=0:raise RuntimeError('视频没有实际执行人脸推理')
    ffmpeg=internal/'env/ffmpeg/bin/ffmpeg.exe'
    media=verify_media(audio,output,ffmpeg)
    if digest(audio)!=before:raise RuntimeError('输入音频在合成中发生变化')
    result={'provider':'restored-offline-avatar','backend':backend,'video_encoder':encoder,'output':str(output),
        'audio_sha256':before,'output_sha256':digest(output),'providers':providers,
        **media,
        'initialization_seconds':initialized-started,'total_seconds':elapsed,
        'pipeline_timings':synth.last_process_timings,
        'synthesis_batches':stats['batches'],'synthesized_frames':stats['frames'],
        'inference_ms':sum(stats['inference_ms']),'prepare_ms':sum(stats['prepare_ms']),
        'paste_ms':sum(stats['paste_ms']),'engine_cache':str(cache),'full_decode_passed':True,
        'live_tested':False,'visual_quality_verified':False}
    if profile:result['executed_node_provider_counts']=counts
    return result
