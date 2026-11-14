"""Recovered title/tag JSON generator."""

from __future__ import annotations

import json
import re

from .llm_base_chat import base_chat
from .content_grounding import validate_grounded_claims


def generate_title_and_tags(script: str, video_url: str = "") -> dict:
    sys_prompt = ('根据视频口播稿生成一个简洁标题和相关标签。只输出 JSON：'
                  '{"title":"标题","tags":["标签1","标签2"]}。')
    question = str(script) + (f"\n视频地址：{video_url}" if video_url else "")
    response_str = base_chat(question, sys_prompt, model_type="title", raise_on_failure=True)
    try:
        json_match = re.search(r"\{[\s\S]*\}", response_str)
        result = json.loads(json_match.group(0) if json_match else response_str)
        if not isinstance(result, dict):
            raise RuntimeError("LLM 标题结果必须是 JSON 对象")
        raw_title = result.get("title")
        if not isinstance(raw_title, str):
            raise RuntimeError("LLM 标题字段必须是文本")
        title = raw_title.strip()
        tags = result.get("tags") or []
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise RuntimeError("LLM 标签字段必须是文本数组")
    except (json.JSONDecodeError, AttributeError):
        title_match = re.search(r'["\']title["\']\s*:\s*["\'](.*?)["\']', response_str)
        tags_match = re.search(r'["\']tags["\']\s*:\s*\[(.*?)\]', response_str,
                               re.DOTALL | re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else response_str.strip()
        tags = []
        if tags_match:
            tags_str = tags_match.group(1)
            tags = [item.strip().replace('"', '').replace("'", '')
                    for item in tags_str.split(',') if item.strip()]
    if not title: raise RuntimeError("LLM 未生成标题")
    normalized_tags = []
    for tag in tags:
        value = str(tag).lstrip("#").strip()
        if value and value not in normalized_tags:
            normalized_tags.append(value)
    validate_grounded_claims(script, "\n".join([title] + normalized_tags), label="标题或标签")
    return {"title": title, "tags": normalized_tags}
