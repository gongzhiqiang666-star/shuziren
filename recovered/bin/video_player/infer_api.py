from recovered import video_player as _implementation
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
