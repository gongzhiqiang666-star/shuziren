from recovered import voice_clone_asr as _implementation
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
