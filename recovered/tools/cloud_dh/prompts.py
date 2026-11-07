from recovered import cloud_dh_prompts as _implementation
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
