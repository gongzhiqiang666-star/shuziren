"""Recovered context-aware forbidden-word replacement functions."""

from __future__ import annotations

import random
import re

import jieba

from .forbidden_words import FORBIDDEN_WORDS


_SAFE_PHRASES = ("最近", "最终")
_SAFE_FROM_ZUI_REGEX = _SAFE_PHRASES


def _protect_phrases(text, phrases):
    slots = []
    result = str(text)
    for phrase in phrases:
        if phrase in result:
            index = len(slots)
            slot = f"\x00SAFE{index}\x00"
            result = result.replace(phrase, slot)
            slots.append(phrase)
    return result, slots


def _restore_phrases(text, slots):
    result = text
    for index, phrase in enumerate(slots):
        result = result.replace(f"\x00SAFE{index}\x00", phrase)
    return result


def _remove_superlative_patterns(text):
    text = re.sub(r"最[\u4e00-\u9fff]{1,3}", "", text)
    return re.sub(r"全网最[\u4e00-\u9fff]*", "", text)


def _pick_replacement(info):
    replacements = info.get("replacements") or [""]
    return random.choice(replacements)


def _replace_literal(text, word, replacement):
    flags = re.IGNORECASE if re.search(r"[A-Za-z]", word) else 0
    return re.sub(re.escape(word), lambda _match: replacement, text, flags=flags)


def replace_forbidden_words(text, additional_words=None):
    jieba.initialize()
    result = str(text or "")
    forbidden_words_dict = {item["word"]: item for item in FORBIDDEN_WORDS}
    for raw_word in additional_words or []:
        word = str(raw_word or "").strip()
        if word and word not in forbidden_words_dict:
            replacement = "*" * len(word)
            forbidden_words_dict[word] = {
                "replacements": [replacement],
                "level": "medium",
            }
    for word in forbidden_words_dict:
        if word:
            jieba.add_word(word)
    protected, safe_slots = _protect_phrases(result, _SAFE_PHRASES)
    multi_words = sorted(
        (word for word in forbidden_words_dict.keys() if len(word) >= 2),
        key=len,
        reverse=True,
    )
    for word in multi_words:
        protected = _replace_literal(
            protected, word, _pick_replacement(forbidden_words_dict[word])
        )
    protected = _remove_superlative_patterns(protected)
    for word, info in forbidden_words_dict.items():
        if len(word) == 1 and word.startswith("最") and word in protected:
            replacement = _pick_replacement(info)
            if replacement != word:
                protected = protected.replace(word, replacement)
    words = list(jieba.cut(protected))
    result = []
    for token in words:
        if token in forbidden_words_dict and len(token) >= 2:
            result.append(_pick_replacement(forbidden_words_dict[token]))
        else:
            result.append(token)
    return _restore_phrases("".join(result), safe_slots)


def test_replacement():
    test_text = "这是全网最低价，也是史上最好的产品"
    return {"original": test_text, "processed": replace_forbidden_words(test_text)}
