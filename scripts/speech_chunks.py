"""Lossless PCM boundaries for long TTS snapshots; no feature or playback claim."""
from dataclasses import dataclass
import hashlib
import io
import wave
from pathlib import Path


@dataclass(frozen=True)
class SpeechChunk:
    audio:bytes
    source_sha256:str
    start_sample:int
    samples:int
    total_samples:int
    original_pcm_sha256:str


def _iter_chunks(source,source_hash,max_samples):
    with source:
        if not isinstance(max_samples,int) or isinstance(max_samples,bool) or max_samples<1:
            raise ValueError('Positive integer sample budget required')
        if (source.getnchannels(),source.getsampwidth(),source.getframerate(),source.getcomptype())!=(1,2,24000,'NONE'):
            raise ValueError('Expected 24kHz mono PCM16 WAV')
        total=source.getnframes()
        if not total:raise ValueError('Empty WAV')
        # Validate the entire snapshot before yielding any playable segment.
        # The validation scan uses small blocks rather than a full PCM copy.
        found=0;pcm_hash=hashlib.sha256()
        while found<total:
            block=source.readframes(min(24000,total-found))
            if not block or len(block)%2:raise ValueError('Truncated WAV')
            pcm_hash.update(block)
            found+=len(block)//2
        source.rewind()
        for start in range(0,total,max_samples):
            pcm=source.readframes(min(max_samples,total-start));stream=io.BytesIO()
            with wave.open(stream,'wb') as writer:
                writer.setparams((1,2,24000,0,'NONE','not compressed'));writer.writeframes(pcm)
            yield SpeechChunk(stream.getvalue(),source_hash,start,len(pcm)//2,total,pcm_hash.hexdigest())


def iter_wav_chunks(audio,max_samples=720000):
    if not isinstance(audio,(bytes,bytearray,memoryview)):raise ValueError('WAV bytes required')
    audio=bytes(audio)
    yield from _iter_chunks(wave.open(io.BytesIO(audio),'rb'),hashlib.sha256(audio).hexdigest(),max_samples)


def iter_wav_file_chunks(path,max_samples=720000):
    """Read one owned immutable snapshot with bounded block and chunk memory."""
    with Path(path).open('rb') as stream:
        value=hashlib.sha256()
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    yield from _iter_chunks(wave.open(str(path),'rb'),value.hexdigest(),max_samples)
