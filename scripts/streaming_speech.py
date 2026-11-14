"""Bounded, provenance-aware PCM stream protocol for an isolated TTS prototype."""

from dataclasses import dataclass
from collections import deque
import hashlib
import threading
import time
import uuid


@dataclass(frozen=True)
class PCMChunk:
    stream_id: str
    sequence: int
    start_sample: int
    pcm: bytes
    final: bool
    cumulative_sha256: str

    @property
    def samples(self):
        return len(self.pcm) // 2


class StreamStopped(RuntimeError):
    pass


class PCMStream:
    """One 24 kHz mono PCM16 stream with bounded producer backpressure."""

    def __init__(self, *, max_chunks=4, max_chunk_samples=12000, stream_id=None):
        if not isinstance(max_chunks, int) or isinstance(max_chunks, bool) or max_chunks < 1:
            raise ValueError("max_chunks must be a positive integer")
        if not isinstance(max_chunk_samples, int) or isinstance(max_chunk_samples, bool) or max_chunk_samples < 1:
            raise ValueError("max_chunk_samples must be a positive integer")
        self.stream_id = stream_id or str(uuid.uuid4())
        self.max_chunk_samples = max_chunk_samples
        self._max_chunks = max_chunks
        self._queue = deque()
        self._condition = threading.Condition(threading.RLock())
        self._digest = hashlib.sha256()
        self._samples = 0
        self._sequence = 0
        self._final = False
        self._stopped = False
        self._error = None

    def put(self, pcm, *, final=False, timeout=None):
        pcm = bytes(pcm)
        if not pcm or len(pcm) % 2:
            raise ValueError("non-empty PCM16 bytes required")
        if len(pcm) // 2 > self.max_chunk_samples:
            raise ValueError("PCM chunk exceeds sample budget")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            if self._stopped:
                raise StreamStopped(self._error or "stream stopped")
            if self._final:
                raise StreamStopped("stream already finalized")
            while len(self._queue) >= self._max_chunks:
                if self._stopped:
                    raise StreamStopped(self._error or "stream stopped")
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("stream backpressure timeout")
                self._condition.wait(remaining)
            if self._stopped:
                raise StreamStopped(self._error or "stream stopped")
            digest = self._digest.copy()
            digest.update(pcm)
            chunk = PCMChunk(self.stream_id, self._sequence, self._samples, pcm,
                             bool(final), digest.hexdigest())
            self._queue.append(chunk)
            self._digest = digest
            self._samples += chunk.samples
            self._sequence += 1
            self._final = chunk.final
            self._condition.notify_all()
            return chunk

    def take(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not self._queue:
                if self._stopped:
                    raise StreamStopped(self._error or "stream stopped")
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("stream chunk timeout")
                self._condition.wait(remaining)
            chunk = self._queue.popleft()
            self._condition.notify_all()
            return chunk

    def stop(self, error=None):
        with self._condition:
            self._stopped = True
            self._error = str(error) if error else None
            self._queue.clear()
            self._condition.notify_all()

    def state(self):
        with self._condition:
            return {
                "stream_id": self.stream_id,
                "queued_chunks": len(self._queue),
                "samples": self._samples,
                "next_sequence": self._sequence,
                "final": self._final,
                "stopped": self._stopped,
                "error": self._error,
                "pcm_sha256": self._digest.hexdigest(),
            }


def iter_pcm_provider(provider, stream, *, stop_event=None, timeout=1.0):
    """Pump an iterable of PCM blocks; the final block is marked atomically."""
    iterator = iter(provider)
    try:
        current = next(iterator)
    except StopIteration as error:
        stream.stop("provider returned no audio")
        raise ValueError("provider returned no audio") from error
    try:
        for following in iterator:
            if stop_event is not None and stop_event.is_set():
                raise StreamStopped("stream cancelled")
            stream.put(current, timeout=timeout)
            current = following
        if stop_event is not None and stop_event.is_set():
            raise StreamStopped("stream cancelled")
        stream.put(current, final=True, timeout=timeout)
        return stream.state()
    except BaseException as error:
        stream.stop(error)
        raise
