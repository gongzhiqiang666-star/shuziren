"""Bounded PCM/silence ledger, read on the common 24kHz sample clock."""
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
        self.read_stage=('idle',time.perf_counter_ns())

    def append(self,timing,source_id,path=None,expected_pcm_sha256=None):
        span = parse_span(timing)
        pcm = None
        if path is not None:
            with wave.open(str(path), 'rb') as reader:
                if (reader.getnchannels(), reader.getsampwidth(), reader.getframerate(),
                        reader.getnframes()) != (1, 2, 24000, span.samples):
                    raise ValueError('PCM source disagrees with its sample range')
                pcm = reader.readframes(span.samples)
            if len(pcm) != span.samples * 2:
                raise ValueError('PCM snapshot truncated before playback')
            if expected_pcm_sha256 and hashlib.sha256(pcm).hexdigest() != expected_pcm_sha256:
                raise ValueError('PCM snapshot fingerprint mismatch')
        with self.condition:
            if self.closed or span.session_id != self.session_id:
                raise RuntimeError('PCM session stopped or changed')
            if span.sample_start != self.written or len(self.entries) >= 4:
                raise ValueError('PCM gap, reorder or source budget exceeded')
            self.entries.append({'id': source_id, 'remaining': span.samples,
                                 'samples': span.samples, 'pcm': pcm, 'hash': hashlib.sha256()})
            self.written = span.sample_end
            self.condition.notify_all()

    def read(self,samples,timeout=2):
        if type(samples) is not int or samples<=0:raise ValueError('Positive integer PCM read required')
        deadline=time.monotonic()+timeout;blocks=[]
        self.read_stage=('acquire',time.perf_counter_ns())
        with self.condition:
            while sum(entry['remaining'] for entry in self.entries)<samples:
                if self.closed:raise RuntimeError('PCM output stopped')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('PCM source underrun')
                self.read_stage=('wait_source',time.perf_counter_ns())
                self.condition.wait(remaining)
            if self.closed:raise RuntimeError('PCM output stopped')
            needed=samples
            while needed:
                entry=self.entries[0];count=min(needed,entry['remaining'])
                pcm = entry['pcm']
                self.read_stage = ('read_memory' if pcm is not None else 'read_silence',
                                   time.perf_counter_ns())
                offset = (entry['samples'] - entry['remaining']) * 2
                block = pcm[offset:offset + count * 2] if pcm is not None else bytes(count * 2)
                blocks.append(block);entry['hash'].update(block);entry['remaining']-=count;needed-=count;self.read_samples+=count
                if not entry['remaining']:
                    self.entries.popleft();actual=entry['hash'].hexdigest()
                    if self.on_complete:
                        self.read_stage=('source_complete',time.perf_counter_ns())
                        self.on_complete({'source_id':entry['id'],'samples':entry['samples'],'pcm_sha256':actual})
            self.read_stage=('returned',time.perf_counter_ns())
            self.condition.notify_all();return b''.join(blocks)

    def close(self):
        with self.condition:
            self.closed=True
            self.entries.clear();self.condition.notify_all()
