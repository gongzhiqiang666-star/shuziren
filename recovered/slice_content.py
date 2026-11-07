"""Recovered host/assistant/pause script slicer from ``tools.slice_content``."""

from __future__ import annotations

import re
from typing import Any


TARGET_CHARS_ZH = 25
HARD_MAX_CHARS_ZH = 40
TARGET_CHARS_EN = 80
HARD_MAX_CHARS_EN = 120
MIN_TERMINAL_CHARS = 4

TERMINAL_PUNCT = "。.!！？?；;\n"
SOFT_PUNCT = "，,、：:"
PUNCTUATION_CHARS = TERMINAL_PUNCT + SOFT_PUNCT
PUNCTUATION_PATTERN = re.compile(rf"(.+?[{re.escape(PUNCTUATION_CHARS)}]+|.+$)", re.S)
_CONTROL_PATTERN = re.compile(r"(\{助[:：][^}]*\}|\{停[:：][\d.]+\})")
_BRACKET_PATTERN = re.compile(r"(\[[^\[\]]*\])")
_CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fa5]")


def _ends_with_punct(text: str, chars: str) -> bool:
    return bool(text) and text.endswith(tuple(chars))


def _is_chinese_text(text: str) -> bool:
    return bool(_CHINESE_PATTERN.search(text or ""))


def _length_limits(text: str) -> tuple[int, int]:
    if _is_chinese_text(text):
        return TARGET_CHARS_ZH, HARD_MAX_CHARS_ZH
    return TARGET_CHARS_EN, HARD_MAX_CHARS_EN


def _join_sentence(current_text: str, sentence: str) -> str:
    current_text = current_text.strip()
    sentence = sentence.strip()
    if not current_text:
        return sentence
    if not sentence:
        return current_text
    if current_text[-1].isascii() and current_text[-1].isalnum() and sentence[0].isascii() and sentence[0].isalnum():
        return current_text + ". " + sentence
    if current_text[-1].isascii() and sentence[0].isascii():
        return current_text + " " + sentence
    return current_text + sentence


def _split_punct_units(segment: str) -> list[str]:
    segment = (segment or "").strip()
    if not segment:
        return []
    units: list[str] = []
    for bracket_part in _BRACKET_PATTERN.split(segment):
        if not bracket_part:
            continue
        if _BRACKET_PATTERN.fullmatch(bracket_part):
            units.append(bracket_part)
            continue
        units.extend(
            match.group(0).strip()
            for match in PUNCTUATION_PATTERN.finditer(bracket_part)
            if match.group(0).strip()
        )
    return units


def _append_host(result: list[dict[str, Any]], text: str) -> None:
    text = text.strip()
    if text:
        result.append({"type": "host", "content": text})


def _merge_host_units(units: list[str], result: list[dict[str, Any]]) -> None:
    current_text = ""

    def flush() -> None:
        nonlocal current_text
        _append_host(result, current_text)
        current_text = ""

    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        target, hard_max = _length_limits(current_text or unit)
        candidate = _join_sentence(current_text, unit)
        if current_text and len(candidate) > hard_max:
            flush()
            candidate = unit
        current_text = candidate
        if len(current_text) >= target and _ends_with_punct(current_text, TERMINAL_PUNCT):
            flush()
        elif (
            len(current_text) >= hard_max
            or len(current_text) >= target
            and _ends_with_punct(current_text, SOFT_PUNCT)
        ):
            flush()
    flush()


def _slice_host_content(segment: str, result: list[dict[str, Any]]) -> None:
    _merge_host_units(_split_punct_units(segment), result)


def slice_content(inp: str) -> list[dict[str, Any]]:
    """Split a live script into ordered host, assistant and pause instructions."""
    if not isinstance(inp, str):
        raise TypeError("inp must be str")
    result: list[dict[str, Any]] = []
    for segment in _CONTROL_PATTERN.split(inp):
        segment = segment.strip()
        if not segment:
            continue
        if segment.startswith(("{助:", "{助：")):
            text = segment[3:-1].strip()
            if text:
                result.append({"type": "assistant", "content": text})
        elif segment.startswith(("{停:", "{停：")):
            duration_str = segment[3:-1].strip()
            try:
                duration = float(duration_str)
            except ValueError:
                _slice_host_content(segment, result)
            else:
                result.append({"type": "pause", "duration": duration})
        else:
            _slice_host_content(segment, result)
    return result

