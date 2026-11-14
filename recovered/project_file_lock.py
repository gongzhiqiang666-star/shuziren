"""Small cross-process lock used by project read-modify-write transactions."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path


_registry_guard = threading.Lock()
_registry: dict[str, threading.RLock] = {}
_thread_state = threading.local()


def _local_lock(path: Path) -> threading.RLock:
    key = str(path)
    with _registry_guard:
        return _registry.setdefault(key, threading.RLock())


def _try_lock(stream) -> bool:
    if os.name == "nt":
        import msvcrt
        try:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(stream) -> None:
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def project_file_lock(base_directory, project_id, timeout=10.0):
    """Lock one project across processes; nested use in one thread is safe."""
    base = Path(base_directory).resolve()
    # Keep lock artifacts outside the user-visible project collection.  Several
    # legacy list APIs treat every child directory as a project, so placing a
    # ``.locks`` directory below ``base`` changes their observable behaviour.
    namespace = hashlib.sha256(str(base).encode("utf-8")).hexdigest()[:16]
    lock_root = base.parent / ".project_locks" / namespace
    lock_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(project_id).encode("utf-8")).hexdigest()
    path = (lock_root / (digest + ".lock")).resolve()
    if path.parent != lock_root:
        raise ValueError("项目锁路径无效")
    local = _local_lock(path)
    with local:
        held = getattr(_thread_state, "held", None)
        if held is None:
            held = _thread_state.held = {}
        active = held.get(str(path))
        if active is not None:
            active[1] += 1
            try:
                yield path
            finally:
                active[1] -= 1
            return
        with path.open("a+b") as stream:
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"0")
                stream.flush()
            deadline = time.monotonic() + max(0.0, float(timeout))
            while not _try_lock(stream):
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待项目文件锁超时")
                time.sleep(0.05)
            held[str(path)] = [stream, 1]
            try:
                yield path
            finally:
                held.pop(str(path), None)
                _unlock(stream)
