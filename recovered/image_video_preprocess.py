"""Video normalization and frame extraction for the image-clone pipeline."""

from __future__ import annotations

from pathlib import Path


def crop_to_portrait(frame, target_ratio=9 / 16):
    height, width = frame.shape[:2]
    current = width / height
    if current > target_ratio:
        wanted = int(height * target_ratio); left = (width - wanted) // 2
        return frame[:, left:left + wanted]
    if current < target_ratio:
        wanted = int(width / target_ratio); top = (height - wanted) // 2
        return frame[top:top + wanted, :]
    return frame


def process_frame(frame, target_width=720, target_height=1280):
    import cv2
    height,width=frame.shape[:2]
    current_ratio=width/height;target_ratio=target_width/target_height
    if abs(current_ratio-target_ratio)<0.01:
        return cv2.resize(frame,(target_width,target_height))
    return cv2.resize(crop_to_portrait(frame,target_ratio),(target_width,target_height))


def extract_frames(video_path, frames_save_folder):
    import cv2
    import numpy as np
    import os
    capture=cv2.VideoCapture(video_path)
    total_frames=int(capture.get(cv2.CAP_PROP_FRAME_COUNT));output_frames=[]
    for frame_idx in range(total_frames):
        ok,frame=capture.read()
        if not ok:break
        processed_frame=process_frame(frame)
        output_path=os.path.join(frames_save_folder,f"{frame_idx}.npy")
        np.save(output_path,processed_frame);output_frames.append(output_path)
    capture.release()
    return output_frames


# Compatibility for older recovered callers; the native functions live in the
# sibling step0_video_normalize module.
from .image_clone_video_normalize import get_video_info,normalize_video
