"""File video reader used by the v2 realtime image pipeline."""

from __future__ import annotations

from .origin_video_face_reader import VideoFaceReader as _OriginVideoFaceReader


class VideoFaceReader(_OriginVideoFaceReader):
    def start_capture(self, video_path):
        return super().start_capture(video_path, 0)

    def _attach_full_mask(self, frame, detection):
        return self.face_pipeline._attach_full_mask(frame, detection) if detection else detection

    def _preprocess_thread(self):
        # The v2 binary has the same producer/consumer contract; its face pipeline additionally
        # attaches the optional occluder mask, already handled by RealtimeFacePipeline.
        return super()._preprocess_thread()
