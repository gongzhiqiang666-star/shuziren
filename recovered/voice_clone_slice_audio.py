"""Recovered silence slicer used by the local voice-clone workflow."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import List, Union

import numpy as np


def get_rms(y, frame_length=2048, hop_length=512, pad_mode="constant"):
    samples = np.asarray(y, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    padding = frame_length // 2
    samples = np.pad(samples, (padding, padding), mode=pad_mode)
    count = max(1, 1 + (len(samples) - frame_length) // hop_length)
    frames = np.lib.stride_tricks.as_strided(
        samples, shape=(count, frame_length),
        strides=(samples.strides[0] * hop_length, samples.strides[0]),
    )
    return np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)


def _read_wav(path: Path):
    with wave.open(str(path), "rb") as stream:
        channels, width, rate, frames = (
            stream.getnchannels(), stream.getsampwidth(),
            stream.getframerate(), stream.getnframes(),
        )
        raw = stream.readframes(frames)
    if width == 1:
        data = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 4:
        data = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    else:
        raise ValueError(f"不支持的 WAV 位深: {width * 8}")
    return data.reshape(-1, channels), rate


def _write_wav(path: Path, audio: np.ndarray, rate: int):
    pcm = np.clip(audio, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(pcm.shape[1])
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm.tobytes())


def slice_audio(
    input_path: Union[str, Path], output_dir: Union[str, Path], threshold=-34,
    min_length=4000, min_interval=300, hop_size=10, max_sil_kept=500,
    max_amplitude=0.9, alpha=0.25,
) -> List[str]:
    source, destination = Path(input_path), Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    audio, rate = _read_wav(source)
    mono = audio.mean(axis=1)
    hop = max(1, round(rate * hop_size / 1000))
    rms = get_rms(mono, frame_length=min(2048, max(32, len(mono))), hop_length=hop)
    silent = rms < 10 ** (threshold / 20)
    minimum_silence = max(1, round(min_interval / hop_size))
    keep = max(0, round(max_sil_kept / hop_size))
    cuts, begin = [], None
    for index, is_silent in enumerate(np.r_[silent, False]):
        if is_silent and begin is None:
            begin = index
        elif not is_silent and begin is not None:
            if index - begin >= minimum_silence:
                cuts.append((begin, index))
            begin = None
    boundaries = [0]
    for silence_start, silence_end in cuts:
        cut = ((silence_start + silence_end) // 2) * hop
        left = max(silence_start * hop, cut - keep * hop)
        right = min(silence_end * hop, cut + keep * hop)
        if left - boundaries[-1] >= min_length * rate / 1000:
            boundaries.extend((left, right))
    boundaries.append(len(audio))
    output_files = []
    for start, end in zip(boundaries[::2], boundaries[1::2]):
        chunk = audio[int(start):int(end)]
        if not len(chunk):
            continue
        peak = float(np.max(np.abs(chunk)))
        if peak > 0:
            chunk = chunk * (max_amplitude / peak * alpha + 1 - alpha)
        output = destination / f"{source.stem}_{len(output_files):04d}.wav"
        _write_wav(output, chunk, rate)
        output_files.append(str(output))
    print(f"Sliced into {len(output_files)} files")
    return output_files
