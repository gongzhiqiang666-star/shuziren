"""Bounded complete-utterance handoff; output must also check session validity."""
from collections import deque
from dataclasses import dataclass
import hashlib
import io
import math
import threading
import time
import uuid
import wave


class StaleSession(ValueError):pass


@dataclass(frozen=True)
class SpeechSession:
    id:str
    binding:tuple


@dataclass(frozen=True)
class SpeechPacket:
    session:SpeechSession
    sequence:int
    pcm:bytes
    samples:int
    source_sha256:str


class LiveSpeechQueue:
    def __init__(self,max_items=4,max_seconds=60,max_utterance_seconds=30):
        if not isinstance(max_items,int) or isinstance(max_items,bool) or max_items<1 or not all(math.isfinite(value) and value>0 for value in [max_seconds,max_utterance_seconds]):
            raise ValueError('Queue limits must be positive')
        self.max_items=max_items;self.max_samples=int(max_seconds*24000)
        self.max_utterance_samples=min(self.max_samples,int(max_utterance_seconds*24000))
        self.condition=threading.Condition();self.items=deque();self.samples=0
        self.session=None;self.sequence=0

    def start(self,binding):
        required={'product_id','product_version','voice_id','avatar_id'}
        if set(binding)!=required or any(not isinstance(binding[key],str) or not binding[key].strip() for key in required-{'product_version'}) or not isinstance(binding['product_version'],int) or isinstance(binding['product_version'],bool) or binding['product_version']<1:
            raise ValueError('Explicit product/version/voice/avatar binding required')
        session=SpeechSession(str(uuid.uuid4()),tuple(sorted(binding.items())))
        with self.condition:
            self.items.clear();self.samples=0;self.sequence=0;self.session=session
            self.condition.notify_all()
        return session

    def stop(self):
        with self.condition:
            self.session=None;self.items.clear();self.samples=0;self.condition.notify_all()

    def is_current(self,session):
        with self.condition:return self.session is not None and self.session==session

    def _check(self,session):
        if self.session is None or session!=self.session:raise StaleSession('Speech session stopped or inputs changed')

    def put(self,session,audio,timeout=0):
        if not isinstance(audio,(bytes,bytearray,memoryview)):raise ValueError('WAV bytes required')
        if memoryview(audio).nbytes>self.max_utterance_samples*2+65536:raise ValueError('Utterance exceeds byte budget')
        audio=bytes(audio)
        with wave.open(io.BytesIO(audio),'rb') as source:
            if (source.getnchannels(),source.getsampwidth(),source.getframerate(),source.getcomptype())!=(1,2,24000,'NONE'):
                raise ValueError('Expected 24kHz mono PCM16 WAV')
            samples=source.getnframes()
            if not 0<samples<=self.max_utterance_samples:raise ValueError('Utterance exceeds duration budget')
            pcm=source.readframes(samples)
            if len(pcm)!=samples*2:raise ValueError('Truncated WAV')
        deadline=time.monotonic()+max(0,timeout)
        with self.condition:
            while True:
                self._check(session)
                if len(self.items)<self.max_items and self.samples+samples<=self.max_samples:break
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Speech queue is full; producer must apply backpressure')
                self.condition.wait(remaining)
            packet=SpeechPacket(session,self.sequence,pcm,samples,hashlib.sha256(audio).hexdigest())
            self.sequence+=1;self.items.append(packet);self.samples+=samples;self.condition.notify_all()
            return packet

    def take(self,session,timeout=0):
        deadline=time.monotonic()+max(0,timeout)
        with self.condition:
            while True:
                self._check(session)
                if self.items:
                    packet=self.items.popleft();self.samples-=packet.samples;self.condition.notify_all();return packet
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('No new speech available')
                self.condition.wait(remaining)

    def state(self):
        with self.condition:
            return {'session_id':self.session.id if self.session else None,'queued_items':len(self.items),
                'queued_samples':self.samples,'queued_seconds':self.samples/24000,'next_sequence':self.sequence}
