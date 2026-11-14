"""Recovered multilingual structured livestream-script generator."""

from __future__ import annotations

import json
import re
import time

from .language_prompts import (DEFAULT_LANGUAGE_CODE, extract_language_code,
                               get_language_template, language_forbids_han,
                               normalize_language_code, strip_language_marker)
from .llm_base_chat import base_chat


_HAN_TEXT_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")
_CURRENCY_RE = re.compile(r"(?:[¥￥$€£]|元|块钱|美元|欧元|英镑)", re.I)
_SCRIPT_RETRY_BASE_SECONDS = .5


def _contains_han_text(text: str) -> bool:
    return bool(_HAN_TEXT_RE.search(str(text or "")))


def _count_script_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _validate_grounded_claims(product_info, script):
    source = (json.dumps(product_info, ensure_ascii=False, sort_keys=True)
              if not isinstance(product_info, str) else product_info)
    source_numbers = set(_NUMBER_RE.findall(source))
    invented_numbers = sorted(set(_NUMBER_RE.findall(str(script))) - source_numbers)
    if invented_numbers:
        raise RuntimeError("生成的话术包含商品资料中不存在的数字: " + ", ".join(invented_numbers))
    if not _CURRENCY_RE.search(source) and _CURRENCY_RE.search(str(script)):
        raise RuntimeError("生成的话术包含商品资料中不存在的价格")


def _postprocess_script(full_script: str, language_code: str) -> str:
    text = str(full_script or "").strip()
    text = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", text, flags=re.I)
    text = re.sub(r"(?m)^\s*(?:#{1,6}|[-*]\s+)\s*", "", text)
    text = re.sub(r"(?m)^\s*(?:脚本|直播话术|Script)\s*[:：]\s*", "", text, flags=re.I)
    return _filter_han_for_language(text.strip(), language_code)


def _filter_han_for_language(text: str, language_code: str) -> str:
    if not language_forbids_han(language_code): return text
    lines = [line for line in str(text).splitlines() if not _contains_han_text(line)]
    return "\n".join(lines).strip()


def _is_multilingual_mode(language_code: str) -> bool:
    return normalize_language_code(language_code) != DEFAULT_LANGUAGE_CODE


def _language_rules(language_code: str) -> str:
    template = get_language_template(language_code)
    base = f"Write only in {template['name']}. {template['translation_prompt']}"
    if language_forbids_han(language_code):
        base += " Do not output Chinese/Han characters, bilingual text, explanations, notes, or prefixes."
    return base


def _language_name(language_code: str) -> str:
    return get_language_template(language_code)["name"]


def _build_script_prompts(product_info, special_instructions=""):
    language_code = extract_language_code(special_instructions)
    extra = strip_language_marker(special_instructions)
    product_text = json.dumps(product_info, ensure_ascii=False, indent=2) if not isinstance(product_info, str) else product_info
    sys_prompt = ("You are a professional livestream script editor. Prefer short spoken sentences and natural "
                  "talk connectors; avoid polished essay-like wording. The output goes directly to text-to-speech.\n"
                  f"Strict output language rules: {_language_rules(language_code)}")
    prompt = (f"Create a complete livestream selling script from this product information:\n{product_text}\n"
              "Include an opening hook, product benefits grounded only in the supplied facts, interaction prompts, "
              "offer explanation, and a natural closing.")
    if extra: prompt += f"\nAdditional instructions (target language always has priority):\n{extra}"
    return prompt, sys_prompt, language_code


def _retry_without_han(product_info, special_instructions, invalid_script):
    return _retry_without_han_configured(product_info, special_instructions, invalid_script)


def _retry_without_han_configured(product_info, special_instructions, invalid_script, *, llm_config=None):
    prompt, sys_prompt, language_code = _build_script_prompts(product_info, special_instructions)
    retry_prompt = (prompt + "\nThe previous livestream script contains forbidden Chinese/Han characters or CJK "
                    "punctuation. Rewrite it entirely in the target language. Previous invalid script:\n" + invalid_script)
    options = {} if llm_config is None else {"llm_config": llm_config}
    return base_chat(retry_prompt, sys_prompt, model_type="script", raise_on_failure=True, **options)


def generate_structured_speech(product_info, special_instructions=""):
    return generate_structured_speech_with_config(product_info, special_instructions)


def generate_structured_speech_with_config(product_info, special_instructions="", *, llm_config=None):
    prompt, sys_prompt, language_code = _build_script_prompts(product_info, special_instructions)
    last_error = None
    for attempt in range(2):
        try:
            options = {} if llm_config is None else {"llm_config": llm_config}
            full_script = base_chat(prompt, sys_prompt, model_type="script", raise_on_failure=True, **options)
            if language_forbids_han(language_code) and _contains_han_text(full_script):
                time.sleep(_SCRIPT_RETRY_BASE_SECONDS * (attempt + 1))
                if llm_config is None:
                    full_script = _retry_without_han(product_info, special_instructions, full_script)
                else:
                    full_script = _retry_without_han_configured(product_info, special_instructions, full_script, **options)
            processed = _postprocess_script(full_script, language_code)
            if not processed or _count_script_chars(processed) < 10:
                raise RuntimeError("生成的话术为空或过短")
            _validate_grounded_claims(product_info, processed)
            return processed
        except Exception as error:
            last_error = error
    raise RuntimeError(f"生成直播话术失败: {last_error}")
