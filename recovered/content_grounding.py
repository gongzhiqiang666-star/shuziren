"""Deterministic checks for numeric and price claims in generated copy."""

import json
import re


NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")
CURRENCY_RE = re.compile(r"(?:[¥￥$€£]|元|块钱|美元|欧元|英镑)", re.I)


def source_text(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True)
            if not isinstance(value, str) else value)


def validate_grounded_claims(source, generated, *, label="生成内容"):
    source = source_text(source)
    generated = str(generated or "")
    source_numbers = set(NUMBER_RE.findall(source))
    invented_numbers = sorted(set(NUMBER_RE.findall(generated)) - source_numbers)
    if invented_numbers:
        raise RuntimeError(f"{label}包含输入资料中不存在的数字: " + ", ".join(invented_numbers))
    if not CURRENCY_RE.search(source) and CURRENCY_RE.search(generated):
        raise RuntimeError(f"{label}包含输入资料中不存在的价格")
