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
