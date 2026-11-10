"""Bounded combined device sink, paced by the actual output audio callback."""
import hashlib
import queue
import threading
import time
import numpy as np
from scripts.live_device_output import VirtualCameraOutput
from scripts.audio_video_clock import AudioVideoClock,VideoDeadline


class AVDeviceSink:
    clock_mode='audio'

    def __init__(self,width,height,audio_device,on_present=None,video_delay_ms=0,smooth_clock=False,buffer_frames=2):
        import sounddevice as sd
        if type(audio_device) is not int:raise ValueError('Explicit output device required')
        if type(smooth_clock) is not bool:raise ValueError('Explicit clock mode required')
        if type(buffer_frames) is not int or buffer_frames not in (2,4):
            raise ValueError('Device buffer must hold two or four frames')
        self.smooth_clock=smooth_clock
        if type(video_delay_ms) not in (int,float) or not 0<=video_delay_ms<=120:raise ValueError('Video compensation must be 0 to 120ms')
        self.sd=sd;self.width=width;self.height=height;self.on_present=on_present
        self.owner_thread=threading.get_ident()
        self.video_delay_ns=int(video_delay_ms*1000000);self.video_queue=queue.Queue(maxsize=4)
        self.video_clock=AudioVideoClock(self.video_delay_ns)
        self.stop_event=threading.Event();self.video_finished=threading.Event();self.video_thread=None
        self.buffer_frames=buffer_frames
        self.queue=queue.Queue(maxsize=buffer_frames);self.closed=False;self.started=False;self.draining=False
        self.error=None;self.frames=0;self.samples=0;self.presented=0;self.peak=0;self.underflows=0
        self.underrun=None
        self.finished=threading.Event();self.pcm_hash=hashlib.sha256();self.camera=None;self.stream=None
        info=sd.query_devices(audio_device)
        settings=sd.WasapiSettings(auto_convert=True) if sd.query_hostapis(info['hostapi'])['name']=='Windows WASAPI' else None
        sd.check_output_settings(device=audio_device,channels=1,dtype='int16',samplerate=24000,extra_settings=settings)
        try:
            self.camera=VirtualCameraOutput(width,height)
            self.stream=sd.RawOutputStream(device=audio_device,samplerate=24000,channels=1,dtype='int16',
                blocksize=960,latency='low',extra_settings=settings,callback=self._callback,finished_callback=self.finished.set)
            self.video_thread=threading.Thread(target=self._video,name='device-video-clock');self.video_thread.start()
        except BaseException:self.abort();raise

    def _callback(self,outdata,frames,timing,status):
        try:
            if status:raise RuntimeError('Audio device status: '+str(status))
            if frames!=960:raise RuntimeError('Unexpected audio callback block size')
            try:index,image,pcm,submitted=self.queue.get_nowait()
            except queue.Empty:
                if self.draining:
                    outdata[:]=bytes(len(outdata));raise self.sd.CallbackStop()
                self.underflows+=1
                self.underrun={'callback_ns':time.perf_counter_ns(), 'next_frame':self.presented,
                               'submitted_frames':self.frames}
                raise RuntimeError('Combined device queue underrun')
            if index!=self.presented:raise RuntimeError('Combined device frame reordered')
            callback_ns=time.perf_counter_ns();outdata[:]=pcm
            deadline=(self.video_clock.deadline(index,callback_ns) if self.smooth_clock
                else VideoDeadline(callback_ns+self.video_delay_ns,0,False))
            self.video_queue.put_nowait((index,image,deadline.due_ns));self.presented+=1
            if self.on_present:self.on_present({'event':'audio_callback','frame_index':index,'pts_ns':index*40000000,
                'callback_ns':callback_ns,'submitted_ns':submitted,
                'video_due_ns':deadline.due_ns,'video_clock_tracked':deadline.tracked,'video_clock_phase_error_ns':deadline.phase_error_ns,
                'audio_dac_time':timing.outputBufferDacTime,'audio_current_time':timing.currentTime})
        except self.sd.CallbackStop:raise
        except BaseException as error:
            self.error=str(error);outdata[:]=bytes(len(outdata));raise self.sd.CallbackAbort()

    def _video(self):
        try:
            while not self.stop_event.is_set():
                try:index,image,due=self.video_queue.get(timeout=.02)
                except queue.Empty:
                    if self.draining and self.finished.is_set() and self.camera.frames==self.frames:return
                    continue
                if self.stop_event.wait(max(0,(due-time.perf_counter_ns())/1e9)):return
                self.camera.send(index,image)
                if self.on_present:self.on_present({'event':'video_sent','frame_index':index,
                    'due_ns':due,'camera_sent_ns':time.perf_counter_ns()})
        except BaseException as error:self.error=str(error)
        finally:self.video_finished.set()

    def submit(self,index,image,pcm):
        if self.closed or self.error:raise RuntimeError(self.error or 'Combined output stopped')
        if self.draining:raise RuntimeError('Combined output input sealed')
        if type(index) is not int or index!=self.frames or image.shape!=(self.height,self.width,3) or image.dtype!=np.uint8 or not isinstance(pcm,bytes) or len(pcm)!=1920:
            raise ValueError('Next BGR frame and 960 PCM16 samples required')
        if not self.started and self.frames==self.buffer_frames-1 and threading.get_ident()!=self.owner_thread:
            raise RuntimeError('WASAPI stream must start on its creating thread')
        packet=(index,image.copy(),pcm,time.perf_counter_ns());deadline=time.monotonic()+2
        while True:
            if self.closed or self.error:raise RuntimeError(self.error or 'Combined output stopped')
            try:self.queue.put(packet,timeout=.02);break
            except queue.Full:
                if time.monotonic()>=deadline:raise TimeoutError('Audio device stopped consuming frames')
        self.frames+=1;self.samples+=960;self.pcm_hash.update(pcm);self.peak=max(self.peak,self.queue.qsize())
        if not self.started and self.frames==self.buffer_frames:self.stream.start();self.started=True
        return {'queued_frames':self.queue.qsize()}

    def finish_input(self):
        """Seal input before potentially slow model/worker cleanup."""
        self.draining=True

    def close(self):
        if self.closed:return
        self.draining=True
        try:
            if not self.started:
                if self.frames:raise RuntimeError(f'At least {self.buffer_frames} frames required to start device output')
                self.finished.set()
            if self.started and not self.finished.wait(2):raise TimeoutError('Audio output did not drain')
            if not self.video_finished.wait(2):raise TimeoutError('Video output did not drain')
            if self.error:raise RuntimeError(self.error)
            if self.presented!=self.frames:raise RuntimeError('Output ended with unpresented frames')
        finally:self.abort()

    def abort(self):
        if self.closed:return
        self.closed=True
        self.stop_event.set()
        try:
            if self.stream:
                try:self.stream.abort()
                finally:self.stream.close()
        finally:
            if self.video_thread:self.video_thread.join(2)
            if self.camera:self.camera.close()
            while True:
                try:self.queue.get_nowait()
                except queue.Empty:break
