from recovered import clone_manager as _implementation
globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
