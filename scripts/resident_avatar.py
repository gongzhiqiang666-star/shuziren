"""Resident whole-utterance features and bounded-batch frame generation."""
import hashlib
import os
from pathlib import Path
import struct
import time
import wave

from scripts.avatar_render import verify_media
from scripts.avatar_store import digest
from scripts.v122_acceleration import configure_runtime,accelerated_unet


class ResidentAvatar:
    def __init__(self,runtime,avatar,cache):
        avatar=Path(avatar).resolve(strict=True);cache=Path(cache).resolve()
        os.environ['NVIDIA_TF32_OVERRIDE']='0';self.internal=configure_runtime(runtime)
        self.context=accelerated_unet(cache,backend='tensorrt',strict_fp32=True)
        self.sessions=self.context.__enter__();self.synth=None
        try:
            from recovered.image_clone_video_synthesizer import VideoSynthesizer
            models=self.internal/'assets/pretrained_models'
            self.synth=VideoSynthesizer(avatar,models/'image_infer_v2/unet_v2.onnx',models/'wenet/conf/train_conformer_multi_cn.yaml',models/'wenet/exp/conformer/wenetmodel.pt',batch_size=4)
        except BaseException:
            self.context.__exit__(None,None,None);raise
        self.session=None;self.frame_offset=0;self.wenet_loads=0

    def start(self,session):
        if not isinstance(session,str) or not session:raise ValueError('Session ID required')
        self.session=session;self.frame_offset=0;self.synth.current_frame_position=0;self.synth.is_forward=True

    def features(self,audio):
        loading=self.synth.wenet_model is None
        features=self.synth.extract_audio_features(audio)
        if loading:self.wenet_loads+=1
        fingerprint=hashlib.sha256()
        for feature in features:fingerprint.update(feature.tobytes())
        return features,fingerprint.hexdigest()

    def render(self,session,task_id,audio,output,pcm_sha256,progress=None):
        if session!=self.session:raise ValueError('Stale avatar session')
        audio=Path(audio).resolve(strict=True);output=Path(output).resolve()
        value=hashlib.sha256()
        with wave.open(str(audio),'rb') as source:
            if (source.getframerate(),source.getnchannels(),source.getsampwidth())!=(24000,1,2):raise ValueError('Expected 24kHz mono PCM16')
            for block in iter(lambda:source.readframes(24000),b''):value.update(block)
        if value.hexdigest()!=pcm_sha256:raise ValueError('Utterance PCM fingerprint changed')
        started=time.perf_counter();features,feature_sha=self.features(audio)
        stats=self.synth.engine.perf_stats
        for key in ['inference_ms','prepare_ms','paste_ms']:stats[key].clear()
        stats['frames']=stats['batches']=0
        feature_seconds=time.perf_counter()-started
        sequence=self.synth._generate_frame_sequence(len(features));first,_=self.synth._load_single_frame(sequence[0])
        from scripts.raw_video_writer import RawVideoWriter
        writer=RawVideoWriter(self.internal/'env/ffmpeg/bin/ffmpeg.exe',output,audio,first.shape[1],first.shape[0])
        offset=self.frame_offset;written=0;peak=0
        try:
            for start in range(0,len(features),self.synth.batch_size):
                indices=sequence[start:start+self.synth.batch_size]
                images,metadata=self.synth._load_batch_frames(indices)
                frames=self.synth._process_batch(images,metadata,features[start:start+len(indices)])
                if len(frames)!=len(indices):raise RuntimeError('Synthesizer dropped frames')
                peak=max(peak,len(frames))
                for frame in frames:
                    writer.write(frame);written+=1
                    if written==1 and progress:progress({'event':'first_frame_written','session_id':session,'task_id':task_id,'frame_index':offset,'source_index':sequence[0]})
            writer.release()
        except BaseException:
            writer.abort();raise
        self.frame_offset+=written
        try:media=verify_media(audio,output,self.internal/'env/ffmpeg/bin/ffmpeg.exe')
        except BaseException:
            output.unlink(missing_ok=True);raise
        return {**media,'session_id':session,'task_id':task_id,'output':str(output),
            'pcm_sha256':pcm_sha256,'audio_sha256':digest(audio),'output_sha256':digest(output),
            'frame_offset':offset,'next_frame_offset':self.frame_offset,
            'source_first':sequence[0],'source_last':sequence[-1],
            'source_sequence_sha256':hashlib.sha256(struct.pack('<'+'I'*len(sequence),*sequence)).hexdigest(),
            'features_sha256':feature_sha,'feature_seconds':feature_seconds,'total_seconds':time.perf_counter()-started,
            'unet_session_identity':id(self.sessions[0]),'wenet_identity':id(self.synth.wenet_model),
            'wenet_load_count':self.wenet_loads,'batch_capacity':self.synth.batch_size,'peak_returned_batch':peak,
            'synthesized_frames':stats['frames'],'inference_ms':sum(stats['inference_ms']),
            'output_device_tested':False,'visual_quality_verified':False}

    def close(self):
        if self.synth:
            self.synth.close();self.synth=None;self.context.__exit__(None,None,None)
