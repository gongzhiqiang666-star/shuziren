"""Diagnostic frame counters and actual camera/cable voice alignment."""
import subprocess
import re
import time
import wave
from bisect import bisect_right
from collections import Counter
from decimal import Decimal
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
        self.path=directory/'receiver.mkv';self.log_path=directory/'receiver.log'
        self.log=self.log_path.open('wb');self.process=None
        self.launched_unix_ns=time.time_ns()
        try:
            self.process=subprocess.Popen([str(ffmpeg),'-nostdin','-y','-hide_banner','-loglevel','info','-nostats',
                '-use_wallclock_as_timestamps','1','-f','dshow','-rtbufsize','16M','-audio_buffer_size','20',
                '-video_size','720x1280','-framerate','25','-i','video=C920:audio=CABLE Output (VB-Audio Virtual Cable)',
                '-t',str(seconds),'-fps_mode','passthrough','-c:v','ffv1','-c:a','pcm_s16le','-ar','48000','-ac','1',str(self.path)],
                stdout=subprocess.DEVNULL,stderr=self.log)
        except BaseException:self.log.close();raise

    def wait(self):
        self.process.wait(timeout=10)
        if self.process.returncode:raise RuntimeError('Device capture failed; see receiver.log')

    def timestamp_origin(self):
        return receiver_origin(self.log_path,self.launched_unix_ns,time.time_ns())

    def close(self):
        try:
            if self.process and self.process.poll() is None:self.process.kill();self.process.wait(timeout=5)
        finally:self.log.close()


def receiver_origin(log,launched_ns,finished_ns):
    with log.open(encoding='utf-8',errors='replace') as lines:
        for line in lines:
            match=re.search(r'Duration:\s*N/A,\s*start:\s*(\d+\.\d+)',line)
            if match:
                origin=int(Decimal(match[1])*1_000_000_000)
                return origin if launched_ns<=origin<=finished_ns else None
    return None


def audit_device_deadlines(trace):
    rows=[row for row in trace if row['event']=='video_sent' and row['frame_index']>=8]
    if not rows:
        return {'count':0,'passed':False}
    late=np.asarray([max(0,row['camera_sent_ns']-row['due_ns'])/1_000_000 for row in rows])
    p95,p99=(float(value) for value in np.percentile(late,[95,99]))
    maximum=float(late.max())
    above=float(np.mean(late>5))
    report={'count':len(rows),'p95_ms':p95,'p99_ms':p99,'max_ms':maximum,'above_5ms_ratio':above,
            'passed':p95<=5 and p99<=20 and maximum<=40 and above<=.01}
    if all('video_dequeued_ns' in row and 'camera_send_started_ns' in row for row in rows):
        dequeue=[];wake=[];send=[]
        for row in rows:
            due=row['due_ns'];taken=row['video_dequeued_ns'];started=row['camera_send_started_ns']
            dequeue.append(max(0,taken-due)/1_000_000)
            wake.append(max(0,started-max(due,taken))/1_000_000)
            send.append((row['camera_sent_ns']-started)/1_000_000)
        report['stages']={name:{'p95_ms':float(np.percentile(values,95)),'max_ms':max(values)}
                          for name,values in (('dequeue_late',dequeue),('wake_late',wake),('camera_send',send))}
        late_rows=[index for index,value in enumerate(late) if value>5]
        report['over_5ms_attributed']={
            'before_dequeue':sum(dequeue[index]>5 for index in late_rows),
            'before_send':sum(dequeue[index]<=5<dequeue[index]+wake[index] for index in late_rows),
            'during_send':sum(dequeue[index]+wake[index]<=5 for index in late_rows)}
    return report


