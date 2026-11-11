"""Origin-frame live manager with interaction audio takeover and seek support."""

from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
import numpy as np

from .image_infer_audio import AudioBatch
from .image_face_reader_runtime import RealtimeFacePipeline
from .image_frame_synthesizer_runtime import FrameSynthesizer
from .origin_tape import OriginTape, TapeFrame
from . import image_infer_audio as shared


def _decode_audio(path, sample_rate):
    result = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                             "-ar", str(sample_rate), "-f", "f32le", "-"], capture_output=True)
    if result.returncode: raise RuntimeError(result.stderr.decode(errors="replace"))
    return np.frombuffer(result.stdout, np.float32).copy()


class VideoStreamManager:
    def __init__(self, wenet_conf_path, wenet_model_path, model_path, video_path_for_driving,
                 silence_feature_path=None, window_width=1280, window_height=720,
                 buffer_threshold=50, device="cuda:0", batch_size=8,
                 synthesis_window_seconds=1.0, output_sample_rate=24000,
                 image_output_mode="window", is_interrupt=False, detect_max_faces=1,
                 enable_occluder=False, occluder_model_path="", face_model_dir=""):
        self.wenet_conf_path=str(wenet_conf_path);self.wenet_model_path=str(wenet_model_path);self.wenet_model=wenet_model_path
        self.model_path=str(model_path);self.video_path_for_driving=str(video_path_for_driving);self.window_width=int(window_width)
        self.window_height=int(window_height);self.buffer_threshold=int(buffer_threshold);self.device=device
        self.synthesis_window_seconds=float(synthesis_window_seconds);self.image_output_mode=image_output_mode
        self.is_interrupt=bool(is_interrupt);self.detect_max_faces=max(1,int(detect_max_faces));self.enable_occluder=bool(enable_occluder)
        self.occluder_model_path=occluder_model_path;self.face_model_dir=face_model_dir;self.player=None
        self.feature_sample_rate=16000;self.output_sample_rate=shared.resolve_output_sample_rate(output_sample_rate);self.fps=25
        self.samples_per_frame=self.feature_sample_rate//self.fps;self.output_samples_per_frame=self.output_sample_rate//self.fps
        self.audio_queues={"normal":queue.Queue(),"danmu":queue.Queue()};self.queue_priority=["danmu","normal"]
        self.pause_event=threading.Event();self.stop_event=threading.Event();self.processing_lock=threading.Lock();self._seek_lock=threading.Lock()
        self._pending_seek_ms=None;self._in_interact=False;self.current_interaction_audio_path=None
        self.idle_fade_out_frames=13;self.idle_fade_in_frames=13;self._fade_out_total=13;self._fade_out_remaining=0
        self._fade_in_total=13;self._fade_in_remaining=0;self._fade_out_started=False
        self.silence_wenet_features=self._load_silence_features(silence_feature_path)
        model_root=Path(model_path).parent if Path(model_path).suffix else Path(model_path)
        self.synthesizer=FrameSynthesizer(model_root,model_path,device,enable_occluder);self.synthesizer.batch_size=int(batch_size);self._batch_size=int(batch_size)
        self.tape=OriginTape(video_path_for_driving,self.output_sample_rate,prefetch=max(24,batch_size*3));self.tape.open()
        if self.tape.width and self.tape.height: self.window_width,self.window_height=self.tape.width,self.tape.height
        self.face_pipeline=None;self._current_audio_path=None;self.worker_thread=None
        self.stats_start_time=time.time();self.total_frames_processed=0;self.total_synthesis_time=0.0

    @staticmethod
    def _load_silence_features(path):
        if path and Path(path).is_file():
            value=np.asarray(np.load(path),np.float32);return value if value.ndim==3 else value.reshape(-1,20,256)
        return np.zeros((1,20,256),np.float32)

    def _apply_gain(self,audio,gain0,gain1):
        samples=np.asarray(audio,np.float32);return samples*np.linspace(gain0,gain1,len(samples),dtype=np.float32) if len(samples) else samples

    def _fade_origin_audio(self,audio,fading_out):
        if fading_out:
            index=self._fade_out_total-self._fade_out_remaining;g0=1-index/max(1,self._fade_out_total);g1=1-(index+1)/max(1,self._fade_out_total)
            self._fade_out_remaining=max(0,self._fade_out_remaining-1)
        else:
            index=self._fade_in_total-self._fade_in_remaining;g0=index/max(1,self._fade_in_total);g1=(index+1)/max(1,self._fade_in_total)
            self._fade_in_remaining=max(0,self._fade_in_remaining-1)
        return self._apply_gain(audio,g0,g1)

    def _ensure_face_pipeline(self):
        if self.face_pipeline is None:
            self.face_pipeline=RealtimeFacePipeline(self.device,self.detect_max_faces,self.enable_occluder,self.occluder_model_path,self.face_model_dir)
        return self.face_pipeline

    def _detection_to_meta(self,detections):
        if not detections:return {"is_no_face":True,"faces":[]}
        return {"is_no_face":False,"faces":detections,**detections[0]}

    def _make_origin_audio_batch(self,tape_frame):
        audio=tape_frame.audio
        if self._fade_out_remaining>0:audio=self._fade_origin_audio(audio,True)
        elif self._fade_in_remaining>0:audio=self._fade_origin_audio(audio,False)
        return AudioBatch(np.zeros(self.samples_per_frame,np.float32),audio,"<origin>",0,"origin",None)

    @staticmethod
    def _is_interact_path(audio_path): return bool(audio_path and audio_path not in {"<origin>","<padding_silence>"})

    def _has_queued_interact(self): return any(not q.empty() for q in self.audio_queues.values())

    def _get_next_audio_batch(self,current_audio_path):
        return self._dequeue_interaction(self._batch_size)

    def _dequeue_interaction(self,frame_count):
        selected=next((name for name in self.queue_priority if not self.audio_queues[name].empty()),None);items=[]
        if selected:
            q=self.audio_queues[selected]
            while len(items)<frame_count:
                try:items.append(q.get_nowait())
                except queue.Empty:break
        path=items[-1].audio_path if items else None
        items.extend([None]*(self._batch_size-len(items)))
        return items,path

    def _seek_to_ms_locked(self,start_ms):
        self.tape.seek_ms(max(0,int(start_ms)));self._pending_seek_ms=None;return True

    def _consume_pending_seek_locked(self):
        if self._pending_seek_ms is not None and not self._in_interact:self._seek_to_ms_locked(self._pending_seek_ms)

    def schedule_seek_after_interaction(self,start_ms):
        with self._seek_lock:self._pending_seek_ms=max(0,int(start_ms))

    def seek_to_ms(self,start_ms):
        with self._seek_lock:
            if self._in_interact:self._pending_seek_ms=max(0,int(start_ms));return False
            return self._seek_to_ms_locked(start_ms)

    def _read_warmup_image(self):
        import cv2
        cap=cv2.VideoCapture(self.video_path_for_driving)
        try:
            ok,image=cap.read();return image if ok else None
        finally:cap.release()

    def _warmup_interact_path(self):
        image=self._read_warmup_image()
        if image is not None:
            pipeline=self._ensure_face_pipeline();pipeline.detect_frame(image)

    @property
    def background_audio(self):return self.tape.audio
    @property
    def bg_audio_pointer(self):return self.tape.sample_pointer
    @bg_audio_pointer.setter
    def bg_audio_pointer(self,sample):self.tape.sample_pointer=sample

    def get_near_audio_clip(self,seconds=10.0,out_dir=None):
        audio,start,end=self.tape.get_audio_clip(self.tape.sample_pointer,seconds);folder=Path(out_dir or Path(self.video_path_for_driving).parent)
        folder.mkdir(parents=True,exist_ok=True);path=folder/f"origin_audio_{start}_{end}.wav"
        pcm=np.clip(audio,-1,1);pcm=(pcm*32767).astype(np.int16)
        with wave.open(str(path),"wb") as output:output.setparams((1,2,self.output_sample_rate,0,"NONE",""));output.writeframes(pcm.tobytes())
        return str(path)

    def extract_audio_features(self,audio_path):return shared.extract_audio_features(self,audio_path)

    def add_audio_to_queue(self,audio_path,queue_name="normal",use_silent_features=False,target_face_index=0):
        if queue_name not in self.audio_queues:raise ValueError(f"未知队列: {queue_name}")
        output=_decode_audio(audio_path,self.output_sample_rate);feature_audio=_decode_audio(audio_path,self.feature_sample_rate)
        frames=max(1,int(np.ceil(len(feature_audio)/self.samples_per_frame)))
        if use_silent_features or self.pause_event.is_set():features=np.tile(self.silence_wenet_features,(frames,1,1))[:frames]
        else:features=np.asarray(self.extract_audio_features(audio_path),np.float32)
        shared.enqueue_audio_frames(self,audio_path,queue_name,target_face_index,feature_audio,output,features);self._current_audio_path=audio_path

    def init_player(self):shared.initialize_output_player(self)

    def process_and_manage_audio(self):
        current_path=None
        while not self.stop_event.is_set() and self.player and self.player.running:
            tape_frames=self.tape.take_frames(self._batch_size,2.0)
            if not tape_frames:continue
            if len(tape_frames)==self._batch_size:
                interaction,current_path=self._get_next_audio_batch(current_path)
            else:
                interaction,current_path=self._dequeue_interaction(len(tape_frames))
            has_interact=any(x is not None for x in interaction)
            if has_interact and not self._in_interact:self._in_interact=True;self._fade_out_remaining=self._fade_out_total
            if has_interact and not self._has_queued_interact():
                with self._seek_lock:
                    if self._pending_seek_ms is not None:
                        # The next iteration seeks before reading any resumed source audio.
                        last_interaction=max(index for index,batch in enumerate(interaction) if batch is not None)
                        tape_frames=tape_frames[:last_interaction+1]
            if self._in_interact and not has_interact and not self._has_queued_interact():
                with self._seek_lock:
                    self._in_interact=False
                    seek_pending=self._pending_seek_ms is not None
                    self._consume_pending_seek_locked()
                self._fade_in_remaining=self._fade_in_total
                current_path=None
                if seek_pending:
                    tape_frames=self.tape.take_frames(self._batch_size,2.0)
                    if not tape_frames:continue
            features=[];audios=[]
            for index,tape_frame in enumerate(tape_frames):
                batch=interaction[index] if index<len(interaction) else None
                if batch is None:
                    origin=self._make_origin_audio_batch(tape_frame);features.append(np.zeros((20,256),np.float32));audios.append(origin.original_audio_chunk)
                else:features.append(batch.wenet_feature);audios.append(batch.original_audio_chunk)
            begin=time.time()
            images=[x.image for x in tape_frames]
            frames=images
            if has_interact:
                detections=self._ensure_face_pipeline().detect_batch(images)
                metadata=[self._detection_to_meta(x) for x in detections]
                frames=self.synthesizer.synthesize_batch(features,images,metadata)
            self.total_synthesis_time+=time.time()-begin
            for frame,audio,tape_frame,batch in zip(frames,audios,tape_frames,interaction):
                self.player.upload_frame({"frame":frame,"audio":audio,"index":tape_frame.index,"physical_index":tape_frame.frame_index,"audio_path":batch.audio_path if batch is not None else "<origin>"})
            self.total_frames_processed+=len(frames)

    def start_playing(self):
        if self.worker_thread is not None and self.worker_thread.is_alive():
            return True
        if self.player is None:self.init_player()
        self.stop_event.clear();self.tape.start(self.tape._play_index)
        try:
            if sys.platform == "win32":
                self.player.start_playing()
            else:
                threading.Thread(target=self.player.start_playing,daemon=True).start()
        except BaseException:
            self.stop_event.set()
            self.tape.stop()
            raise
        self.worker_thread=threading.Thread(target=self.process_and_manage_audio,daemon=True);self.worker_thread.start();return True

    def stop_playing(self):
        self.stop_event.set();self.tape.stop()
        if self.player:self.player.stop_playing()
        if self.worker_thread and self.worker_thread.is_alive() and self.worker_thread is not threading.current_thread():self.worker_thread.join(timeout=2)
        self.worker_thread=None

    def pause(self):self.pause_event.set()
    def resume(self):self.pause_event.clear()
    def clear_audio_queues(self):
        for q in self.audio_queues.values():
            with q.mutex:q.queue.clear()
        self._current_audio_path=None
    def get_queue_lengths(self):return {name:q.qsize() for name,q in self.audio_queues.items()}
    def get_current_playing_audio_path(self):return self._current_audio_path

    def __del__(self):
        try:self.stop_playing();self.tape.close()
        except Exception:pass


def _resolve_output_sample_rate(preferred_rate,channels=1):return shared.resolve_output_sample_rate(preferred_rate,channels)
