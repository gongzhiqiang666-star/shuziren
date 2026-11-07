from recovered import auto_live_action as _implementation
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
