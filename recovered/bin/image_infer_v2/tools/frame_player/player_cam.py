from recovered.frame_player_cam import *
from recovered.frame_player_cam import _apply_kt_overlay
from recovered.frame_player_kt import _resolve_output_sample_rate as _shared_resolve_output_sample_rate

def _resolve_output_sample_rate(py_audio, preferred_rate):
    return _shared_resolve_output_sample_rate(py_audio, preferred_rate)
