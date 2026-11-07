"""Shared realtime face-detection runtime for v2 and origin-frame modes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict
import numpy as np

from .image_scrfd import SCRFD

BORDER_TOUCH_EPS = 2
LANDMARK_FILL_RATIO = .55
SCRFD_KPS_MIN_SPAN_RATIO = .12


class FaceDetectionResult(TypedDict, total=False):
    raw_box: np.ndarray
    detection_box: np.ndarray
    crop_box: np.ndarray
    bounding_box: np.ndarray
    landmarks: np.ndarray
    scrfd_kps: np.ndarray
    score: float
    truncated: bool
    truncated_reason: str


def should_use_cpu() -> bool:
    value = os.environ.get("YUNCHUANG_FACE_CPU", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def resolve_model_dir(model_dir=None) -> Path:
    candidates = []
    if model_dir: candidates.append(Path(model_dir).expanduser())
    env = os.environ.get("YUNCHUANG_FACE_MODEL_DIR")
    if env: candidates.append(Path(env).expanduser())
    base = Path(__file__).resolve().parents[1]
    candidates += [base / "pretrained_models", base / "resources", Path.cwd() / "pretrained_models"]
    for candidate in candidates:
        if candidate.is_dir(): return candidate.resolve()
    return candidates[0].resolve() if candidates else (base / "pretrained_models").resolve()


class RealtimeFaceDetector:
    def __init__(self, model_dir=None, cpu=None, detection_threshold=.6):
        self.model_dir = resolve_model_dir(model_dir); self.cpu = should_use_cpu() if cpu is None else bool(cpu)
        self.detection_threshold = float(detection_threshold); self.detector = None; self.landmark_session = None

    def _initialize_models(self):
        if self.detector is not None: return
        names = ("scrfd_500m_bnkps_shape640x640.onnx", "scrfd_10g_bnkps.onnx")
        model = next((self.model_dir / name for name in names if (self.model_dir / name).is_file()), None)
        if model is None: raise FileNotFoundError(f"找不到 SCRFD 模型: {self.model_dir}")
        self.detector = SCRFD(str(model), cpu=self.cpu); self.detector.prepare(-1 if self.cpu else 0, input_size=(640, 640))

    @staticmethod
    def _select_primary_face(face_boxes):
        boxes = np.asarray(face_boxes)
        if not len(boxes): return boxes
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        return boxes[int(np.argmax(areas))]

    @staticmethod
    def _expand_detection_box(frame_shape, detection_box):
        height, width = frame_shape[:2]; x1, y1, x2, y2 = map(float, detection_box[:4])
        size = max(x2 - x1, y2 - y1) * 1.45; cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        return np.asarray([max(0, cx - size / 2), max(0, cy - size * .43),
                           min(width, cx + size / 2), min(height, cy + size * .57)], dtype=np.int32)

    @staticmethod
    def _compute_crop_box(frame_shape, landmarks):
        points = np.asarray(landmarks, dtype=np.float32).reshape(-1, 2)
        if not len(points) or not np.isfinite(points).all(): return None
        low, high = points.min(axis=0), points.max(axis=0); span = high - low
        if np.any(span <= 1): return None
        size = max(span[0] * 1.65, span[1] * 1.45); center = (low + high) / 2
        center[1] += size * .04; height, width = frame_shape[:2]
        return np.asarray([max(0, center[0] - size / 2), max(0, center[1] - size / 2),
                           min(width, center[0] + size / 2), min(height, center[1] + size / 2)], dtype=np.int32)

    @staticmethod
    def crop_box_to_bounding_box(crop_box):
        x1, y1, x2, y2 = np.asarray(crop_box, dtype=np.int32).reshape(4)
        # Synthesizer slices as image[top:bottom, left:right].
        return np.asarray([x1, x2, y1, y2], dtype=np.int32)

    @staticmethod
    def _is_truncated_face(frame_shape, raw_box, landmarks, scrfd_kps=None, border_eps=BORDER_TOUCH_EPS,
                           fill_ratio=LANDMARK_FILL_RATIO, min_kps_span_ratio=SCRFD_KPS_MIN_SPAN_RATIO):
        height, width = frame_shape[:2]; x1, y1, x2, y2 = map(float, raw_box[:4])
        sides = []
        if x1 <= border_eps: sides.append("left")
        if y1 <= border_eps: sides.append("top")
        if x2 >= width - border_eps: sides.append("right")
        if y2 >= height - border_eps: sides.append("bottom")
        points = np.asarray(landmarks).reshape(-1, 2)
        if np.any(points[:, 0] < 0) or np.any(points[:, 0] >= width) or np.any(points[:, 1] < 0) or np.any(points[:, 1] >= height):
            return True, "truncated(outside)"
        if scrfd_kps is not None:
            kps = np.asarray(scrfd_kps).reshape(-1, 2); span = np.ptp(kps, axis=0)
            face_size = max(x2 - x1, y2 - y1, 1)
            if min(span) / face_size < min_kps_span_ratio: return True, "truncated(narrow_kps)"
        lm_span = np.ptp(points, axis=0); box_span = np.asarray([max(x2 - x1, 1), max(y2 - y1, 1)])
        if sides and np.min(lm_span / box_span) < fill_ratio: return True, "truncated(" + ",".join(sides) + ")"
        return bool(sides), ("truncated(" + ",".join(sides) + ")") if sides else ""

    def _predict_landmarks(self, frame, detection_box):
        # SCRFD supplies five stable landmarks. The packaged PFLD model upgrades this to 98 points;
        # retain an explicit hook so callers/tests can inject the recovered landmark runtime.
        if self.landmark_session is None: return np.empty((0, 2), dtype=np.float32)
        return np.asarray(self.landmark_session(frame, detection_box), dtype=np.float32).reshape(-1, 2)

    def _detect_faces_impl(self, frame, max_faces=1):
        self._initialize_models(); boxes, keypoints = self.detector.detect(frame, self.detection_threshold, max_num=max_faces)
        output = []
        for index, box in enumerate(boxes):
            raw = np.asarray(box[:4], dtype=np.float32); score = float(box[4]); kps = None if keypoints is None else keypoints[index]
            landmarks = self._predict_landmarks(frame, raw)
            if not len(landmarks) and kps is not None: landmarks = np.asarray(kps, dtype=np.float32)
            crop = self._compute_crop_box(frame.shape, landmarks) if len(landmarks) else self._expand_detection_box(frame.shape, raw)
            truncated, reason = self._is_truncated_face(frame.shape, raw, landmarks if len(landmarks) else raw.reshape(2, 2), kps)
            output.append({"raw_box": raw, "detection_box": raw.astype(np.int32), "crop_box": crop,
                "bounding_box": self.crop_box_to_bounding_box(crop), "landmarks": landmarks, "scrfd_kps": kps,
                "score": score, "truncated": truncated, "truncated_reason": reason})
        return output

    def _detect_many_impl(self, frame, max_faces=1):
        return self._detect_faces_impl(frame, max_faces)

    def detect_faces(self, frame, max_faces=1): return self._detect_faces_impl(frame, max_faces)
    def detect_many(self, frame, max_faces=1): return self._detect_many_impl(frame, max_faces)
    def detect(self, frame):
        results = self._detect_faces_impl(frame, 1); return results[0] if results else None
