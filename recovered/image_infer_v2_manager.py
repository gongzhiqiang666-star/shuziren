"""Top-level v2 live image inference manager."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import threading
import time
import cv2
import numpy as np

from .image_frame_synthesizer_runtime import FrameSynthesizer
from .image_realtime_face_reader import RealtimeFaceReader
from .image_rtmp_face_reader import RtmpFaceReader
from .image_v2_video_face_reader import VideoFaceReader
from . import image_infer_audio as runtime
from .output_mode import normalize_output_mode


class VideoStreamManager:
    def __init__(self, data_dir, wenet_conf_path, wenet_model_path, model_path,
                 silence_feature_path=None, window_width=1280, window_height=720,
                 buffer_threshold=50, device="cuda:0", batch_size=8,
                 synthesis_window_seconds=1.0, output_sample_rate=24000,
                 image_output_mode="window", is_interrupt=False, input_mode="file",
                 camera_index=-1, camera_resolution="1280x720", video_path_for_driving="",
                 rtmp_url_for_driving="", enable_action_generalization=False,
                 detect_max_faces=1, auth_token="", enable_occluder=False,
                 occluder_model_path="", face_model_dir=""):
        self.data_dir = str(data_dir); self.wenet_conf_path = str(wenet_conf_path); self.wenet_model_path = str(wenet_model_path)
        self.wenet_model = wenet_model_path; self.window_width = int(window_width); self.window_height = int(window_height)
        self.buffer_threshold = int(buffer_threshold); self.device = device; self.synthesis_window_seconds = float(synthesis_window_seconds)
        self.image_output_mode = normalize_output_mode(image_output_mode); self.is_interrupt = bool(is_interrupt); self.input_mode = input_mode
        self.camera_index = int(camera_index); self.camera_resolution = camera_resolution
        self.video_path_for_driving = video_path_for_driving; self.rtmp_url_for_driving = rtmp_url_for_driving
        self.enable_action_generalization = bool(enable_action_generalization); self.detect_max_faces = max(1, int(detect_max_faces))
        self.auth_token = auth_token; self.enable_occluder = bool(enable_occluder); self.occluder_model_path = occluder_model_path
        self.face_model_dir = face_model_dir; self.player = None; self.face_reader = self.face_reader_iterator = None
        self.preloaded_frame_queue = self.preload_stop_event = self.preload_thread = None
        self.live_frame_queue = self.live_frame_stop_event = self.live_frame_thread = None
        self.camera_frame_buffer = []; self._last_live_frame_batch = []; self._live_frame_physical_index = 0
        self.executor = None; self._current_audio_path = None
        runtime.initialize_speech_state(self, output_sample_rate)
        self.synthesizer = FrameSynthesizer(data_dir, model_path, device, enable_occluder); self.synthesizer.batch_size = int(batch_size)
        self.silence_wenet_features = self._load_silence_features(silence_feature_path)
        if input_mode == "file":
            runtime.initialize_file_frame_source(self, data_dir); runtime.initialize_frame_preload(self)
        elif input_mode == "camera":
            self.face_reader = RealtimeFaceReader(device, enable_occluder, occluder_model_path, face_model_dir)
        elif input_mode == "video":
            self.face_reader = VideoFaceReader(device, self.detect_max_faces, enable_occluder, occluder_model_path, face_model_dir)
        elif input_mode == "rtmp":
            self.face_reader = RtmpFaceReader(device, enable_occluder, occluder_model_path, face_model_dir)
        else: raise ValueError(f"不支持的输入模式: {input_mode}")
        runtime.initialize_playback_stats(self)

    @staticmethod
    def _load_silence_features(path):
        if path and Path(path).is_file():
            value = np.asarray(np.load(path), np.float32)
            return value if value.ndim == 3 else value.reshape(-1, 20, 256)
        return np.zeros((1, 20, 256), np.float32)

    _has_valid_bounding_box = staticmethod(runtime.has_valid_bounding_box)
    @classmethod
    def _face_slot_from_detection(cls, face_data):
        return runtime.face_slot_from_detection(face_data)

    def _fade_in_gain_curve(self, fade_frame_index, samples):
        total = self._fade_in_total or self.idle_fade_in_frames
        return runtime.fade_in_gain_curve(total,fade_frame_index,samples)

    def _fade_out_gain_curve(self, fade_frame_index, samples):
        total = self._fade_out_total or self.idle_fade_out_frames
        return runtime.fade_out_gain_curve(total,fade_frame_index,samples)

    def _apply_playback_gain(self, audio_batch, curve_fn, start_index, frame_count): return runtime.apply_playback_gain(audio_batch, curve_fn, start_index, frame_count)
    def _batch_primary_queue(self, audio_batch): return runtime.batch_primary_queue(audio_batch)
    def _make_silence_audio_batches(self, count): return runtime.make_silence_audio_batches(count, self.samples_per_frame, self.output_samples_per_frame, self.silence_wenet_features)
    def _peek_preferred_queue(self, current_audio_path, queue_interrupt_mode):
        return runtime.peek_preferred_queue(
            self.audio_queues,
            self.queue_priority,
            current_audio_path,
            queue_interrupt_mode,
        )
    def _pull_normal_for_fade_out(self, current_audio_path, count): return runtime.pull_normal_for_fade_out(self.audio_queues, count, current_audio_path, self.samples_per_frame, self.output_samples_per_frame, self.silence_wenet_features)
    def _get_next_audio_batch(self, current_audio_path):
        result = runtime.get_next_audio_batch(self, current_audio_path); self._current_audio_path = result[1]; return result
    @classmethod
    def _resolve_face_metadata_for_synthesis(cls, metadata, target_face_index=0): return runtime.resolve_face_metadata_for_synthesis(cls, metadata, target_face_index)
    def _build_live_frame_batch(self, frames, detections):
        output=[]
        for frame, faces in zip(frames,detections):
            output.append(runtime.FrameData(frame,{"faces":faces,"is_no_face":not bool(faces)},self._live_frame_physical_index));self._live_frame_physical_index+=1
        return output
    def _get_camera_frame_batch(self,last_frame_index): return runtime.get_camera_frame_batch(self,last_frame_index)
    def _create_dummy_frame_batch(self): return runtime.create_dummy_frame_batch(self)
    def _load_single_frame_data(self,frame_idx): return runtime.load_single_frame_data(self,frame_idx)
    def _load_batch_frame_data(self,frame_indices): return runtime.load_batch_frame_data(self,frame_indices)
    def _generate_sequential_frame_sequence(self,needed_frames): return runtime.generate_sequential_frame_sequence(self,needed_frames)
    def _generate_frame_sequence(self,needed_frames): return runtime.generate_action_frame_sequence(self,needed_frames) if self.enable_action_generalization else runtime.generate_sequential_frame_sequence(self,needed_frames)
    def _process_audio_batch(self,audio_batch,frame_data_batch,last_frame_index): return runtime.process_audio_batch(self,audio_batch,frame_data_batch,last_frame_index)
    def _preload_frames_worker(self): return runtime.run_preload_frames_worker(self)
    def _live_frame_worker(self): return runtime.run_live_frame_worker(self)
    def _start_live_frame_pipeline(self): return runtime.start_live_frame_pipeline(self)
    def _stop_live_frame_pipeline(self): return runtime.stop_live_frame_pipeline(self)
    def _record_rate_stats(self,frame_count,read_elapsed,synthesis_elapsed): return runtime.record_rate_stats(self,frame_count,read_elapsed,synthesis_elapsed)

    def init_player(self): return runtime.initialize_output_player(self)
    def start_playing(self): return runtime.start_playing(self)
    def stop_playing(self): return runtime.stop_playing(self)
    def process_and_manage_audio(self): return runtime.run_preloaded_inference_loop(self)
    def add_audio_to_queue(self,audio_path,queue_name="normal",use_silent_features=False,target_face_index=0):
        self._current_audio_path=audio_path; return runtime.add_audio_to_queue(self,audio_path,queue_name,use_silent_features,target_face_index)
    def extract_audio_features(self,audio_path): return runtime.extract_audio_features(self,audio_path)
    def get_queue_lengths(self): return runtime.get_queue_lengths(self)
    def get_current_playing_audio_path(self): return self._current_audio_path
    def clear_audio_queues(self):
        for _,audio_queue in self.audio_queues.items():
            while not audio_queue.empty():audio_queue.get()
        player=getattr(self,"player",None)
        frame_queue=getattr(player,"frame_queue",None) if player is not None else None
        if frame_queue is not None:
            with frame_queue.mutex:frame_queue.queue.clear()
        self._speech_av_mode="normal"
        self._last_real_queue="silence"
        self._pending_fade_in=False
        self._fade_out_remaining=0
        self._fade_out_total=0
        self._fade_in_remaining=0
        self._fade_in_total=0
        self._current_audio_path=None
    def pause(self): self.pause_event.set()
    def resume(self): self.pause_event.clear()

    def switch_image_model(self,new_data_dir):
        if self.input_mode!="file":
            print("警告: 仅在 'file' 输入模式下支持无缝切换形象。")
            return None
        print(f"开始切换形象素材至: {new_data_dir}")
        if self.preload_stop_event:self.preload_stop_event.set()
        if self.preload_thread and self.preload_thread.is_alive():
            self.preload_thread.join(timeout=2)
            print("旧的预加载线程已停止。")
        if self.preloaded_frame_queue:
            with self.preloaded_frame_queue.mutex:self.preloaded_frame_queue.queue.clear()
            print("预加载队列已清空。")
        self.frames_dir=os.path.join(new_data_dir,"frames")
        self.positions_dir=os.path.join(new_data_dir,"positions")
        frames=[name for name in os.listdir(self.frames_dir) if name.endswith(".jpg")]
        self.total_frames=len(frames)
        self.current_frame_position=0
        self.sequence_frame_position=0
        self.current_direction=None
        print(f"形象素材路径已更新，总帧数: {self.total_frames}")
        self.preload_stop_event=threading.Event()
        self.preload_thread=threading.Thread(target=self._preload_frames_worker,daemon=True)
        self.preload_thread.start()
        print("新的预加载线程已启动。")
        return None

    def drive_with_special_video(self,video_path,audio_path,force_is_no_face=False):
        print(f"开始执行特殊视频驱动任务: video='{video_path}', audio='{audio_path}', force_is_no_face={force_is_no_face}")
        if not self.player or not self.player.running:
            print("错误: 播放器未运行，无法执行特殊视频驱动任务。")
            return None
        import librosa
        print(f"开始处理音频: {audio_path}")
        audio,_=librosa.load(audio_path,sr=self.output_sample_rate,mono=True)
        all_audio_features=list(self.extract_audio_features(audio_path))
        if not all_audio_features:return None
        total_audio_frames=max(len(all_audio_features),int(np.ceil(len(audio)/self.output_samples_per_frame)))
        if len(all_audio_features)<total_audio_frames:
            all_audio_features.extend([all_audio_features[-1]]*(total_audio_frames-len(all_audio_features)))
        with self.processing_lock:
            print("已获取处理锁，常规流程已暂停，开始注入特殊视频。")
            if getattr(self,"special_video_face_reader",None) is None:
                print("初始化特殊视频驱动器...")
                self.special_video_face_reader=VideoFaceReader(
                    device=str(self.device),enable_occluder=self.enable_occluder,
                    occluder_model_path=self.occluder_model_path,face_model_dir=self.face_model_dir,
                )
                print("特殊视频驱动器初始化完成。")
            reader=self.special_video_face_reader
            reader.start_capture(video_path)
            frame_number=(self.player.get_last_queue_item() or {}).get("index",-1)+1
            processed=0
            iterator=iter(reader)
            while processed<total_audio_frames:
                needed=min(self.synthesizer.batch_size,total_audio_frames-processed)
                frames=[];detections=[]
                while len(frames)<needed:
                    try:
                        new_frames,new_detections=next(iterator)
                    except StopIteration:
                        if not reader.rewind():
                            print("视频驱动循环重置失败: 无法重置视频读取器")
                            return None
                        iterator=iter(reader);continue
                    take=min(needed-len(frames),len(new_frames))
                    frames.extend(new_frames[:take]);detections.extend(new_detections[:take])
                    overflow=list(zip(new_frames[take:],new_detections[take:]))
                    if overflow and hasattr(reader,"internal_buffer"):reader.internal_buffer.extend(overflow)
                frame_objects=self._build_live_frame_batch(frames,detections)
                metadata=[]
                for item in frame_objects:
                    data=self._resolve_face_metadata_for_synthesis(item.metadata,0)
                    if force_is_no_face:data={"is_no_face":True}
                    metadata.append(data)
                features=all_audio_features[processed:processed+needed]
                generated=self.synthesizer.synthesize_batch(features,frames,metadata)
                for offset,frame in enumerate(generated):
                    start=(processed+offset)*self.output_samples_per_frame
                    chunk=np.asarray(audio[start:start+self.output_samples_per_frame],dtype=np.float32)
                    if len(chunk)<self.output_samples_per_frame:
                        chunk=np.pad(chunk,(0,self.output_samples_per_frame-len(chunk)))
                    self.player.upload_frame({"frame":frame,"index":frame_number,
                                              "audio":chunk,"physical_index":frame_objects[offset].physical_index})
                    frame_number+=1
                processed+=needed
        print("特殊视频驱动任务完成，释放处理锁。")
        return None

    def process_single_file(self,audio_path,output_path=None,batch_size=None):
        if batch_size is None:
            batch_size = self.synthesizer.batch_size
        print("开始处理音频: " + audio_path)
        start_time = time.time()
        all_audio_features = self.extract_audio_features(audio_path)
        output_frames = [] if not output_path else None
        video_writer = None
        temp_video_path = None
        try:
            for start in range(0, len(all_audio_features), batch_size):
                actual_batch_size = min(batch_size, len(all_audio_features) - start)
                frame_indices = self._generate_frame_sequence(actual_batch_size)
                frame_data = self._load_batch_frame_data(frame_indices)
                generated_frames = self.synthesizer.synthesize_batch(
                    batch_audio_features=all_audio_features[start:start + actual_batch_size],
                    batch_images=[item.image for item in frame_data],
                    batch_frame_data=[item.metadata for item in frame_data],
                )[:actual_batch_size]
                if not output_path:
                    output_frames.extend(generated_frames)
                    continue
                if video_writer is None:
                    if not generated_frames:
                        raise RuntimeError("没有生成任何视频帧")
                    height, width = generated_frames[0].shape[:2]
                    temp_video_path = os.path.splitext(output_path)[0] + "_temp.mp4"
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    video_writer = cv2.VideoWriter(temp_video_path, fourcc, self.fps, (width, height))
                    if not video_writer.isOpened():
                        raise RuntimeError("无法创建临时视频文件: " + temp_video_path)
                for frame in generated_frames:
                    video_writer.write(frame)

            if output_path:
                if video_writer is None:
                    raise RuntimeError("视频帧写入失败，没有生成临时视频")
                video_writer.release()
                video_writer = None
                print("合并音频与视频...")
                subprocess.run([
                    "ffmpeg", "-y", "-i", temp_video_path, "-i", audio_path,
                    "-c:v", "copy", "-c:a", "aac", "-strict", "experimental",
                    "-map", "0:v:0", "-map", "1:a:0", output_path,
                ], check=True)
                os.remove(temp_video_path)
                result = output_path
            else:
                result = output_frames
            print(f"处理完成，总耗时: {time.time() - start_time:.2f}秒")
            return result
        finally:
            if video_writer is not None:
                video_writer.release()

    def __del__(self):
        try:
            self.stop_playing()
            if self.executor is not None: self.executor.shutdown(wait=False, cancel_futures=True)
        except Exception: pass


def _resolve_output_sample_rate(preferred_rate,channels=1): return runtime.resolve_output_sample_rate(preferred_rate,channels)
