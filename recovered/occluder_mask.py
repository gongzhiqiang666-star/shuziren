"""Recovered occluder-mask inference and compositing for image_infer_v2."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np


def resolve_occluder_model_path(
    model_path: str | os.PathLike | None = None,
) -> Path:
    """Resolve the packaged ``assets/pretrained_models/occluder.onnx`` model."""
    candidates: list[Path] = []
    if model_path:
        candidates.append(Path(model_path).expanduser())

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(
            Path(meipass) / "assets" / "pretrained_models" / "occluder.onnx"
        )

    module_path = Path(__file__).resolve()
    candidates.extend(
        parent / "assets" / "pretrained_models" / "occluder.onnx"
        for parent in module_path.parents
    )
    candidates.extend(
        (
            Path.cwd() / "assets" / "pretrained_models" / "occluder.onnx",
            Path.cwd()
            / "yunchuang_v122"
            / "_internal"
            / "assets"
            / "pretrained_models"
            / "occluder.onnx",
            Path(sys.executable).resolve().parent
            / "_internal"
            / "assets"
            / "pretrained_models"
            / "occluder.onnx",
        )
    )

    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved

    checked = "\n".join(f"  - {candidate}" for candidate in candidates)
    raise FileNotFoundError(f"未找到 Occluder 模型，已检查:\n{checked}")


class RealtimeOccluderMasker:
    """Small ONNX Runtime wrapper used by the realtime synthesis pipeline."""

    def __init__(
        self,
        model_path: str | os.PathLike | None = None,
        device: str = "cuda:0",
    ) -> None:
        import onnxruntime

        self.model_path = resolve_occluder_model_path(model_path)
        self.providers = ["CPUExecutionProvider"]
        if device.startswith("cuda"):
            self.providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = onnxruntime.InferenceSession(
            str(self.model_path), providers=self.providers
        )
        self.input_name = self.session.get_inputs()[0].name

    def infer_full_mask(
        self,
        frame: np.ndarray,
        landmarks: np.ndarray,
    ) -> np.ndarray:
        return infer_full_mask(
            self.session,
            self.input_name,
            frame,
            landmarks,
            256,
        )


def get_alignment_matrix(
    landmarks: np.ndarray, target_size: int = 256
) -> Optional[np.ndarray]:
    """Build the eye-alignment transform used by the occluder model."""
    import cv2

    points = np.asarray(landmarks, dtype=np.float32)
    left_eye = points[36:42].mean(axis=0)
    right_eye = points[42:48].mean(axis=0)
    eye_center = (left_eye + right_eye) / 2.0
    eye_delta = right_eye - left_eye
    eye_dist = np.linalg.norm(eye_delta)
    if eye_dist < 1e-6:
        return None

    angle = np.degrees(np.arctan2(eye_delta[1], eye_delta[0]))
    scale = target_size * 0.3 / eye_dist
    matrix = cv2.getRotationMatrix2D(tuple(eye_center), angle, scale)
    desired_eye_center = np.array(
        [target_size * 0.5, target_size * 0.42], dtype=np.float32
    )
    matrix[:, 2] += desired_eye_center - eye_center
    return matrix


def infer_full_mask(
    session,
    input_name: str,
    frame: np.ndarray,
    landmarks: np.ndarray,
    target_size: int = 256,
) -> np.ndarray:
    """Infer an aligned occlusion mask and warp it back to the source frame."""
    import cv2

    if len(landmarks) < 48:
        raise ValueError(f"Occluder 需要至少 48 个全图 landmarks，当前: {len(landmarks)}")

    matrix = get_alignment_matrix(landmarks, target_size)
    if matrix is None:
        raise ValueError("Occluder 对齐矩阵计算失败")

    aligned = cv2.warpAffine(
        frame,
        matrix,
        (target_size, target_size),
        flags=cv2.INTER_LINEAR,
    )
    img_input = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    img_input = np.expand_dims(img_input.transpose(2, 0, 1), axis=0)
    mask_output = np.squeeze(session.run(None, {input_name: img_input})[0])
    if mask_output.ndim == 3:
        mask_output = mask_output[0]
    mask_output = np.clip(mask_output, 0.0, 1.0).astype(np.float32)

    matrix_inv = cv2.invertAffineTransform(matrix)
    return cv2.warpAffine(
        mask_output,
        matrix_inv,
        (frame.shape[1], frame.shape[0]),
        flags=cv2.INTER_LINEAR,
    )


def paste_occluder_mask(
    image: np.ndarray,
    generated_face: np.ndarray,
    bounding_box,
    full_mask: np.ndarray,
    *,
    inplace: bool = False,
) -> np.ndarray:
    """Blend a generated face into its rectangle using the full-frame mask."""
    import cv2

    left, right, top, bottom = map(int, bounding_box)
    crop_width = right - left
    crop_height = bottom - top
    if crop_width <= 0 or crop_height <= 0:
        raise ValueError(f"无效 bounding_box: {bounding_box}")

    face_img_resized = cv2.resize(
        generated_face,
        (crop_width, crop_height),
        interpolation=cv2.INTER_LINEAR,
    )
    mask_crop = full_mask[top:bottom, left:right]
    mask_blurred = cv2.blur(mask_crop, (11, 11)).astype(np.float32)
    alpha = mask_blurred[..., np.newaxis]
    if alpha.shape[2] == 1:
        alpha = np.repeat(alpha, 3, axis=2)

    result = image if inplace else image.copy()
    original_crop = result[top:bottom, left:right].astype(np.float32)
    blended = (
        original_crop * (1.0 - alpha)
        + face_img_resized.astype(np.float32) * alpha
    )
    result[top:bottom, left:right] = blended.astype(np.uint8)
    return result
