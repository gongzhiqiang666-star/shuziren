from recovered import record_live_manager as _implementation
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
