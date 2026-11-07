"""Recovered language markers and strict output-language rules."""

from __future__ import annotations

import re


DEFAULT_LANGUAGE_CODE = "zh-CN"
LANGUAGE_MARKER_PREFIX = "[TARGET_LANGUAGE="
LANGUAGE_CODE_ALIASES = {
    "zh": "zh-CN", "zh-cn": "zh-CN", "cn": "zh-CN", "chinese": "zh-CN",
    "zh-tw": "zh-TW", "en": "en-US", "english": "en-US", "vi": "vi-VN",
    "vietnamese": "vi-VN", "th": "th-TH", "thai": "th-TH", "id": "id-ID",
    "indonesian": "id-ID", "ms": "ms-MY", "malay": "ms-MY", "fil": "fil-PH",
    "tl": "fil-PH", "es": "es-ES", "pt": "pt-BR", "fr": "fr-FR", "de": "de-DE",
}
SUPPORTED_LANGUAGE_CODES = frozenset(LANGUAGE_CODE_ALIASES.values())
HAN_ALLOWED_LANGUAGE_CODES = frozenset({"zh-CN", "zh-TW"})
LANGUAGE_TEMPLATE_MAP = {
    "zh-CN": {"name": "简体中文", "translation_prompt": "请使用自然的简体中文。"},
    "zh-TW": {"name": "繁體中文", "translation_prompt": "請使用自然的繁體中文。"},
    "en-US": {"name": "English", "translation_prompt": "You are a professional translator. Translate the user's input into natural English."},
    "vi-VN": {"name": "Vietnamese", "translation_prompt": "Use natural Vietnamese livestream language."},
    "th-TH": {"name": "Thai", "translation_prompt": "Use natural Thai livestream language."},
    "id-ID": {"name": "Indonesian", "translation_prompt": "Use natural Indonesian livestream language."},
    "ms-MY": {"name": "Malay", "translation_prompt": "Use natural Malay livestream language."},
    "fil-PH": {"name": "Filipino", "translation_prompt": "Isa kang propesyonal na tagasalin. Isalin ang input ng user sa natural na Filipino."},
    "es-ES": {"name": "Spanish", "translation_prompt": "Use natural Spanish livestream language."},
    "pt-BR": {"name": "Portuguese", "translation_prompt": "Use natural Brazilian Portuguese livestream language."},
    "fr-FR": {"name": "French", "translation_prompt": "Use natural French livestream language."},
    "de-DE": {"name": "German", "translation_prompt": "Use natural German livestream language."},
}


def normalize_language_code(language_code: str) -> str:
    value = str(language_code or DEFAULT_LANGUAGE_CODE).strip().replace("_", "-")
    alias_key = value.lower()
    if alias_key in LANGUAGE_CODE_ALIASES: return LANGUAGE_CODE_ALIASES[alias_key]
    for code in SUPPORTED_LANGUAGE_CODES:
        if code.lower() == alias_key: return code
    return DEFAULT_LANGUAGE_CODE


def is_chinese_language(language_code: str) -> bool:
    return normalize_language_code(language_code) in HAN_ALLOWED_LANGUAGE_CODES


def language_forbids_han(language_code: str) -> bool:
    return not is_chinese_language(language_code)


def build_no_han_output_rule(language_code: str) -> str:
    if not language_forbids_han(language_code): return ""
    return ("Output language requirement:\n- Do not output Chinese, Cantonese, pinyin, romanization, "
            "bilingual text, bracketed notes, or explanations.\n- If the input contains Chinese or another "
            "language, translate or paraphrase it completely into the target language before replying.")


def get_language_template(language_code: str) -> dict:
    return dict(LANGUAGE_TEMPLATE_MAP[normalize_language_code(language_code)])


def build_language_special_instructions(language_code: str, extra_instructions: str = "") -> str:
    code = normalize_language_code(language_code)
    parts = [f"[TARGET_LANGUAGE={code}]", get_language_template(code)["translation_prompt"]]
    rule = build_no_han_output_rule(code)
    if rule: parts.append(rule)
    if str(extra_instructions).strip(): parts.append(str(extra_instructions).strip())
    return "\n".join(parts)


def extract_language_code(special_instructions: str) -> str:
    match = re.search(r"\[TARGET_LANGUAGE=([^\]]+)\]", str(special_instructions or ""))
    return normalize_language_code(match.group(1)) if match else DEFAULT_LANGUAGE_CODE


def strip_language_marker(special_instructions: str) -> str:
    return re.sub(r"^\[TARGET_LANGUAGE=[^\]]+\]\s*", "", str(special_instructions or "")).strip()
