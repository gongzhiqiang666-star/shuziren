"""Probe real Windows SAPI output against the bounded X05 PCM protocol.

This is an isolated candidate validator, not a production voice provider.  It
uses an installed Windows voice, never a reference recording or cloud API.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import wave

from scripts.streaming_speech import PCMStream, iter_pcm_provider


def powershell_command(wav_path, text, voice):
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"

    source = f"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice({literal(voice)})
$format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile({literal(wav_path)},$format)
$s.Speak({literal(text)})
$s.Dispose()
"""
    encoded = base64.b64encode(source.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def data_offset(header):
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        return None
    offset = 12
    while offset + 8 <= len(header):
        size = int.from_bytes(header[offset + 4:offset + 8], "little")
        if header[offset:offset + 4] == b"data":
            return offset + 8
        offset += 8 + size + (size % 2)
    return None


def growing_pcm(path, process, observations, deliveries, *, block_bytes=9_600):
    offset = None
    consumed = 0
    while process.poll() is None or path.exists() and path.stat().st_size > (offset or 0) + consumed:
        try:
            size = path.stat().st_size
            observations.append((time.perf_counter(), size))
            with path.open("rb") as stream:
                if offset is None:
                    offset = data_offset(stream.read(min(size, 4096)))
                    if offset is None:
                        time.sleep(0.01)
                        continue
                available = size - offset - consumed
                if available >= 2:
                    length = min(block_bytes, available - available % 2)
                    stream.seek(offset + consumed)
                    chunk = stream.read(length)
                    if chunk:
                        consumed += len(chunk)
                        deliveries.append((time.perf_counter(), len(chunk), process.poll() is None))
                        yield chunk
                        continue
        except (FileNotFoundError, PermissionError, OSError):
            pass
        time.sleep(0.01)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--voice", default="Microsoft Huihui Desktop")
    parser.add_argument("--text", default=("欢迎来到数字人直播间。我们正在验证真实增量语音输出，"
                                           "每一段音频都必须连续、有序、可以取消并且不能重复。") * 5)
    args = parser.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="shuziren-sapi-") as temporary:
        wav_path = Path(temporary) / "speech.wav"
        process = subprocess.Popen(powershell_command(wav_path, args.text, args.voice),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        observations, deliveries = [], []
        stream = PCMStream(max_chunks=4, max_chunk_samples=12_000, stream_id="windows-sapi-probe")
        failure = []

        def produce():
            try:
                iter_pcm_provider(growing_pcm(wav_path, process, observations, deliveries), stream, timeout=5)
            except BaseException as error:
                failure.append(error)

        producer = threading.Thread(target=produce, name="sapi-incremental-producer")
        producer.start()
        chunks = []
        while producer.is_alive() or stream.state()["queued_chunks"]:
            try:
                item = stream.take(timeout=.1)
            except TimeoutError:
                continue
            chunks.append(item)
            if item.final:
                break
        producer.join(10)
        stderr = process.communicate(timeout=10)[1].decode("utf-8", "replace")
        if process.returncode:
            raise RuntimeError(f"SAPI exited {process.returncode}: {stderr[-500:]}")
        if failure:
            raise failure[0]
        with wave.open(str(wav_path), "rb") as audio:
            properties = (audio.getframerate(), audio.getnchannels(), audio.getsampwidth())
            complete_pcm = audio.readframes(audio.getnframes())
        received = b"".join(item.pcm for item in chunks)
        if properties != (24000, 1, 2):
            raise RuntimeError(f"unexpected WAV properties: {properties}")
        if received != complete_pcm:
            raise RuntimeError("incremental PCM differs from finalized WAV")
        if not chunks or not chunks[-1].final:
            raise RuntimeError("stream did not publish one final chunk")
        first_growth = next((moment for moment, size in observations if size > 64), None)
        ended = time.perf_counter()
        report = {
            "result": "passed",
            "scope": "isolated Windows SAPI incremental-output probe; not a production/cloned voice",
            "voice": args.voice,
            "sample_rate": properties[0],
            "channels": properties[1],
            "sample_width": properties[2],
            "samples": len(received) // 2,
            "duration_seconds": len(received) / 2 / properties[0],
            "chunks": len(chunks),
            "first_chunk_samples": chunks[0].samples,
            "first_file_growth_seconds": None if first_growth is None else first_growth - started,
            "first_pcm_delivery_seconds": None if not deliveries else deliveries[0][0] - started,
            "pcm_deliveries_while_engine_running": sum(active for _, _, active in deliveries),
            "pcm_bytes_while_engine_running": sum(size for _, size, active in deliveries if active),
            "total_seconds": ended - started,
            "pcm_sha256": hashlib.sha256(received).hexdigest(),
            "contiguous_sequences": [item.sequence for item in chunks] == list(range(len(chunks))),
            "contiguous_samples": all(item.start_sample == sum(previous.samples for previous in chunks[:index])
                                      for index, item in enumerate(chunks)),
            "final_chunks": sum(item.final for item in chunks),
            "file_observations": len(observations),
        }
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
