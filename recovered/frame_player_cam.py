"""Virtual camera output for recovered inference frames."""

import logging

from .frame_player_kt import FPS, StreamPlayer as WindowStreamPlayer, _apply_kt_overlay
from .frame_geometry import fit_frame_to_canvas


class StreamPlayer(WindowStreamPlayer):
    def __init__(self, window_width, window_height, device=None):
        super().__init__(window_width, window_height)
        self.player.render_loop = self._stop_event.wait
        self.window_width = window_width
        self.window_height = window_height
        self.device = device
        self._camera = None

    def _send_frame_to_virtual_cam(self, frame_info):
        import cv2
        import pyvirtualcam

        frame = frame_info.get("frame")
        if frame is None:
            return
        try:
            frame = _apply_kt_overlay(frame, frame_info.get("physical_index"))
        except Exception:
            pass
        size = (self.window_width, self.window_height)
        if frame.shape[:2] != size[::-1]:
            frame = fit_frame_to_canvas(frame, *size)
        if self._camera is None:
            self._camera = pyvirtualcam.Camera(
                width=size[0], height=size[1], fps=FPS,
                device=self.device, fmt=pyvirtualcam.PixelFormat.RGB,
            )
        self._camera.send(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    def _submit_video_frame(self, frame, physical_index):
        try:
            self._send_frame_to_virtual_cam({"frame": frame, "physical_index": physical_index})
        except (ImportError, OSError, RuntimeError):
            logging.getLogger(__name__).exception("Virtual camera output failed")
            try:
                self._close_camera()
            except (OSError, RuntimeError):
                logging.getLogger(__name__).exception("Virtual camera cleanup failed")
            return
        with self._queue_lock:
            self._output_frame_count += 1

    def _run_playback(self):
        try:
            super()._run_playback()
        finally:
            self._close_camera()

    def _close_camera(self):
        camera, self._camera = self._camera, None
        if camera is not None:
            camera.close()
