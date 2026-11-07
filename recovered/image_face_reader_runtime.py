"""Frame-oriented face pipeline used by origin-frame playback."""

from __future__ import annotations

from .image_face_detector_runtime import RealtimeFaceDetector
from .occluder_mask import RealtimeOccluderMasker


class RealtimeFacePipeline:
    def __init__(self, device="cuda:0", detect_max_faces=1, enable_occluder=False,
                 occluder_model_path="", face_model_dir=""):
        self.device = device; self.detect_max_faces = max(1, int(detect_max_faces))
        self.detector = RealtimeFaceDetector(face_model_dir or None, cpu=not str(device).startswith("cuda"))
        self.enable_occluder = bool(enable_occluder)
        self.occluder = RealtimeOccluderMasker(occluder_model_path or None, device) if self.enable_occluder else None

    def _attach_full_mask(self, frame, detection):
        result = dict(detection)
        if self.occluder is not None and len(result.get("landmarks", ())) >= 48:
            result["full_mask"] = self.occluder.infer_full_mask(frame, result["landmarks"])
        return result

    def detect_frame(self, frame):
        detections = self.detector.detect_many(frame, self.detect_max_faces)
        detections = sorted(detections, key=lambda item: float(item.get("score", 0)), reverse=True)
        output = []
        for face_index, detection in enumerate(detections):
            item = self._attach_full_mask(frame, detection); item["face_index"] = face_index; item["is_no_face"] = False
            output.append(item)
        return output

    def detect_batch(self, frames):
        return [self.detect_frame(frame) for frame in frames]
