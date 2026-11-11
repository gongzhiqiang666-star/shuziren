"""Live idle/speech jobs, bounded raw frames and one PCM/video presentation clock."""
from dataclasses import asdict
from collections import deque
import logging
from pathlib import Path
import queue
import statistics
import sys
import threading
import time
from scripts.pcm_timeline import PCMTimeline
from scripts.sample_timeline import SampleTimeline,FramePacer
from scripts.speech_assembler import Utterance
from scripts.v122_acceleration import windows_timer_precision


class ContinuousSession:
    def __init__(self,session_id,client,receiver,sink,source_directory,on_source_complete=None,on_present=None,on_started=None,*,idle_frames=8):
        if type(idle_frames) is not int or idle_frames not in (4,8):
            raise ValueError('Idle spans must contain four or eight frames')
        self.idle_frames=idle_frames
        self.session_id=session_id;self.client=client;self.receiver=receiver;self.sink=sink
        self.root=Path(source_directory).resolve();self.clock=SampleTimeline(session_id)
        self.ready=queue.PriorityQueue(maxsize=5);self.submission_order=0
        self.manual=False;self.control_revision=0
        self.stop_event=threading.Event();self.producer=None;self.pacer=None;self.errors=[]
        self.on_source_complete=on_source_complete;self.on_present=on_present;self.on_started=on_started
        self.leases={};self.lease_lock=threading.RLock();self.pcm=PCMTimeline(session_id,self._audio_done)
        self.frames_written=0;self.started=threading.Event();self.finished=threading.Event();self.consumer_thread=None
        self.submit_costs=deque(maxlen=64)
        self.producer_stage=('starting',time.perf_counter_ns(),None)
        self.consumer_stage=('starting',time.perf_counter_ns(),None)
        self.last_idle_timing=None

    def stall_context(self):
        context={name:{'stage':stage,'since_ns':since,'position':position}
                for name,(stage,since,position) in (
                    ('producer',self.producer_stage),('consumer',self.consumer_stage))}
        if self.last_idle_timing is not None:context['last_completed_idle']=self.last_idle_timing
        if context['consumer']['stage']=='pcm':
            stage,since=self.pcm.read_stage
            context['pcm_read']={'stage':stage,'since_ns':since}
        return context

    def submit(self,utterance,*,priority=False,manual_revision=None,reply_guard=None):
        if not isinstance(utterance,Utterance) or utterance.session_id!=self.session_id or utterance.path.resolve().parent!=self.root:
            raise ValueError('Owned utterance for this session required')
        with self.lease_lock:
            if self.stop_event.is_set():raise RuntimeError('Continuous session stopped')
            if utterance.task_id in self.leases:raise ValueError('Utterance already pending')
            if type(priority) is not bool:raise ValueError('Priority must be a boolean')
            if manual_revision is not None and (not self.manual or manual_revision!=self.control_revision):
                raise ValueError('手动接管状态已变化')
            if manual_revision is None and self.manual:
                raise ValueError('手动接管中，请使用手动口播')
            if self.queue_full(manual_revision):raise queue.Full
            rank = -1 if manual_revision is not None else 0 if priority else 1
            self.ready.put_nowait((rank,self.submission_order,utterance))
            self.submission_order+=1
            self.leases[utterance.task_id]={'path':utterance.path,'model':False,'audio':False}
            if reply_guard is not None:self.leases[utterance.task_id]['reply_guard']=reply_guard

    def control_state(self):
        with self.lease_lock:
            return {'manual':self.manual,'control_revision':self.control_revision,'pending':self.ready.qsize()}

    def queue_full(self, manual_revision=None):
        return self.ready.qsize() >= (5 if manual_revision is not None else 4)

    def discard_pending(self, task_id):
        """Discard an owned item only if the producer has not claimed it."""
        with self.lease_lock:
            retained=[]
            discarded=False
            while not self.ready.empty():
                entry=self.ready.get_nowait()
                self.ready.task_done()
                if entry[2].task_id==task_id:
                    discarded=True
                else:
                    retained.append(entry)
            for entry in retained:self.ready.put_nowait(entry)
            if discarded:
                self.leases[task_id]['path'].unlink(missing_ok=True)
                del self.leases[task_id]

    def set_manual(self, enabled, revision):
        with self.lease_lock:
            if self.stop_event.is_set() or revision!=self.control_revision:
                raise ValueError('场次控制状态已变化，请刷新')
            if self.manual==enabled:
                return
            if not enabled:
                # Manual utterances sort first. Release only work not yet claimed.
                while not self.ready.empty():
                    entry=self.ready.get_nowait()
                    self.ready.task_done()
                    if entry[0]!=-1:
                        self.ready.put_nowait(entry)
                        break
                    self.leases[entry[2].task_id]['path'].unlink(missing_ok=True)
                    del self.leases[entry[2].task_id]
            self.manual=enabled
            self.control_revision+=1

    def _next_utterance(self):
        with self.lease_lock:
            while not self.ready.empty():
                entry=self.ready.get_nowait()
                self.ready.task_done()
                lease=self.leases[entry[2].task_id]
                guard=lease.get('reply_guard')
                if guard is not None:
                    cancellations,revision,deadline=guard
                    if any(event.is_set() for event in cancellations) or revision!=self.control_revision or time.monotonic()>=deadline:
                        lease['path'].unlink(missing_ok=True)
                        del self.leases[entry[2].task_id]
                        continue
                if self.manual and entry[0]!=-1:
                    self.ready.put_nowait(entry)
                    break
                return entry[2]
            return None

    def _release(self,source_id,part):
        with self.lease_lock:
            lease=self.leases.get(source_id)
            if not lease:return
            lease[part]=True
            if lease['model'] and lease['audio']:
                lease['path'].unlink(missing_ok=True);del self.leases[source_id]

    def _audio_done(self,event):
        self._release(event['source_id'],'audio')
        if self.on_source_complete:self.on_source_complete(event)

    def _produce(self):
        try:
            while not self.stop_event.is_set():
                self.producer_stage=('next_utterance',time.perf_counter_ns(),None)
                utterance=self._next_utterance()
                if utterance:
                    span=self.clock.reserve(self.session_id,utterance.samples);timing=asdict(span)
                    self.producer_stage=('speech_pcm',time.perf_counter_ns(),span.frame_start)
                    self.pcm.append(timing,utterance.task_id,utterance.path,utterance.pcm_sha256)
                    self.producer_stage=('speech_model',time.perf_counter_ns(),span.frame_start)
                    self.client.request('stream',timeout=max(360,utterance.samples/24000+60),session_id=self.session_id,task_id=utterance.task_id,
                        audio=str(utterance.path),pcm_sha256=utterance.pcm_sha256,timing=timing)
                    self._release(utterance.task_id,'model')
                else:
                    idle_frames=self.idle_frames if self.started.is_set() else 8
                    span=self.clock.reserve(self.session_id,idle_frames*960);timing=asdict(span);source_id='idle-'+str(span.frame_start)
                    self.producer_stage=('idle_pcm',time.perf_counter_ns(),span.frame_start)
                    self.pcm.append(timing,source_id)
                    self.producer_stage=('idle_model',time.perf_counter_ns(),span.frame_start)
                    def idle_progress(value):
                        if value.get('event')=='idle_stage':
                            self.producer_stage=('idle_'+value['stage'],time.perf_counter_ns(),value['frame_index'])
                    result=self.client.request('idle',progress=idle_progress,session_id=self.session_id,task_id=source_id,timing=timing)
                    if isinstance(result,dict) and 'idle_stage_ns' in result:
                        self.last_idle_timing={'frame_index':span.frame_start,'stage_ns':result['idle_stage_ns']}
        except BaseException as error:
            if not self.stop_event.is_set():self.errors.append(str(error));self.stop_event.set()

    def _write(self,index):
        self.consumer_stage=('receive',time.perf_counter_ns(),index)
        frame=self.receiver.take(timeout=10)
        if frame.frame_index!=index or frame.session_id!=self.session_id:raise ValueError('Presentation frame/session mismatch')
        self.consumer_stage=('pcm',time.perf_counter_ns(),index)
        pcm=self.pcm.read(960)
        if self.stop_event.is_set():raise RuntimeError('Presentation stopped')
        started=time.perf_counter_ns()
        self.consumer_stage=('submit',started,index)
        self.sink.submit(index,frame.image,pcm);self.frames_written+=1
        if index>=2:self.submit_costs.append(time.perf_counter_ns()-started)

    def run(self,frames=None):
        if frames is not None and (type(frames) is not int or frames<9):raise ValueError('At least nine frames required for prebuffered output')
        if self.producer is not None:raise RuntimeError('Session cannot be run twice')
        self.consumer_thread=threading.current_thread();success=False
        try:
            self.producer=threading.Thread(target=self._produce,name='continuous-avatar-producer');self.producer.start()
            startup_deadline=time.monotonic()+30
            while not self.receiver.full.wait(.05):
                if self.stop_event.is_set():raise RuntimeError('Presentation stopped during startup')
                if time.monotonic()>=startup_deadline:raise TimeoutError('Eight real initial frames were not ready')
            with windows_timer_precision():
                # These initial idle frames initialize the real encoder. They are
                # explicitly startup preroll, not steady deadline measurements.
                for index in range(8):self._write(index)
                origin=time.perf_counter_ns()-8*40000000
                audio_clock=getattr(self.sink,'clock_mode',None)=='audio'
                if not audio_clock:self.pacer=FramePacer(self.session_id,origin,start_frame=8)
                self.started.set()
                if self.on_started:self.on_started()
                index=8
                while not self.stop_event.is_set() and (frames is None or index<frames):
                    receive_started=time.perf_counter_ns()
                    self.consumer_stage=('receive',receive_started,index)
                    frame=self.receiver.take(timeout=10)
                    received=time.perf_counter_ns()
                    if frame.frame_index!=index:raise ValueError('Output frame order changed')
                    self.consumer_stage=('pcm',received,index)
                    pcm=self.pcm.read(960);pcm_ready=time.perf_counter_ns()
                    # Compensate measured synchronous submit cost, without moving
                    # the canonical PTS/deadline or hiding early completion.
                    lead=min(20000000,int(statistics.median(self.submit_costs))) if not audio_clock and self.submit_costs else 0
                    deadline=None if audio_clock else self.pacer.wait_for(self.session_id,index,submit_lead_ns=lead)
                    if self.stop_event.is_set():break
                    submit_started=time.perf_counter_ns()
                    self.consumer_stage=('submit',submit_started,index)
                    sink_timing=self.sink.submit(index,frame.image,pcm);self.frames_written+=1
                    stamp=({'frame_index':index,'pts_ns':index*40000000,'presented_ns':time.perf_counter_ns(),
                        'event':'device_queue_submission'}
                        if audio_clock else self.pacer.presented(deadline))
                    if not audio_clock:self.submit_costs.append(stamp['presented_ns']-submit_started)
                    self.consumer_stage=('present_observer',stamp['presented_ns'],index)
                    if self.on_present:self.on_present({**stamp,'task_id':frame.task_id,
                        'receive_ns':received-receive_started,'pcm_read_ns':pcm_ready-received,
                        'submit_started_ns':submit_started,'submit_ns':stamp['presented_ns']-submit_started,
                        'submit_lead_ns':lead,'sink_timing':sink_timing})
                    index+=1
            if self.errors:raise RuntimeError(self.errors[0])
            success=True
        finally:
            primary_error = sys.exc_info()[1]
            cleanup_errors = []

            def cleanup(action):
                try:
                    action()
                except Exception as error:
                    cleanup_errors.append(error)
                    logging.warning('场次资源清理失败：%s', type(error).__name__)

            self.stop_event.set()
            if self.pacer:cleanup(self.pacer.stop)
            if getattr(self.sink,'clock_mode',None)=='audio':
                if success:cleanup(self.sink.finish_input)
                else:cleanup(self.sink.abort)
            for action in (self.receiver.close, self.client.close, self.pcm.close):
                cleanup(action)
            if self.producer:
                cleanup(lambda: self.producer.join(timeout=10))
                if self.producer.is_alive():
                    cleanup_errors.append(RuntimeError('Avatar producer did not stop'))
            try:
                if success and not cleanup_errors:
                    cleanup(self.sink.close)
                if not success or cleanup_errors:
                    cleanup(self.sink.abort)
            finally:
                with self.lease_lock:
                    for lease in self.leases.values():
                        cleanup(lambda: lease['path'].unlink(missing_ok=True))
                    self.leases.clear()
                self.finished.set()
            if cleanup_errors and primary_error is None:
                raise RuntimeError('场次资源未能正常清理') from cleanup_errors[0]

    def stop(self):
        self.stop_event.set()
        if self.pacer:self.pacer.stop()
        if getattr(self.sink,'clock_mode',None)=='audio':self.sink.abort()
        self.receiver.close();self.client.close();self.pcm.close()
        if self.consumer_thread is None:
            self.sink.abort()
            with self.lease_lock:
                for lease in self.leases.values():lease['path'].unlink(missing_ok=True)
                self.leases.clear()
            self.finished.set()
            return
        if self.consumer_thread is not threading.current_thread() and not self.finished.wait(5):
            self.sink.abort()
            if not self.finished.wait(5):raise RuntimeError('Continuous output did not stop')