def audit_received_voice(path,completed,expected,origin_ns=None):
    video=[];blocks=[];block_times=[];block_offsets=[];sample_count=0
    with av.open(str(path)) as container:
        for packet in container.demux():
            for frame in packet.decode():
                if isinstance(frame,av.VideoFrame):video.append((read_counter(frame.to_ndarray(format='bgr24')),float(frame.time)))
                else:
                    if frame.sample_rate!=48000 or frame.layout.nb_channels!=1:raise ValueError('Expected 48k mono receiver audio')
                    block=frame.to_ndarray().reshape(-1)
                    if block_times and frame.time < block_times[-1]:raise ValueError('Receiver audio timestamp reordered')
                    block_times.append(float(frame.time));block_offsets.append(sample_count)
                    sample_count+=len(block);blocks.append(block)
    if not video or not blocks:raise ValueError('Receiver missed video or audio')
    received=np.concatenate(blocks);blocks.clear();source_start=0;voices=[]
    speech_frames=set()
    for event in completed:
        if event['source_id'] in expected:
            source=expected[event['source_id']]
            with wave.open(source['path'],'rb') as sound:
                if (sound.getframerate(),sound.getnchannels(),sound.getsampwidth())!=(24000,1,2):raise ValueError('Unexpected reference PCM format')
                reference=signal.resample_poly(np.frombuffer(sound.readframes(sound.getnframes()),dtype='<i2').astype(float),2,1)
            target=source_start//960
            end=(source_start+event['samples']+959)//960
            speech_frames.update(range(target,end))
            frame_index,video_time=min(video,key=lambda item:abs(item[0]-target))
            uncertainty=abs(frame_index-target)*40
            expected_video_time=video_time+(source_start-frame_index*960)/24000
            # Search around the source-aligned video, wider than the 80 ms acceptance window.
            # A bounded window avoids correlating against an entire long recording or a later repeat.
            window_start=expected_video_time-.5
            window_end=expected_video_time+.5+len(reference)/48000
            first=max(0,bisect_right(block_times,window_start)-1)
            after=bisect_right(block_times,window_end)
            start=block_offsets[first]
            end=block_offsets[after] if after<len(block_offsets) else sample_count
            window=received[start:end].astype(float)
            coefficient=0.
            audio_time=delta_ms=signal_time=None
            if len(window)>=len(reference):
                correlation=signal.correlate(window,reference,mode='valid',method='fft')
                relative=int(np.argmax(correlation))
                aligned=window[relative:relative+len(reference)]
                denominator=np.linalg.norm(aligned)*np.linalg.norm(reference)
                coefficient=float(np.dot(aligned,reference)/denominator) if denominator else 0.
                offset=start+relative
                block_index=bisect_right(block_offsets,offset)-1
                audio_time=block_times[block_index]+(offset-block_offsets[block_index])/48000
                delta_ms=(audio_time-expected_video_time)*1000
                signal_indices=np.flatnonzero(np.abs(aligned)>=256)
                if signal_indices.size:
                    signal_offset=offset+int(signal_indices[0])
                    signal_block=bisect_right(block_offsets,signal_offset)-1
                    signal_time=block_times[signal_block]+(signal_offset-block_offsets[signal_block])/48000
            voices.append({'task_id':event['source_id'],'source_start_sample':source_start,'samples':event['samples'],
                'correlation':coefficient,'audio_receive_start_seconds':audio_time,
                'reference_video_frame':frame_index,'av_offset_ms':delta_ms,'video_uncertainty_ms':uncertainty,
                'passed':delta_ms is not None and coefficient>=.95 and abs(delta_ms)+uncertainty<=80})
            ready_ns=source.get('wav_ready_unix_ns')
            if source.get('case_id') is not None:
                voices[-1]['case_id']=source['case_id']
            if origin_ns is not None and ready_ns is not None and voices[-1]['passed']:
                origin_from_ready_ms=(origin_ns-ready_ns)/1_000_000
                voices[-1]['wav_ready_to_received_signal_ms']=(
                    origin_from_ready_ms+signal_time*1000 if signal_time is not None else None)
                voices[-1]['wav_ready_to_received_frame_ms']=(
                    origin_from_ready_ms+video_time*1000 if frame_index==target else None)
        source_start+=event['samples']
    steps=[b[0]-a[0] for a,b in zip(video,video[1:])]
    received_speech=[index for index,_ in video if index in speech_frames]
    speech_counts=Counter(received_speech)
    speech_missing=len(speech_frames-speech_counts.keys())
    speech_repeated=sum(count-1 for count in speech_counts.values())
    speech_reordered=sum(next_index<index for index,next_index in zip(received_speech,received_speech[1:]))
    drift=None
    if len(voices)>1 and voices[0]['passed'] and voices[-1]['passed']:
        drift=abs(voices[-1]['av_offset_ms']-voices[0]['av_offset_ms'])
    latency={}
    for kind in ('signal','frame'):
        field=f'wav_ready_to_received_{kind}_ms'
        measurements=[voice[field] for voice in voices if voice.get(field) is not None and voice[field]>=0]
        latency[kind]={'count':len(measurements),'p95_ms':float(np.percentile(measurements,95)) if measurements else None}
    return {'voices':voices,'received_video_frames':len(video),'received_audio_samples':len(received),
        'received_video_span_seconds':video[-1][1]-video[0][1],
        'missing_frames':sum(max(0,step-1) for step in steps),'repeated_frames':sum(step==0 for step in steps),
        'reordered_frames':sum(step<0 for step in steps),'frame_continuity_passed':bool(steps) and all(step==1 for step in steps),
        'voice_sync_passed':len(voices)==len(expected) and bool(voices) and all(voice['passed'] for voice in voices),
        'speech_video_frames_expected':len(speech_frames),'speech_missing_frames':speech_missing,
        'speech_repeated_frames':speech_repeated,'speech_reordered_frames':speech_reordered,
        'speech_frame_continuity_passed':bool(speech_frames) and not (speech_missing or speech_repeated or speech_reordered),
        'speech_av_drift_ms':drift,
        'speech_measurement_span_seconds':(voices[-1]['source_start_sample']-voices[0]['source_start_sample'])/24000 if drift is not None else None,
        'receiver_timestamp_origin_unix_ns':origin_ns,
        'receiver_latency_calibration':latency,
        'received_signal_threshold_pcm16':256,
        'timing_acceptance':False,'markers_are_diagnostic_overlay':True}
