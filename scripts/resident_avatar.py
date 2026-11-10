"""Resident whole-utterance features and bounded-batch frame generation."""
import hashlib
import os
from pathlib import Path
import struct
import time
import tempfile
import wave

from scripts.avatar_render import verify_media
from scripts.avatar_store import digest
from scripts.v122_acceleration import configure_runtime,accelerated_unet
from scripts.sample_timeline import parse_span,feature_indices


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
            from scripts.verified_avatar_reader import VerifiedAvatarReader
            self.synth._load_single_frame=VerifiedAvatarReader(avatar,self.synth.total_frames).load
        except BaseException:
            self.context.__exit__(None,None,None);raise
        self.session=None;self.frame_offset=0;self.sample_offset=0;self.timed_mode=None;self.wenet_loads=0;self.prepared=False;self.prepare_result=None;self.silence_features=None

    def start(self,session):
        if not isinstance(session,str) or not session:raise ValueError('Session ID required')
        self.session=session;self.frame_offset=0;self.sample_offset=0;self.timed_mode=None;self.synth.current_frame_position=0;self.synth.is_forward=True

    def features(self,audio):
        loading=self.synth.wenet_model is None
        features=self.synth.extract_audio_features(audio)
        if loading:self.wenet_loads+=1
        fingerprint=hashlib.sha256()
        for feature in features:fingerprint.update(feature.tobytes())
        return features,fingerprint.hexdigest()

    def prepare(self):
        if self.prepared:return {**self.prepare_result,'reused':True,'frame_offset':self.frame_offset,'sample_offset':self.sample_offset}
        started=time.perf_counter()
        position=(self.synth.current_frame_position,self.synth.is_forward,self.frame_offset,self.sample_offset)
        # Scratch is private and short-lived; prewarming never writes audible media.
        with tempfile.TemporaryDirectory(prefix='shuziren-warm-') as temporary:
            audio=Path(temporary)/'silence.wav'
            with wave.open(str(audio),'wb') as writer:
                writer.setparams((1,2,24000,0,'NONE','not compressed'));writer.writeframes(bytes(48000))
            features,fingerprint=self.features(audio)
            if len(features)<4:raise RuntimeError('Insufficient silence features for warmup')
            sizes=[]
            for size in [1,2,3,4]:
                indices=[index%self.synth.total_frames for index in range(size)]
                images,metadata=self.synth._load_batch_frames(indices)
                frames=self.synth._process_batch(images,metadata,features[:size])
                if len(frames)!=size:raise RuntimeError('Warmup dropped frames')
                sizes.append(size)
        after=(self.synth.current_frame_position,self.synth.is_forward,self.frame_offset,self.sample_offset)
        if after!=position:raise RuntimeError('Warmup changed presentation position')
        self.silence_features=tuple(feature.copy() for feature in features)
        for feature in self.silence_features:feature.setflags(write=False)
        self.prepare_result={'model_ready':True,'warmed_batch_sizes':sizes,'wenet_load_count':self.wenet_loads,
            'wenet_identity':id(self.synth.wenet_model),'unet_session_identity':id(self.sessions[0]),
            'silence_features_sha256':fingerprint,'seconds':time.perf_counter()-started,
            'frame_offset':self.frame_offset,'sample_offset':self.sample_offset,'output_generated':False}
        self.prepared=True;return {**self.prepare_result,'reused':False}

    def idle(self,session,task_id,timing,frame_channel):
        if not self.prepared or not self.silence_features:raise ValueError('Prepare silence features before idle output')
        span=parse_span(timing)
        if session!=self.session or span.session_id!=session or span.sample_start!=self.sample_offset or span.frame_start!=self.frame_offset:
            raise ValueError('Idle session/timing mismatch')
        if not 1<=span.frames<=8 or span.samples!=span.frames*960 or self.timed_mode is False:raise ValueError('Idle chunk must be one to eight timed frames')
        self.timed_mode=True;sequence=self.synth._generate_frame_sequence(span.frames);offset=self.frame_offset
        stats=self.synth.engine.perf_stats
        for key in ['inference_ms','prepare_ms','paste_ms']:stats[key].clear()
        stats['frames']=stats['batches']=0
        written=0
        try:
            for start in range(0,len(sequence),self.synth.batch_size):
                indices=sequence[start:start+self.synth.batch_size];images,metadata=self.synth._load_batch_frames(indices)
                features=[self.silence_features[(start+index)%len(self.silence_features)] for index in range(len(indices))]
                frames=self.synth._process_batch(images,metadata,features)
                if len(frames)!=len(indices):raise RuntimeError('Idle frame missing')
                for frame in frames:frame_channel.send(session,task_id,offset+written,frame);written+=1
        except BaseException:frame_channel.close();raise
        self.frame_offset+=written;self.sample_offset+=span.samples
        return {'session_id':session,'task_id':task_id,'timing':timing,'frames':written,'raw_frames_sent':written,
            'output':None,'output_mode':'raw-frame-stream','audio_data_sent':False,'idle':True,
            'frame_offset':offset,'next_frame_offset':self.frame_offset,'source_first':sequence[0],'source_last':sequence[-1]}

    def render(self,session,task_id,audio,output,pcm_sha256,progress=None,timing=None,frame_channel=None):
        if session!=self.session:raise ValueError('Stale avatar session')
        if frame_channel is not None and not self.prepared:raise ValueError('Prepare avatar models before streaming frames')
        audio=Path(audio).resolve(strict=True);output=Path(output).resolve() if frame_channel is None else None
        value=hashlib.sha256()
        with wave.open(str(audio),'rb') as source:
            if (source.getframerate(),source.getnchannels(),source.getsampwidth())!=(24000,1,2):raise ValueError('Expected 24kHz mono PCM16')
            samples=source.getnframes()
            for block in iter(lambda:source.readframes(24000),b''):value.update(block)
        if value.hexdigest()!=pcm_sha256:raise ValueError('Utterance PCM fingerprint changed')
        mode=timing is not None
        if self.timed_mode is not None and mode!=self.timed_mode:raise ValueError('Cannot mix legacy and timed rendering in one session')
        span=parse_span(timing) if mode else None
        if span and (span.session_id!=session or span.samples!=samples or span.sample_start!=self.sample_offset or span.frame_start!=self.frame_offset):raise ValueError('Audio clock/input boundary mismatch')
        if span and not span.frames and frame_channel is None:raise ValueError('Audio-only span requires the continuous output sink, not a standalone MP4')
        self.timed_mode=mode
        if span and not span.frames:
            self.sample_offset+=samples
            return {'session_id':session,'task_id':task_id,'pcm_sha256':pcm_sha256,'audio_sha256':digest(audio),
                'output':None,'output_sha256':None,'output_mode':'raw-frame-stream','frames':0,'raw_frames_sent':0,
                'audio_data_sent':False,'audio_only':True,'frame_offset':self.frame_offset,'next_frame_offset':self.frame_offset,'timing':timing}
        started=time.perf_counter();features,feature_sha=self.features(audio)
        native_count=len(features);indices=feature_indices(native_count,span.frames if span else native_count)
        features=[features[index] for index in indices]
        stats=self.synth.engine.perf_stats
        for key in ['inference_ms','prepare_ms','paste_ms']:stats[key].clear()
        stats['frames']=stats['batches']=0
        feature_seconds=time.perf_counter()-started
        sequence=self.synth._generate_frame_sequence(len(features));first,_=self.synth._load_single_frame(sequence[0])
        from scripts.raw_video_writer import RawVideoWriter
        writer=RawVideoWriter(self.internal/'env/ffmpeg/bin/ffmpeg.exe',output,audio,first.shape[1],first.shape[0]) if frame_channel is None else None
        offset=self.frame_offset;written=0;peak=0
        try:
            for start in range(0,len(features),self.synth.batch_size):
                indices=sequence[start:start+self.synth.batch_size]
                images,metadata=self.synth._load_batch_frames(indices)
                frames=self.synth._process_batch(images,metadata,features[start:start+len(indices)])
                if len(frames)!=len(indices):raise RuntimeError('Synthesizer dropped frames')
                peak=max(peak,len(frames))
                for frame in frames:
                    if writer:writer.write(frame)
                    else:frame_channel.send(session,task_id,offset+written,frame)
                    written+=1
                    if written==1 and progress:progress({'event':'first_frame_written' if writer else 'first_frame_sent','session_id':session,'task_id':task_id,'frame_index':offset,'source_index':sequence[0]})
            if writer:writer.release()
        except BaseException:
            if writer:writer.abort()
            else:frame_channel.close()
            raise
        self.frame_offset+=written
        self.sample_offset+=samples
        if writer:
            try:media=verify_media(audio,output,self.internal/'env/ffmpeg/bin/ffmpeg.exe')
            except BaseException:
                output.unlink(missing_ok=True);raise
        else:media={'frames':written,'width':first.shape[1],'height':first.shape[0],'raw_frames_sent':written,'audio_data_sent':False}
        return {**media,'session_id':session,'task_id':task_id,'output':str(output) if writer else None,
            'pcm_sha256':pcm_sha256,'audio_sha256':digest(audio),'output_sha256':digest(output) if writer else None,
            'output_mode':'mp4' if writer else 'raw-frame-stream',
            'timing':timing,'native_feature_frames':native_count,'render_feature_frames':len(features),
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
