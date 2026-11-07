"""Position compatibility for current and legacy image-inference packages."""

import numpy as np


def crop_lm_to_frame_landmarks(crop_lm: np.ndarray, bounding_box, img_size: int = 256) -> np.ndarray:
    """将克隆阶段保存的 crop_lm 还原为全图坐标 landmarks。"""
    Ymin, Ymax, Xmin, Xmax = bounding_box
    crop_w = Xmax - Xmin
    crop_h = Ymax - Ymin
    if crop_w <= 0 or crop_h <= 0:
        raise ValueError("无效 bounding_box，无法转换 crop_lm")
    target_size = img_size + int(img_size / 256) * 10
    crop_lm = np.asarray(crop_lm, dtype=np.float64)
    landmarks = np.zeros_like(crop_lm, dtype=np.float64)
    landmarks[:, 0] = Xmin + crop_lm[:, 0] * crop_w / target_size
    landmarks[:, 1] = Ymin + crop_lm[:, 1] * crop_h / target_size
    return landmarks.astype(np.int32)


def resolve_frame_landmarks(frame_data: dict, img_size: int = 256):
    """优先使用 landmarks；旧数据仅有 crop_lm 时自动转换。"""
    landmarks = frame_data.get("landmarks")
    if landmarks is None:
        crop_lm = frame_data.get("crop_lm")
        bounding_box = frame_data.get("bounding_box")
        if crop_lm is not None and bounding_box is not None:
            return crop_lm_to_frame_landmarks(crop_lm, bounding_box, img_size=img_size)
        return None
    return np.asarray(landmarks, dtype=np.int32)
