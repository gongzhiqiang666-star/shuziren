try:
    from ... import ip_agent_post_process as _implementation
    from ...ip_agent_post_process import *
except ImportError:
    import ip_agent_post_process as _implementation
    from ip_agent_post_process import *

globals().update({name: value for name, value in vars(_implementation).items() if not name.startswith("__")})
