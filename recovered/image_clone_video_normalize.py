"""Step-zero video normalization recovered from its dedicated extension."""

from __future__ import annotations

import json
import os
import subprocess

from .output_resolution import (
    DEFAULT_RESOLUTION,
    normalize_resolution_key,
    normalize_target_height,
)


def get_video_info(video_path: str) -> dict:
    command=[
        "ffprobe","-v","quiet","-print_format","json",
        "-show_format","-show_streams",video_path,
    ]
    data=json.loads(subprocess.check_output(command).decode("utf-8"))
    video_stream=next(stream for stream in data["streams"] if stream.get("codec_type")=="video")
    audio_stream=next((stream for stream in data["streams"] if stream.get("codec_type")=="audio"),{})
    width=int(video_stream["width"]);height=int(video_stream["height"])
    rotation=0
    tags=video_stream.get("tags") or {}
    if "rotate" in tags:rotation=int(tags["rotate"])
    for side_data in video_stream.get("side_data_list") or []:
        if "rotation" in side_data:rotation=int(side_data["rotation"])
    if abs(rotation)%180==90:width,height=height,width
    frame_rate=video_stream.get("r_frame_rate","0/1")
    fps=eval(frame_rate,{"__builtins__":{}},{})
    return {
        "width":width,"height":height,"fps":fps,
        "is_landscape":width>height,"rotation":rotation,
        "audio_sample_rate":int(audio_stream.get("sample_rate") or 16000),
        "audio_channels":int(audio_stream.get("channels") or 1),
    }


def normalize_video(input_path: str, resolution: str = DEFAULT_RESOLUTION) -> str:
    input_path=os.path.abspath(input_path)
    resolution_key=normalize_resolution_key(resolution)
    video_info=get_video_info(input_path)
    target_height=normalize_target_height(resolution_key,video_info["is_landscape"])
    scale_ratio=target_height/video_info["height"]
    new_width=int(video_info["width"]*scale_ratio)
    new_width-=new_width%2
    input_dir=os.path.dirname(input_path);input_filename=os.path.basename(input_path)
    output_path=os.path.join(input_dir,"normalized_"+input_filename)
    command=[
        "ffmpeg","-y","-i",input_path,
        "-vf",f"scale={new_width}:{target_height}",
        "-c:v","libx264","-preset","medium","-crf","18",
        "-c:a","aac","-b:a","128k",
        "-ar",str(video_info["audio_sample_rate"]),
        "-ac",str(video_info["audio_channels"]),
        output_path,
    ]
    subprocess.run(command,check=True)
    output_info=get_video_info(output_path)
    print(json.dumps({"input":video_info,"output":output_info},ensure_ascii=False,indent=2))
    return output_path
