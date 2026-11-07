"""Recovered title/tag JSON generator."""

from __future__ import annotations

import json
import re

from .llm_base_chat import base_chat


def generate_title_and_tags(script: str, video_url: str = "") -> dict:
    sys_prompt = ('根据视频口播稿生成一个简洁标题和相关标签。只输出 JSON：'
                  '{"title":"标题","tags":["标签1","标签2"]}。')
    question = str(script) + (f"\n视频地址：{video_url}" if video_url else "")
    response_str = base_chat(question, sys_prompt, model_type="title", raise_on_failure=True)
    try:
        json_match = re.search(r"\{[\s\S]*\}", response_str)
        result = json.loads(json_match.group(0) if json_match else response_str)
        title = str(result.get("title") or "").strip()
        tags = result.get("tags") or []
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
    return {"title": title, "tags": [str(tag).lstrip("#").strip() for tag in tags if str(tag).strip()]}
