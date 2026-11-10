"""Process-local acceleration for the authorized v122 Windows runtime.

No models or vendor modules are modified. Use before loading v122 modules;
keep the context active until inference workers have stopped.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def windows_timer_precision():
    """Request 1ms Windows scheduling for paced output, then release it."""
    timer = None
    if sys.platform == "win32":
        import ctypes
        timer = ctypes.WinDLL("winmm")
        if timer.timeBeginPeriod(1) != 0:
            raise RuntimeError("Cannot enable 1ms playback timer")
    try:
        yield
    finally:
        if timer is not None:
            timer.timeEndPeriod(1)


def configure_runtime(runtime_root):
    internal = Path(runtime_root).resolve() / "_internal"
    environment = internal / "env"
    directories = [
        environment / "ffmpeg/bin",
        environment / "CUDA/v11.8/bin",
        environment / "CUDA/TensorRT-8.6.1.6/lib",
        environment / "Library/bin",
        environment,
    ]
    os.environ["PATH"] = os.pathsep.join(
        [str(path) for path in directories if path.is_dir()]
        + [os.environ.get("PATH", "")]
    )
    sys.path.insert(0, str(internal))
    os.chdir(internal)
    return internal


@contextmanager
def accelerated_unet(cache_directory, backend="tensorrt", memory_gb=4, profile_directory=None):
    """Select validated providers for UNet only; fail on provider fallback.

    This patches ORT's Python constructor in this process, not installed files.
    Session creation must not run concurrently with entering/leaving this scope.
    FP16 changes numerical results; evaluate quality against the CUDA baseline.
    """
    import cv2
    import onnxruntime as ort
    import torch

    if backend not in {"cuda", "tensorrt"}:
        raise ValueError("backend must be cuda or tensorrt")
    cache = Path(cache_directory).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    cv2.setNumThreads(2)
    original = ort.InferenceSession.__init__
    sessions = []

    def initialize(session, model, *args, **kwargs):
        if not isinstance(model, (str, os.PathLike)) or not Path(model).name.startswith("unet"):
            return original(session, model, *args, **kwargs)
        if len(args) > 1:
            raise ValueError("UNet provider arguments must be passed by keyword")
        cuda = ("CUDAExecutionProvider", {
            "cudnn_conv_algo_search": "HEURISTIC",
            "gpu_mem_limit": str(int(memory_gb * 1024**3)),
            "arena_extend_strategy": "kSameAsRequested",
        })
        providers = [cuda, "CPUExecutionProvider"]
        if backend == "tensorrt":
            providers.insert(0, ("TensorrtExecutionProvider", {
                "trt_fp16_enable": "True",
                "trt_engine_cache_enable": "True",
                "trt_engine_cache_path": str(cache),
                "trt_max_workspace_size": str(2 * 1024**3),
            }))
        kwargs["providers"] = providers
        kwargs.pop("provider_options", None)
        if profile_directory is not None:
            profile = Path(profile_directory).resolve()
            profile.mkdir(parents=True, exist_ok=True)
            options = kwargs.get('sess_options') or (args[0] if args else ort.SessionOptions())
            options.enable_profiling = True
            options.profile_file_prefix = str(profile/'unet')
            if args:
                args = (options,)
            else:
                kwargs['sess_options'] = options
        original(session, model, *args, **kwargs)
        expected = providers[0][0]
        if expected not in session.get_providers():
            raise RuntimeError("Requested provider failed to load: " + expected)
        session.disable_fallback()
        sessions.append(session)

    ort.InferenceSession.__init__ = initialize
    try:
        yield sessions
    finally:
        ort.InferenceSession.__init__ = original
