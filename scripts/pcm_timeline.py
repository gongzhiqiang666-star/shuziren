"""Bounded file/silence ledger, read on the common 24kHz sample clock."""
from collections import deque
import hashlib
import threading
import time
import wave
from scripts.sample_timeline import parse_span


class PCMTimeline:
    def __init__(self,session_id,on_complete=None):
        self.session_id=session_id;self.entries=deque();self.condition=threading.Condition()
        self.written=0;self.read_samples=0;self.closed=False;self.on_complete=on_complete

    def append(self,timing,source_id,path=None,expected_pcm_sha256=None):
        span=parse_span(timing);reader=None
        try:
            if path is not None:
                reader=wave.open(str(path),'rb')
                if (reader.getnchannels(),reader.getsampwidth(),reader.getframerate(),reader.getnframes())!=(1,2,24000,span.samples):
                    raise ValueError('PCM source disagrees with its sample range')
                if expected_pcm_sha256:
                    fingerprint=hashlib.sha256()
                    for block in iter(lambda:reader.readframes(24000),b''):fingerprint.update(block)
                    if fingerprint.hexdigest()!=expected_pcm_sha256:raise ValueError('PCM snapshot fingerprint mismatch')
                    reader.rewind()
            with self.condition:
                if self.closed or span.session_id!=self.session_id:raise RuntimeError('PCM session stopped or changed')
                if span.sample_start!=self.written or len(self.entries)>=4:raise ValueError('PCM gap, reorder or source budget exceeded')
                self.entries.append({'id':source_id,'remaining':span.samples,'samples':span.samples,'reader':reader,'hash':hashlib.sha256(),'expected':expected_pcm_sha256})
                self.written=span.sample_end;self.condition.notify_all()
        except BaseException:
            if reader:reader.close()
            raise

    def read(self,samples,timeout=2):
        if type(samples) is not int or samples<=0:raise ValueError('Positive integer PCM read required')
        deadline=time.monotonic()+timeout;blocks=[]
        with self.condition:
            while sum(entry['remaining'] for entry in self.entries)<samples:
                if self.closed:raise RuntimeError('PCM output stopped')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('PCM source underrun')
                self.condition.wait(remaining)
            if self.closed:raise RuntimeError('PCM output stopped')
            needed=samples
            while needed:
                entry=self.entries[0];count=min(needed,entry['remaining'])
                block=entry['reader'].readframes(count) if entry['reader'] else bytes(count*2)
                if len(block)!=count*2:raise ValueError('PCM snapshot truncated during playback')
                blocks.append(block);entry['hash'].update(block);entry['remaining']-=count;needed-=count;self.read_samples+=count
                if not entry['remaining']:
                    if entry['reader']:entry['reader'].close()
                    self.entries.popleft();actual=entry['hash'].hexdigest()
                    if entry['expected'] and actual!=entry['expected']:raise ValueError('PCM playback source fingerprint changed')
                    if self.on_complete:self.on_complete({'source_id':entry['id'],'samples':entry['samples'],'pcm_sha256':actual})
            self.condition.notify_all();return b''.join(blocks)

    def close(self):
        with self.condition:
            self.closed=True
            for entry in self.entries:
                if entry['reader']:entry['reader'].close()
            self.entries.clear();self.condition.notify_all()
