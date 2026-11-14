"""Validated audio replacement plan for the recorded-interaction candidate."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Replacement:
    start_ms: int
    end_ms: int
    reply_audio: str
    source_id: str


def validate_replacements(items, *, duration_ms, max_items=100):
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 1:
        raise ValueError("positive integer duration required")
    if not isinstance(items, (list, tuple)) or len(items) > max_items:
        raise ValueError("replacement count exceeds limit")
    result = []
    previous_end = 0
    seen = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("replacement must be an object")
        if set(raw) != {"start_ms", "end_ms", "reply_audio", "source_id"}:
            raise ValueError("replacement fields are invalid")
        start, end = raw["start_ms"], raw["end_ms"]
        if any(not isinstance(value, int) or isinstance(value, bool) for value in (start, end)):
            raise ValueError("replacement times must be integers")
        if start < previous_end or end <= start or end > duration_ms:
            raise ValueError("replacement intervals overlap or exceed media")
        source_id = str(raw["source_id"] or "").strip()
        if not source_id or source_id in seen:
            raise ValueError("replacement source identity is missing or duplicated")
        supplied = Path(str(raw["reply_audio"] or ""))
        if supplied.is_symlink():
            raise ValueError("replacement audio is not a regular file")
        path = supplied.resolve()
        if not path.is_file():
            raise ValueError("replacement audio is not a regular file")
        result.append(Replacement(start, end, str(path), source_id))
        previous_end = end
        seen.add(source_id)
    return result


def mix_replacements(original_audio, replacements):
    """Silence approved intervals and overlay replies without shifting the source."""
    from pydub import AudioSegment

    output = original_audio
    for item in replacements:
        with Path(item.reply_audio).open("rb") as source:
            reply = AudioSegment.from_file(source, format="wav")
        budget = item.end_ms - item.start_ms
        if len(reply) > budget:
            raise ValueError(f"reply audio exceeds approved interval: {item.source_id}")
        silence = AudioSegment.silent(duration=budget, frame_rate=output.frame_rate)
        silence = silence.set_channels(output.channels).set_sample_width(output.sample_width)
        output = output[:item.start_ms] + silence + output[item.end_ms:]
        output = output.overlay(reply, position=item.start_ms)
    return output
