"""Smooth callback arrival bursts while following the audio sample clock phase."""
from collections import deque
from dataclasses import dataclass
import statistics


@dataclass(frozen=True)
class VideoDeadline:
    due_ns:int
    phase_error_ns:int
    tracked:bool


class AudioVideoClock:
    def __init__(self,delay_ns):
        if type(delay_ns) is not int or not 0<=delay_ns<=120000000:raise ValueError('Unsupported video delay')
        self.delay_ns=delay_ns;self.phases=deque(maxlen=64);self.next_frame=0;self.phase=None

    def deadline(self,index,callback_ns):
        if type(index) is not int or index!=self.next_frame or type(callback_ns) is not int:raise ValueError('Ordered integer frame/clock required')
        observed=callback_ns-index*40000000
        # WASAPI can fill its initial buffers in a burst. Keep these explicit
        # startup frames; acquire phase after the existing eight-frame preroll.
        if index>=2:self.phases.append(observed)
        if index<8:
            result=VideoDeadline(callback_ns+self.delay_ns,0,False)
        else:
            target=int(statistics.median(self.phases))
            if self.phase is None:self.phase=target
            error=target-self.phase
            if abs(error)>80000000:raise RuntimeError('Audio/video clock phase lost tracking')
            self.phase+=max(-100000,min(100000,error))
            result=VideoDeadline(self.phase+index*40000000+self.delay_ns,target-self.phase,True)
        self.next_frame+=1
        return result
