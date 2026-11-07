"""Recovered room-title generation through Ark or configured LLM."""

from __future__ import annotations

import requests

from .live_sticker_prompts import ROOM_TITLE_SYSTEM_PROMPT, build_room_title_user_prompt, parse_room_titles
from .llm_base_chat import base_chat, get_llm_config


ARK_CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
ARK_TITLE_MODEL = "doubao-seed-1-6-flash-250828"


def _chat_ark(api_key: str, product: dict, model: str = ARK_TITLE_MODEL) -> str:
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ValueError("缺少火山引擎 API Key，无法生成直播间标题")
    response = requests.post(
        ARK_CHAT_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": ROOM_TITLE_SYSTEM_PROMPT},
                {"role": "user", "content": build_room_title_user_prompt(product)},
            ],
            "temperature": 0.7,
            "thinking": {"type": "disabled"},
        },
        timeout=120,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Ark 标题生成失败 HTTP {response.status_code}: {response.text}")
    choices = response.json().get("choices") or []
    content = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
    if not content:
        raise RuntimeError("Ark 标题生成返回空内容")
    return content


def generate_room_titles(product, *, ark_api_key=""):
    errors = []
    content = None
    used_model = ""
    try:
        content = base_chat(build_room_title_user_prompt(product), ROOM_TITLE_SYSTEM_PROMPT,
                            raise_on_failure=True)
        used_model = "llm_config"
    except Exception as error:
        errors.append(f"llm_config: {error}")
    if content is None:
        try:
            content = _chat_ark(ark_api_key, product)
            used_model = f"ark: {ARK_TITLE_MODEL}"
        except Exception as error:
            errors.append(f"ark: {error}")
    if content is None:
        raise ValueError("生成直播间标题失败: " + " | ".join(errors))
    titles = parse_room_titles(content)
    return {"room_titles": titles, "room_title": titles[0], "title_model": used_model}
