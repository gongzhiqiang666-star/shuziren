from recovered import win_power_throttling as _implementation
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
