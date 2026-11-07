"""Load an unobfuscated Python companion shipped beside a Cython extension."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load(relative_path: str, alias: str):
    source = Path(__file__).resolve().parent.parent / "yunchuang_v122" / "_internal" / relative_path
    spec = importlib.util.spec_from_file_location(alias, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load bundled source: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
