# Main runtime and configuration API recovery

Recovered in this pass:

- User/private configuration delegation, atomic YAML persistence and recursive
  merge support.
- Token, administrator ID, OEM branding, background image and version APIs.
- Local image/voice/pretrained model enumeration and path-safe deletion.
- Audio-directory counting and bounded cache cleanup.
- Camera enumeration, resolution probing, GPU/CUDA/VRAM reporting and RTX 50
  series recognition.
- ffprobe video dimension/FPS validation with the packaged 25 FPS rule.
- Volcengine image configuration, structured script generation, chunked LLM
  translation, stream URLs and interruption state updates.
- Distribution root and `env`/`env_50` selection, FFMPEG_HOME/PATH/DLL setup,
  startup admin ID and console-output setup.
- Generic YAML/text/subprocess/media-preview helpers used by the main API.

Verification included isolated user configuration, fake OEM/assets, safe model
deletion, real 25/30 FPS sample videos, simulated camera devices, simulated RTX
5090 `nvidia-smi`, mocked LLM calls and a real AVI-to-browser-MP4 conversion.
The full recovered source tree continues to pass `compileall`.
