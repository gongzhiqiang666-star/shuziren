"""Audio preparation for recovered voice cloning."""

import subprocess
import base64
from io import BytesIO
import shutil
import time
import yaml
from pathlib import Path

VOICE_OPTIMIZE_MAX_SECONDS = 15.5
VOICE_OPTIMIZE_SAMPLE_RATE = 24000
VOICE_OPTIMIZE_SAMPLE_TEXT = (
    "我给你们算一下啊，普通的猫一个月的饭量，两袋左右就够了，"
    "也就是六十块钱出头，这比咱们给自己点个外卖还便宜。"
)


class CloneManager:
    def __init__(self, config):
        self.config=dict(config or {})
        runtime=Path(self.config.get("runtime_dir") or Path.cwd())
        self.config.setdefault("image_base_dir",str(runtime/"assets/characters/images"))
        self.config.setdefault("voice_base_dir",str(runtime/"assets/characters/voices"))
        self._image_preview_cache={}; self._audio_preview_cache={}

    def _config_path(self,key): return str(Path(self.config[key]).expanduser().resolve())
    def _resource_dir(self,config_key,resource_id):
        raw=str(resource_id).strip(); safe=Path(raw).name
        if not safe or safe in {".",".."} or raw!=safe: raise ValueError("资源 ID 无效")
        return str(Path(self._config_path(config_key))/safe)
    def _build_cache_key(self,file_path):
        path=Path(file_path).resolve(); stat=path.stat(); return (str(path),stat.st_size,stat.st_mtime_ns)
    def _encode_file_as_data_url(self,file_path,mime_type,cache):
        key=self._build_cache_key(file_path)
        if key not in cache:
            encoded=base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
            cache.clear(); cache[key]=f"data:{mime_type};base64,{encoded}"
        return cache[key]
    def _build_model_preview(self,sample_path):
        key=self._build_cache_key(sample_path)
        cached=self._image_preview_cache.get(key)
        if cached is not None: return cached
        try:
            from PIL import Image
            with Image.open(sample_path) as source:
                image=source.convert("RGB")
                resampling=getattr(Image,"Resampling",Image).LANCZOS
                image.thumbnail((320,568),resampling)
                buffer=BytesIO()
                image.save(buffer,format="JPEG",quality=72,optimize=True)
            data_url="data:image/jpeg;base64,"+base64.b64encode(buffer.getvalue()).decode("ascii")
            self._image_preview_cache.clear();self._image_preview_cache[key]=data_url
            return data_url
        except Exception:
            return self._encode_file_as_data_url(sample_path,"image/jpeg",self._image_preview_cache)
    def _build_voice_preview(self,audio_path):
        return self._encode_file_as_data_url(audio_path,"audio/wav",self._audio_preview_cache)
    def _probe_audio_duration(self,audio_path):
        result=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(audio_path)],capture_output=True,text=True,check=True)
        return float(result.stdout.strip())

    def _create_model_info(self,model_dir,name,model_id,supported_versions=None,resolution="720p",width=720,height=1280,kt_board=False,kt_board_hit=0):
        info={"name":name,"id":model_id,"create_time":time.strftime("%Y-%m-%d %H:%M:%S"),
              "provider":"image","supported_versions":sorted(set(supported_versions or ["v2"])),
              "resolution":resolution,"width":int(width),"height":int(height),
              "kt_board":bool(kt_board),"kt_board_hit":int(kt_board_hit)}
        path=Path(model_dir)/"model_info.yaml"; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(yaml.safe_dump(info,allow_unicode=True,sort_keys=False),encoding="utf-8")
    def _create_voice_info(self,voice_dir,name,voice_id,supported_versions=None):
        info={"name":name,"id":voice_id,"create_time":time.strftime("%Y-%m-%d %H:%M:%S"),
              "provider":"voice","supported_versions":sorted(set(supported_versions or ["v1","v2","v3","malai_local","vietnam_local"]))}
        path=Path(voice_dir)/"model_info.yaml"; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(yaml.safe_dump(info,allow_unicode=True,sort_keys=False),encoding="utf-8")
    def _read_model_info(self,model_dir):
        path=Path(model_dir)/"model_info.yaml"
        if path.is_file(): return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {}

    def _create_model_record(self,directory):
        info=self._read_model_info(directory)
        sample=directory/"sample.jpg"
        kt_board=False
        if info.get("kt_board"):
            from .product_kt_overlay import model_has_kt_board_cache
            kt_board=bool(model_has_kt_board_cache(directory))
        return {"id":info.get("id",directory.name),"name":info.get("name"),
                "create_time":info.get("create_time"),
                "sample_data":self._build_model_preview(sample) if sample.is_file() else None,
                "supported_versions":info.get("supported_versions",["v2"]),
                "resolution":info.get("resolution") or False,
                "width":int(info.get("width") or 720),"height":int(info.get("height") or 1280),
                "kt_board":kt_board,"kt_board_hit":int(info.get("kt_board_hit") or 0)}
    def _create_voice_record(self,directory):
        info=self._read_model_info(directory)
        audio=directory/"ref_audio.wav"
        return {"id":info.get("id",directory.name),"name":info.get("name"),
                "create_time":info.get("create_time"),
                "sample_data":self._build_voice_preview(audio) if audio.is_file() else None,
                "provider":info.get("provider"),
                "supported_versions":info.get("supported_versions",["v1","v2","v3","malai_local","vietnam_local"])}

    def get_local_models(self):
        image_root=Path(self._config_path("image_base_dir")); voice_root=Path(self._config_path("voice_base_dir"))
        images=[self._create_model_record(p) for p in image_root.iterdir() if p.is_dir()] if image_root.is_dir() else []
        voices=[self._create_voice_record(p) for p in voice_root.iterdir() if p.is_dir()] if voice_root.is_dir() else []
        return images,voices
    def delete_model(self,model_name):
        target=Path(self._resource_dir("image_base_dir",model_name)); shutil.rmtree(target)
    def delete_voice(self,voice_name):
        target=Path(self._resource_dir("voice_base_dir",voice_name)); shutil.rmtree(target)
    def model_supports_kt_board(self,model_id):
        info=self._read_model_info(self._resource_dir("image_base_dir",model_id))
        return bool(info.get("kt_board") or info.get("enable_kt_board"))

    def clone_voice_local(self,audio_path,voice_name,voice_id,asr_lang="zh",auto_audio_optimize=False):
        from .voice_clone_infer_api import clone_voice_local
        source=audio_path
        if auto_audio_optimize:
            target=Path(self.config.get("temp_dir") or Path.cwd())/f"{voice_id}_optimized.wav"
            source=self._export_audio_within_seconds(audio_path,target,VOICE_OPTIMIZE_MAX_SECONDS)
        result=clone_voice_local(source,voice_id,self._config_path("voice_base_dir"),self.config.get("asr_weight_path") or self.config.get("models_base_path","assets/pretrained_models"),asr_lang)
        self._create_voice_info(result,voice_name,voice_id); return None

    def clone_video_local(self,video_path,model_name,model_id,resolution="720p",enable_kt_board=False):
        from .image_video_preprocess import normalize_video
        from .image_clone_api import preprocess_video
        directory=Path(self._resource_dir("image_base_dir",model_id))
        if directory.exists(): shutil.rmtree(directory)
        directory.mkdir(parents=True)
        normalized=normalize_video(video_path,resolution)
        info=preprocess_video(normalized,directory)
        frame=next((directory/"frames").glob("*"),None)
        if frame: shutil.copy2(frame,directory/"sample.jpg")
        width,height=int(info.get("width",720)),int(info.get("height",1280)); hit=0
        if enable_kt_board:
            from .product_kt_overlay import compute_and_save_kt_board_cache
            hit=compute_and_save_kt_board_cache(directory)
        self._create_model_info(directory,model_name,model_id,resolution=resolution,width=width,height=height,kt_board=enable_kt_board,kt_board_hit=hit)
        return None

    def _build_optimized_clone_audio(self,voice_id):
        from .local_voice import synthesize_local_audio
        generated=synthesize_local_audio(self.config,voice_id,VOICE_OPTIMIZE_SAMPLE_TEXT,1.0,"v1")
        target=Path(self.config.get("temp_dir") or Path.cwd())/f"{voice_id}_optimized.wav"
        return self._export_audio_within_seconds(generated,target,VOICE_OPTIMIZE_MAX_SECONDS)
    def _export_audio_within_seconds(
        self, source_path, target_path, max_seconds, sample_rate=VOICE_OPTIMIZE_SAMPLE_RATE,
    ):
        source = Path(source_path)
        target = Path(target_path)
        if source.resolve() == target.resolve():
            raise ValueError("源音频和输出文件必须不同")
        if max_seconds <= 0 or sample_rate <= 0:
            raise ValueError("音频时长和采样率必须大于零")
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
                "-map", "0:a:0", "-t", str(max_seconds), "-ac", "1",
                "-ar", str(sample_rate), "-c:a", "pcm_s16le", "-f", "wav", str(target),
            ],
            check=True,
            capture_output=True,
        )
        return str(target)
