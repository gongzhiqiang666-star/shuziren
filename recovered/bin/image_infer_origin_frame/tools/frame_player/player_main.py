from recovered.frame_player_kt import *
from recovered.frame_player_kt import _apply_kt_overlay, _resolve_output_sample_rate as _shared_resolve_output_sample_rate

def _resolve_output_sample_rate(py_audio, preferred_rate):
    return _shared_resolve_output_sample_rate(py_audio, preferred_rate)
