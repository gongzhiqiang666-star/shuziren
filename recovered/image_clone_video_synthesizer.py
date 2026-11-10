"""Offline frame synthesizer and audio/video muxer for image cloning."""

from __future__ import annotations

from ast import literal_eval
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import tempfile
import cv2
import numpy as np

from .image_frame_synthesizer_runtime import FrameSynthesizer


def _mux_video_audio(video_path,audio_path,output_path):
    # Keep the complete speech track: rounding to a 25fps frame grid can make
    # video a few milliseconds shorter, and -shortest drops the final AAC packet.
    result=subprocess.run([shutil.which("ffmpeg") or "ffmpeg","-nostdin","-y","-v","error",
        "-i",str(video_path),"-i",str(audio_path),"-map","0:v:0","-map","1:a:0",
        "-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(output_path)],
        capture_output=True,text=True,timeout=300)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])


class VideoSynthesizer:
    def __init__(self,data_dir,model_path,wenet_conf_path,wenet_model_path,device="cuda:0",batch_size=8,silence_feature_path=None):
        self.data_dir=Path(data_dir);self.frames_dir=self.data_dir/"frames";self.positions_dir=self.data_dir/"positions"
        self.wenet_conf_path=str(wenet_conf_path);self.wenet_model_path=str(wenet_model_path);self.device=device;self.batch_size=int(batch_size)
        self.total_frames=len(list(self.frames_dir.glob("*.jpg")));self.current_frame_position=0;self.is_forward=True
        self.engine=FrameSynthesizer(self.data_dir,model_path,device);self.engine.batch_size=self.batch_size
        self.executor=ThreadPoolExecutor(max_workers=max(1,self.batch_size),thread_name_prefix="image-clone-frame")
        self.silence_feature_path=silence_feature_path
        self.wenet_model=None
        self._closed=False

    def tensor_norm_no_training(self,img_tensor,mask=None):return self.engine.tensor_norm_no_training(img_tensor,mask)

    def _generate_frame_sequence(self,needed_frames):
        if self.total_frames<=1:return [0]*needed_frames
        output=[]
        for _ in range(needed_frames):
            output.append(self.current_frame_position)
            self.current_frame_position+=1 if self.is_forward else -1
            if self.current_frame_position>=self.total_frames:
                self.current_frame_position=self.total_frames-2;self.is_forward=False
            elif self.current_frame_position<0:
                self.current_frame_position=1;self.is_forward=True
        return output

    def _load_single_frame(self,frame_idx):
        index=int(frame_idx)%max(self.total_frames,1);frame=cv2.imread(str(self.frames_dir/f"{index:06d}.jpg"))
        if frame is None:raise FileNotFoundError(self.frames_dir/f"{index:06d}.jpg")
        metadata={};path=self.positions_dir/f"{index:06d}.txt"
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                key,sep,value=line.partition(":")
                if not sep:continue
                key=key.strip();value=value.strip()
                if key in {"bounding_box","bbox","landmarks","positions","lmk"}:metadata[key]=np.asarray(literal_eval(value))
                elif key=="is_no_face":metadata[key]=value.lower()=="true"
        if "bounding_box" not in metadata:metadata["is_no_face"]=True
        return frame,metadata

    def _load_batch_frames(self,frame_indices):
        if self._closed:raise RuntimeError("VideoSynthesizer 已关闭")
        loaded=list(self.executor.map(self._load_single_frame,frame_indices))
        return [x[0] for x in loaded],[x[1] for x in loaded]

    def _get_audio_features(self,features,indices):return [features[index] for index in indices]
    def _process_batch(self,batch_images,batch_frame_data,audio_features):return self.engine.process_batch(batch_images,batch_frame_data,audio_features)
    def inference(self,audio_info,face_data_dict,this_batch):
        images=[];metadata=[]
        for index in range(this_batch):
            item=face_data_dict[index] if not isinstance(face_data_dict,dict) else face_data_dict[index]
            images.append(item.get("image",item.get("frame")));metadata.append(item)
        return self._process_batch(images,metadata,audio_info[:this_batch])

    def extract_audio_features(self,audio_path):
        if self._closed:raise RuntimeError("VideoSynthesizer 已关闭")
        try:from bin.image_clone.wenet.compute_ctc_att_bnf import get_weget,load_ppg_model
        except ImportError as error:raise RuntimeError("离线克隆需要 WeNet 特征提取模块") from error
        probe=subprocess.run([shutil.which("ffprobe") or "ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(audio_path)],capture_output=True,text=True,check=True,timeout=30)
        duration=float(probe.stdout.strip());frame_count=max(1,round(duration*25))
        if self.wenet_model is None:
            self.wenet_model=load_ppg_model(self.wenet_conf_path,self.wenet_model_path,self.device)
        features=np.asarray(get_weget(str(audio_path),self.wenet_model,560000))
        if features.ndim!=2 or features.shape[0]<20 or features.shape[1]!=256:
            raise ValueError(f"WeNet特征形状无效: {features.shape}")
        max_start=max(0,len(features)-20);denominator=max(frame_count-1,1)
        return [features[int(i/denominator*max_start):int(i/denominator*max_start)+20] for i in range(frame_count)]

    def process_single_file(self,audio_path,output_path,frames_dir=None):
        features=self.extract_audio_features(audio_path);total_audio_frames=len(features);sequence=self._generate_frame_sequence(total_audio_frames)
        output_path=Path(output_path);output_path.parent.mkdir(parents=True,exist_ok=True)
        first,_=self._load_single_frame(sequence[0]);height,width=first.shape[:2]
        temp_video=output_path.with_name(output_path.stem+"_temp.mp4");writer=cv2.VideoWriter(str(temp_video),cv2.VideoWriter_fourcc(*"mp4v"),25,(width,height))
        if not writer.isOpened():raise RuntimeError(f"无法创建输出视频: {temp_video}")
        save_dir=Path(frames_dir) if frames_dir else None
        if save_dir:save_dir.mkdir(parents=True,exist_ok=True)
        try:
            for start in range(0,total_audio_frames,self.batch_size):
                indices=sequence[start:start+self.batch_size];images,metadata=self._load_batch_frames(indices)
                frames=self._process_batch(images,metadata,features[start:start+len(indices)])
                for offset,frame in enumerate(frames):
                    writer.write(frame)
                    if save_dir:cv2.imwrite(str(save_dir/f"frame_{start+offset:06d}.jpg"),frame)
        finally:writer.release()
        try:_mux_video_audio(temp_video,audio_path,output_path)
        finally:temp_video.unlink(missing_ok=True)
        return str(output_path)

    def close(self,wait=True):
        """Stop frame-loading workers and release the underlying ONNX session."""
        if getattr(self,"_closed",False):return
        self._closed=True
        executor=getattr(self,"executor",None);self.executor=None
        if executor is not None:executor.shutdown(wait=wait,cancel_futures=True)
        engine=getattr(self,"engine",None);self.engine=None
        close=getattr(engine,"close",None)
        if callable(close):close()
        self.wenet_model=None

    def __enter__(self):return self
    def __exit__(self,_type,_value,_traceback):self.close()

    def __del__(self):
        try:self.close(wait=False)
        except Exception:pass
