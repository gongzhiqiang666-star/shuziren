"""Recovered image preparation helpers for live-room stickers."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image


STICKER_MAX_SIZE = (1600, 1600)


def _as_path(path: Union[str, Path]) -> Path:
    value = Path(path).expanduser().resolve()
    if not value.is_file(): raise FileNotFoundError(value)
    return value


def resize_cover_square(src, dst, edge: int = 750) -> Path:
    source = _as_path(src); target = Path(dst)
    with Image.open(source) as image:
        image = image.convert("RGB")
        scale = max(edge / image.width, edge / image.height)
        resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
        left, top = (resized.width - edge) // 2, (resized.height - edge) // 2
        cropped = resized.crop((left, top, left + edge, top + edge))
        target.parent.mkdir(parents=True, exist_ok=True); cropped.save(target, "PNG", optimize=True)
    return target


def compress_sticker_image(src, dst=None, max_size=STICKER_MAX_SIZE) -> Path:
    source = _as_path(src); target = Path(dst) if dst else source.with_name(source.stem + "_compressed.png")
    with Image.open(source) as image:
        image = image.convert("RGBA"); image.thumbnail(max_size, Image.Resampling.LANCZOS)
        target.parent.mkdir(parents=True, exist_ok=True); image.save(target, "PNG", optimize=True, compress_level=9)
    return target


def image_size_label(path) -> str:
    with Image.open(_as_path(path)) as image: return f"{image.width}×{image.height}"


def key_green(src, dst, min_g: int = 160, dominance: int = 35) -> Path:
    with Image.open(_as_path(src)) as image:
        data = np.asarray(image.convert("RGBA")).copy()
    mask = (data[..., 1] >= min_g) & (data[..., 1] >= data[..., 0] + dominance) & (data[..., 1] >= data[..., 2] + dominance)
    data[..., 3][mask] = 0
    target = Path(dst); target.parent.mkdir(parents=True, exist_ok=True); Image.fromarray(data).save(target, "PNG")
    return target


def key_white(src, dst, threshold: int = 245) -> Path:
    with Image.open(_as_path(src)) as image:
        data = np.asarray(image.convert("RGBA")).copy()
    mask = np.all(data[..., :3] >= threshold, axis=-1); data[..., 3][mask] = 0
    target = Path(dst); target.parent.mkdir(parents=True, exist_ok=True); Image.fromarray(data).save(target, "PNG")
    return target
