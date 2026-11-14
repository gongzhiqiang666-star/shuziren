"""Public offline image-cloning orchestration API."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from uuid import uuid4
from pathlib import Path
import yaml

from .image_clone_generate_data import read_video_frames,process_face_frames
from .image_clone_video_synthesizer import VideoSynthesizer
from .image_video_preprocess import normalize_video


def setup_temp_dir():
    root=Path(tempfile.gettempdir())/"yunchuang_image_clone";root.mkdir(parents=True,exist_ok=True);return str(root)


def _source_identity(video_path):
    path=Path(video_path).expanduser().resolve();stat=path.stat()
    return {"source_video_path":str(path),"size":stat.st_size,"mtime_ns":stat.st_mtime_ns}


def find_cached_preprocessing(video_path,cache_base_dir):
    identity=_source_identity(video_path);base=Path(cache_base_dir)
    if not base.is_dir():return None
    for info_path in base.glob("*/cache_info.yaml"):
        try:info=yaml.safe_load(info_path.read_text(encoding="utf-8")) or {}
        except Exception:continue
        if all(info.get(key)==value for key,value in identity.items()):
            candidate=info_path.parent/"processed_data"
            if (candidate/"frames").is_dir() and (candidate/"positions").is_dir():return str(candidate)
    return None


def preprocess_video(video_path,output_dir,img_size=256,face_model_path=None):
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True);info=read_video_frames(video_path,output)
    if face_model_path is None:
        candidate=Path(__file__).resolve().parents[1]/"yunchuang_v122/_internal/assets/pretrained_models/face_detect"
        face_model_path=candidate
    process_face_frames(output/"frames",info["total_frames"],output,info,img_size=img_size,
                        cpu=False,model_path=face_model_path)
    face_frames=0;multi_face_frames=0;no_face_frames=[]
    for index in range(info["total_frames"]):
        metadata=yaml.safe_load((output/"positions"/f"{index:06d}.txt").read_text(encoding="utf-8")) or {}
        if metadata.get("is_no_face",True):no_face_frames.append(index)
        else:
            face_frames+=1
            if int(metadata.get("face_count",1))>1:multi_face_frames+=1
    return {**info,"face_frames":face_frames,"no_face_frames":no_face_frames,
            "multi_face_frames":multi_face_frames,
            "frames_dir":str(output/"frames"),"processed_data_dir":str(output)}


def generate_video(processed_data_dir,audio_path,output_path,wenet_conf_path,wenet_model_path,unet_v2_model,
                   device="cuda:0",batch_size=16,frames_dir=None,silence_feature_path=None):
    synthesizer=VideoSynthesizer(processed_data_dir,unet_v2_model,wenet_conf_path,wenet_model_path,device,batch_size,silence_feature_path)
    try:
        return synthesizer.process_single_file(audio_path,output_path,frames_dir)
    finally:
        synthesizer.close()


def generate_lip_sync_video(video_path,audio_path,output_path,config_params,use_cache=False):
    config=dict(config_params or {});cache_base=Path(config.get("cache_base_dir") or Path(setup_temp_dir())/"short_video_preprocess_cache")
    cache_base.mkdir(parents=True,exist_ok=True);processed=find_cached_preprocessing(video_path,cache_base) if use_cache else None
    if processed is None:
        identity=_source_identity(video_path);cache_id=hashlib.sha256(f"{identity['source_video_path']}:{identity['size']}:{identity['mtime_ns']}".encode()).hexdigest()[:20]
        cache_dir=cache_base/cache_id;processed_dir=cache_dir/"processed_data"
        preprocess_video(video_path,processed_dir,config.get("img_size",256),config.get("face_detect_model_dir") or config.get("face_model_path"))
        (cache_dir/"cache_info.yaml").write_text(yaml.safe_dump(identity,allow_unicode=True),encoding="utf-8");processed=str(processed_dir)
    return generate_video(processed,audio_path,output_path,config.get("wenet_config") or config.get("wenet_conf_path"),
                          config.get("wenet_model") or config.get("wenet_model_path"),config.get("unet_v2_model") or config.get("model_path"),
                          config.get("device","cuda:0"),int(config.get("batch_size",16)),config.get("frames_dir"),config.get("silence_feature_path"))


def clone_video_local(video_path,base_character_path,model_name=None,resolution="720p"):
    source=Path(video_path).expanduser().resolve()
    if not source.is_file():raise FileNotFoundError(source)
    resolution=str(resolution or "720p").lower()
    if resolution not in {"480p","720p","1080p","2k","4k"}:raise ValueError(f"不支持的清晰度档位: {resolution}")
    base=Path(base_character_path).expanduser().resolve();base.mkdir(parents=True,exist_ok=True)
    model_id=str(uuid4());model_dir=base/model_id;model_dir.mkdir()
    normalized_path=None
    try:
        normalized_path=Path(normalize_video(str(source),resolution)).resolve()
        stored_video=model_dir/"normalized_video.mp4"
        shutil.move(str(normalized_path),stored_video);normalized_path=None
        video_info=preprocess_video(str(stored_video),model_dir)
        sample=next(iter(sorted((model_dir/"frames").glob("*.jpg"))),None)
        if sample is None:raise RuntimeError("形象视频未生成任何有效帧")
        shutil.copy2(sample,model_dir/"sample.jpg")
        metadata={
            "model_id":model_id,
            "model_name":str(model_name or source.stem),
            "resolution":resolution,
            "source_video_path":str(source),
            "normalized_video_path":str(stored_video),
            "width":int(video_info.get("width") or 0),
            "height":int(video_info.get("height") or 0),
            "fps":float(video_info.get("fps") or 25),
            "total_frames":int(video_info.get("total_frames") or 0),
            "face_frames":int(video_info.get("face_frames") or 0),
            "no_face_frames":list(video_info.get("no_face_frames") or []),
        }
        (model_dir/"video_info.yaml").write_text(yaml.safe_dump(metadata,allow_unicode=True,sort_keys=False),encoding="utf-8")
        return model_id
    except BaseException:
        shutil.rmtree(model_dir,ignore_errors=True)
        if normalized_path is not None: normalized_path.unlink(missing_ok=True)
        raise
