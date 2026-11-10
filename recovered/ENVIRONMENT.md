# Recovered runtime environment

The original `yunchuang_v122` distribution embeds CPython 3.10 and two Windows
environments. Package versions in the requirement files are taken from their
actual `.dist-info` directories rather than inferred from imports.

- `requirements-core.txt`: media, browser automation, network and text runtime.
- `requirements-ai-cu118.txt`: the normal CUDA 11.8 model environment.
- `requirements-windows.txt`: audio devices, virtual camera and desktop APIs.

The bundled `env_50` uses `torch 2.8.0+cu128`, `torchaudio 2.8.0+cu128`,
`torchvision 0.23.0+cu128`, and `onnxruntime-gpu 1.19.0` for RTX 50-series
machines. Install those instead of the CU118 variants when the launcher selects
`env_50`.

FFmpeg and ffprobe are external runtime requirements. The original package puts
them under `env/ffmpeg/bin` and `env_50/ffmpeg/bin`; the recovered modules also
accept executables from `PATH`.

After installing Playwright, run `playwright install chromium`. Windows-only
integration tests still require the bundled virtual-camera DLL, WebView2,
PyAudio devices, NVIDIA drivers and the corresponding model weights.

## Recovery validation against an external original runtime

Run with the original CPython 3.10 environment and explicit UTF-8 mode on Windows:

```powershell
$runtime = 'D:\TEMP\v122-minimum-proof-ready\runtime\yunchuang_v122'
$env:PATH = "$runtime\_internal\env\ffmpeg\bin;" + $env:PATH
& "$runtime\_internal\env\python.exe" -I -X utf8 recovered/verify_recovery.py --runtime-root $runtime
```

The argument accepts a distribution root or its `_internal` directory.
`YUNCHUANG_RUNTIME_ROOT` is also supported, including under `-I` (this is an
application variable, not a Python interpreter configuration variable).
The explicit argument is preferred for reproducibility. Missing runtime
paths fail; bundled environments and macOS resource forks are excluded from the
128-module inventory. Binary symbols are read in Python, so a Unix `strings`
executable is not required. This check proves the listed contracts and imports,
not complete Windows/GPU/platform behavior compatibility.
