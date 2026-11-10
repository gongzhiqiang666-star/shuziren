"""Diagnostic frame counters and actual camera/cable voice alignment."""
import subprocess
import wave
from collections import Counter
import av
import numpy as np
from scipy import signal
from scripts.live_av_device_sink import AVDeviceSink


def stamp_counter(image,index):
    if not 0<=index<65536:raise ValueError('Diagnostic counter exceeds 16 bits')
    result=image.copy()
    for row in range(2):
        for bit in range(8):
            result[80+row*100:160+row*100,40+bit*80:100+bit*80]=224 if index&(1<<(row*8+bit)) else 32
    return result


def read_counter(image):
    return sum(int(image[90+row*100:150+row*100,50+bit*80:90+bit*80].mean()>128)<<(row*8+bit)
        for row in range(2) for bit in range(8))


class CounterDeviceSink(AVDeviceSink):
    def submit(self,index,image,pcm):return super().submit(index,stamp_counter(image,index),pcm)


class DeviceCapture:
    def __init__(self,ffmpeg,directory,seconds):
        self.path=directory/'receiver.mkv';self.log=(directory/'receiver.log').open('wb');self.process=None
        try:
            self.process=subprocess.Popen([str(ffmpeg),'-nostdin','-y','-hide_banner','-loglevel','error',
                '-use_wallclock_as_timestamps','1','-f','dshow','-audio_buffer_size','20',
                '-video_size','720x1280','-framerate','25','-i','video=C920:audio=CABLE Output (VB-Audio Virtual Cable)',
                '-t',str(seconds),'-fps_mode','passthrough','-c:v','ffv1','-c:a','pcm_s16le','-ar','48000','-ac','1',str(self.path)],
                stdout=subprocess.DEVNULL,stderr=self.log)
        except BaseException:self.log.close();raise

    def wait(self):
        self.process.wait(timeout=10)
        if self.process.returncode:raise RuntimeError('Device capture failed; see receiver.log')

    def close(self):
        try:
            if self.process and self.process.poll() is None:self.process.kill();self.process.wait(timeout=5)
        finally:self.log.close()


def audit_received_voice(path,completed,expected):
    video=[];blocks=[];times=[]
    with av.open(str(path)) as container:
        for packet in container.demux():
            for frame in packet.decode():
                if isinstance(frame,av.VideoFrame):video.append((read_counter(frame.to_ndarray(format='bgr24')),float(frame.time)))
                else:
                    if frame.sample_rate!=48000 or frame.layout.nb_channels!=1:raise ValueError('Expected 48k mono receiver audio')
                    block=frame.to_ndarray().reshape(-1).astype(float);blocks.append(block)
                    times.append(float(frame.time)+np.arange(len(block))/48000)
    if not video or not blocks:raise ValueError('Receiver missed video or audio')
    received=np.concatenate(blocks);audio_times=np.concatenate(times);source_start=0;voices=[]
    speech_frames=set()
    for event in completed:
        if event['source_id'] in expected:
            source=expected[event['source_id']]
            with wave.open(source['path'],'rb') as sound:
                if (sound.getframerate(),sound.getnchannels(),sound.getsampwidth())!=(24000,1,2):raise ValueError('Unexpected reference PCM format')
                reference=signal.resample_poly(np.frombuffer(sound.readframes(sound.getnframes()),dtype='<i2').astype(float),2,1)
            if len(reference)>len(received):raise ValueError('Receiver audio shorter than utterance')
            correlation=signal.correlate(received,reference,mode='valid',method='fft');offset=int(np.argmax(correlation))
            aligned=received[offset:offset+len(reference)];denominator=np.linalg.norm(aligned)*np.linalg.norm(reference)
            coefficient=float(np.dot(aligned,reference)/denominator) if denominator else 0.
            target=source_start//960
            end=(source_start+event['samples']+959)//960
            speech_frames.update(range(target,end))
            frame_index,video_time=min(video,key=lambda item:abs(item[0]-target))
            uncertainty=abs(frame_index-target)*40
            expected_video_time=video_time+(source_start-frame_index*960)/24000
            delta_ms=(float(audio_times[offset])-expected_video_time)*1000
            voices.append({'task_id':event['source_id'],'source_start_sample':source_start,'samples':event['samples'],
                'correlation':coefficient,'audio_receive_start_seconds':float(audio_times[offset]),
                'reference_video_frame':frame_index,'av_offset_ms':delta_ms,'video_uncertainty_ms':uncertainty,
                'passed':coefficient>=.95 and abs(delta_ms)+uncertainty<=80})
        source_start+=event['samples']
    steps=[b[0]-a[0] for a,b in zip(video,video[1:])]
    received_speech=[index for index,_ in video if index in speech_frames]
    speech_counts=Counter(received_speech)
    speech_missing=len(speech_frames-speech_counts.keys())
    speech_repeated=sum(count-1 for count in speech_counts.values())
    speech_reordered=sum(next_index<index for index,next_index in zip(received_speech,received_speech[1:]))
    return {'voices':voices,'received_video_frames':len(video),'received_audio_samples':len(received),
        'missing_frames':sum(max(0,step-1) for step in steps),'repeated_frames':sum(step==0 for step in steps),
        'reordered_frames':sum(step<0 for step in steps),'frame_continuity_passed':bool(steps) and all(step==1 for step in steps),
        'voice_sync_passed':len(voices)==len(expected) and bool(voices) and all(voice['passed'] for voice in voices),
        'speech_video_frames_expected':len(speech_frames),'speech_missing_frames':speech_missing,
        'speech_repeated_frames':speech_repeated,'speech_reordered_frames':speech_reordered,
        'speech_frame_continuity_passed':bool(speech_frames) and not (speech_missing or speech_repeated or speech_reordered),
        'timing_acceptance':False,'markers_are_diagnostic_overlay':True}
