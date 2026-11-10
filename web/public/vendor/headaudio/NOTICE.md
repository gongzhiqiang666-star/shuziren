# HeadAudio source attribution

Upstream: https://github.com/met4citizen/HeadAudio

Pinned revision: `c6d8af35034068b1c98dcc0fa3ec9602d711e784` (v1.0).

The files in `modules/` and `dist/model-en-mixed.bin` are vendored from that revision under the included MIT LICENSE. The source modules retain the upstream implementation; only trailing whitespace and final newlines are normalized. `avatar3d-worker.mjs` is our separate integration and runs classification before playback in a local Web Worker.

Model: 14,352 bytes; SHA256 `0358f68989b5861f9b7d18871b010fa6cbf88a53bda4954a954d8c548bbcf251`.

This upstream model is trained with English speech. The upstream README explicitly describes prediction and VAD accuracy limitations. It is an acoustic preview for testing a rig and playback, not proof of accurate Mandarin articulation. It does not contact a TTS service or generate speech. The page also supports imported, audio-bound viseme tracks for separately aligned/tested speech.
