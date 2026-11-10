"""Recovered OpenAI-compatible chat-completions client."""

from __future__ import annotations

import re
from pathlib import Path

import requests
import yaml

from .main_config import resolve_user_config_path


def remove_emojis(text):
    return re.sub("[\U0001F000-\U0001FAFF\u2600-\u27BF\ufe0f]", "", str(text or "")).strip()


def _is_siliconflow_endpoint(url: str) -> bool:
    value = str(url or "").lower()
    return "siliconflow.cn" in value or "siliconflow.com" in value


def _apply_model_request_options(data: dict, model: str, url: str) -> None:
    normalized = str(model or "").lower()
    if _is_siliconflow_endpoint(url) and ("deepseek" in normalized or "deepseek-v4" in normalized):
        data["enable_thinking"] = False
    if normalized.startswith(("o1", "o3", "o4")):
        data["reasoning_effort"] = "low"


def _normalize_llm_config(llm_config):
    value = dict(llm_config or {})
    value["endpoint"] = str(value.get("endpoint") or value.get("url") or "").strip()
    value["api_key"] = str(value.get("api_key") or value.get("key") or "").strip()
    value["model"] = str(value.get("model") or value.get("model_name") or "").strip()
    return value


def get_llm_config(llm_config=None):
    if llm_config is not None:
        return _normalize_llm_config(llm_config)
    path = Path(resolve_user_config_path())
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return _normalize_llm_config(loaded.get("llm_config") or loaded)
    return _normalize_llm_config({})


def base_chat(question, sys_prompt, chat_history=[], *, model_type="reply",
              raise_on_failure=False, llm_config=None):
    try:
        config = get_llm_config(llm_config)
        if not all(config.get(key) for key in ("endpoint", "api_key", "model")):
            raise ValueError("请配置 LLM 地址、API Key 和模型")
        messages = [{"role": "system", "content": str(sys_prompt)}]
        messages.extend(dict(item) for item in (chat_history or []))
        messages.append({"role": "user", "content": str(question)})
        data = {"model": config["model"], "messages": messages, "stream": False}
        if model_type == "reply": data["temperature"] = .6
        elif model_type == "script": data.update({"temperature": .75, "max_tokens": 4096})
        elif model_type == "title": data.update({"temperature": .4, "max_tokens": 512})
        _apply_model_request_options(data, config["model"], config["endpoint"])
        request_options = {}
        if "allow_redirects" in config:
            request_options["allow_redirects"] = bool(config["allow_redirects"])
        response = requests.post(config["endpoint"], headers={"Authorization": f"Bearer {config['api_key']}",
                                 "Content-Type": "application/json"}, json=data,
                                 timeout=float(config.get("timeout", 60)), **request_options)
        response.raise_for_status()
        choices = response.json().get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") if choices else None)
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM 未返回有效内容")
        return remove_emojis(content)
    except Exception as error:
        if raise_on_failure: raise
        return f"LLM 调用失败: {error}"
