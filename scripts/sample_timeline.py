"""Integer audio-sample master timeline; no per-utterance rounding drift."""
from dataclasses import dataclass
import threading
import time
from scripts.live_speech_queue import StaleSession


@dataclass(frozen=True)
class SampleSpan:
    session_id:str
    sample_start:int
    sample_end:int
    frame_start:int
    frame_end:int
    sample_rate:int=24000
    fps:int=25

    @property
    def samples(self):return self.sample_end-self.sample_start

    @property
    def frames(self):return self.frame_end-self.frame_start


class SampleTimeline:
    def __init__(self,session_id,sample_rate=24000,fps=25):
        if not isinstance(session_id,str) or not session_id:raise ValueError('Session ID required')
        if any(type(v) is not int or v<=0 for v in [sample_rate,fps]):raise ValueError('Positive integer sample rate/fps required')
        self.session_id=session_id;self.sample_rate=sample_rate;self.fps=fps
        self.samples=0;self.frames=0;self.closed=False;self.lock=threading.Lock()

    def reserve(self,session_id,samples):
        if type(samples) is not int or samples<=0:raise ValueError('Positive integer sample count required')
        with self.lock:
            if self.closed or session_id!=self.session_id:raise StaleSession('Timeline session stopped or changed')
            end=self.samples+samples
            # Nearest global frame boundary, explicit half-up ties, all integer.
            frame_end=(2*end*self.fps+self.sample_rate)//(2*self.sample_rate)
            span=SampleSpan(session_id,self.samples,end,self.frames,frame_end,self.sample_rate,self.fps)
            self.samples=end;self.frames=frame_end;return span

    def stop(self):
        with self.lock:self.closed=True


def parse_span(value):
    if not isinstance(value,dict) or set(value)!=set(SampleSpan.__dataclass_fields__):raise ValueError('Complete timing span required')
    span=SampleSpan(**value)
    if not isinstance(span.session_id,str) or not span.session_id:raise ValueError('Timing session required')
    if any(type(getattr(span,key)) is not int for key in ['sample_start','sample_end','frame_start','frame_end','sample_rate','fps']):raise ValueError('Integer timing fields required')
    if span.sample_rate!=24000 or span.fps!=25 or span.sample_start<0 or span.samples<=0:raise ValueError('Unsupported live audio timing')
    expected=lambda samples:(2*samples*span.fps+span.sample_rate)//(2*span.sample_rate)
    if span.frame_start!=expected(span.sample_start) or span.frame_end!=expected(span.sample_end):raise ValueError('Non-canonical frame boundary')
    return span


def feature_indices(native_count,frame_count):
    """Keep whole-utterance endpoint context when the clock adds/removes one frame."""
    if type(native_count) is not int or type(frame_count) is not int or native_count<1 or frame_count<0 or abs(native_count-frame_count)>1:
        raise ValueError('Frame correction must be at most one frame')
    if not frame_count:return []
    if frame_count==1:return [0]
    return [(2*index*(native_count-1)+frame_count-1)//(2*(frame_count-1)) for index in range(frame_count)]


@dataclass(frozen=True)
class FrameDeadline:
    session_id:str
    frame_index:int
    pts_ns:int
    deadline_ns:int


class FramePacer:
    """Interruptible deadlines. Caller records actual sink completion separately."""
    def __init__(self,session_id,origin_ns,fps=25,now=None):
        if not isinstance(session_id,str) or not session_id or type(origin_ns) is not int or type(fps) is not int or fps<=0:
            raise ValueError('Explicit session, integer origin and fps required')
        self.session_id=session_id;self.origin_ns=origin_ns;self.fps=fps;self.now=now or time.perf_counter_ns
        self.stop_event=threading.Event();self.lock=threading.Lock();self.next_frame=0;self.pending=None

    def wait_for(self,session_id,frame_index):
        with self.lock:
            self._check(session_id)
            if type(frame_index) is not int or frame_index!=self.next_frame or self.pending is not None:
                raise ValueError('Missing, repeated or unacknowledged frame')
            pts=frame_index*1000000000//self.fps;deadline=self.origin_ns+pts
            while True:
                self._check(session_id);remaining=deadline-self.now()
                if remaining<=0:break
                self.stop_event.wait(remaining/1000000000)
            self._check(session_id)
            self.pending=FrameDeadline(session_id,frame_index,pts,deadline);return self.pending

    def presented(self,deadline):
        with self.lock:
            self._check(deadline.session_id)
            if deadline!=self.pending:raise ValueError('Unknown presentation acknowledgement')
            actual=self.now();self.pending=None;self.next_frame+=1
            return {'frame_index':deadline.frame_index,'pts_ns':deadline.pts_ns,'deadline_ns':deadline.deadline_ns,
                'presented_ns':actual,'late_ns':max(0,actual-deadline.deadline_ns)}

    def _check(self,session_id):
        if self.stop_event.is_set() or session_id!=self.session_id:raise StaleSession('Presentation session stopped or changed')

    def stop(self):self.stop_event.set()
