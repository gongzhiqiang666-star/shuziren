"""Landmark-aware face fusion shared by both realtime inference variants."""

from __future__ import annotations

import cv2
import numpy as np


def crop_inner_margin(img_size: int) -> int:
    return max(2, int(round(img_size * .04)))


def landmarks_to_crop_coords(landmarks, bbox, crop_shape, img_size: int):
    points = np.asarray(landmarks, dtype=np.float32).reshape(-1, 2).copy()
    left, right, top, bottom = map(float, bbox)
    if right <= left or bottom <= top: raise ValueError("Bounding box for landmark transformation has zero size.")
    crop_h, crop_w = crop_shape[:2]
    points[:, 0] = (points[:, 0] - left) * crop_w / (right - left)
    points[:, 1] = (points[:, 1] - top) * crop_h / (bottom - top)
    if (crop_w, crop_h) != (img_size, img_size):
        points *= np.asarray([img_size / crop_w, img_size / crop_h], np.float32)
    return np.clip(points, 0, img_size - 1)


def get_face_mask_heygem(crop_img, landmarks):
    height, width = crop_img.shape[:2]; points = np.asarray(landmarks, dtype=np.float32).reshape(-1, 2)
    mask = np.zeros((height, width), np.uint8)
    if len(points) >= 3:
        hull = cv2.convexHull(np.rint(points).astype(np.int32)); cv2.fillConvexPoly(mask, hull, 255)
    else:
        cv2.ellipse(mask, (width // 2, height // 2), (width * 3 // 8, height * 7 // 16), 0, 0, 360, 255, -1)
    kernel_size = max(3, (min(width, height) // 32) | 1)
    mask = cv2.dilate(mask, np.ones((kernel_size, kernel_size), np.uint8), iterations=2)
    blur_k = max(3, (min(width, height) // 12) | 1)
    return cv2.GaussianBlur(mask, (blur_k, blur_k), 0).astype(np.float32) / 255.0


def fuse_crop_heygem_lmk(original_crop, generated_face, landmarks, bbox, img_size: int, *, inplace=False):
    target = original_crop if inplace else original_crop.copy()
    generated = cv2.resize(generated_face, (target.shape[1], target.shape[0]))
    local = landmarks_to_crop_coords(landmarks, bbox, target.shape, img_size)
    if (target.shape[1], target.shape[0]) != (img_size, img_size):
        local *= np.asarray([target.shape[1] / img_size, target.shape[0] / img_size], np.float32)
    blend_mask_full = get_face_mask_heygem(target, local)
    margin = crop_inner_margin(min(target.shape[:2])); blend_mask_inner = blend_mask_full.copy()
    if margin and target.shape[0] > margin * 2 and target.shape[1] > margin * 2:
        edge = np.zeros_like(blend_mask_inner); edge[margin:-margin, margin:-margin] = 1
        blur_k = max(3, (margin * 2 + 1) | 1); edge = cv2.GaussianBlur(edge, (blur_k, blur_k), 0)
        blend_mask_inner *= edge
    alpha = blend_mask_inner[..., None].astype(np.float32)
    target[:] = np.clip(generated.astype(np.float32) * alpha + target.astype(np.float32) * (1 - alpha), 0, 255).astype(target.dtype)
    return target, blend_mask_full, blend_mask_inner


def paste_fused_crop_rectangle(image, fused_crop, bbox, *, inplace=False):
    output = image if inplace else image.copy(); height, width = output.shape[:2]
    left, right, top, bottom = map(int, np.rint(bbox)); left, top = max(0, left), max(0, top)
    right, bottom = min(width, right), min(height, bottom)
    if right <= left or bottom <= top: return output
    output[top:bottom, left:right] = cv2.resize(fused_crop, (right - left, bottom - top))
    return output
