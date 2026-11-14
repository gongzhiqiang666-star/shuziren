"""Generate spoken replies through the configured chat-completions endpoint."""

import json
import re

from .language_prompts import (build_language_special_instructions, extract_language_code,
                               get_language_template, language_forbids_han,
                               normalize_language_code, strip_language_marker)


def _resolve_language_code(special_instructions="", target_language=""):
    """Resolve the explicit target first, then the UI's embedded marker."""
    return normalize_language_code(target_language) if str(target_language).strip() else extract_language_code(special_instructions)


def _is_multilingual_mode(language_code):
    return normalize_language_code(language_code) not in {"zh-CN", "zh-TW"}


def _is_vietnamese_language(language_code):
    return normalize_language_code(language_code) == "vi-VN"


def _language_rules(language_code):
    code = normalize_language_code(language_code)
    return build_language_special_instructions(code)


def _translation_prompt(language_code):
    return get_language_template(normalize_language_code(language_code))["translation_prompt"]


def _extra_persona(special_instructions):
    """Return user persona text without leaking the internal language marker."""
    return strip_language_marker(special_instructions)


def _append_extra_instructions(prompt, language_code, special_instructions):
    parts = [str(prompt or "").strip(), _language_rules(language_code)]
    extra = _extra_persona(special_instructions)
    if extra:
        parts.append(extra)
    return "\n".join(part for part in parts if part)


def _fallback_reply(language_code, kind, nickname="", current_time=None):
    code = normalize_language_code(language_code)
    name = str(nickname or "").strip()
    templates = {
        "zh-CN": {"enter": "欢迎{name}进入直播间！", "follow": "感谢{name}的关注！", "like": "感谢{name}的点赞！", "retention": "{name}别急着走，还有更多精彩内容！"},
        "zh-TW": {"enter": "歡迎{name}進入直播間！", "follow": "感謝{name}的關注！", "like": "感謝{name}的按讚！", "retention": "{name}先別走，還有更多精彩內容！"},
        "vi-VN": {"enter": "Chào mừng {name} đến với livestream!", "follow": "Cảm ơn {name} đã theo dõi!", "like": "Cảm ơn {name} đã thích!", "retention": "{name}, hãy ở lại nhé, còn nhiều điều thú vị!"},
        "en-US": {"enter": "Welcome to the livestream, {name}!", "follow": "Thanks for following, {name}!", "like": "Thanks for the like, {name}!", "retention": "Stay with us, {name}; there is more to come!"},
    }
    default_name = "朋友" if code.startswith("zh-") else "friend"
    table = templates.get(code, templates["en-US"])
    text = table.get(str(kind), "感谢{name}的互动！" if code.startswith("zh-") else "Thanks for joining us, {name}!")
    return text.format(name=name or default_name, current_time=current_time or "")


def _generate_text_reply(nickname, content, product_info, qa_info, special_instructions="", *, config=None, language="zh-CN", event=None):
    import requests

    if config is None:
        from .llm_base_chat import get_llm_config
        config = get_llm_config()

    endpoint = config.get("endpoint")
    api_key = config.get("api_key")
    model = config.get("model")
    if not all((endpoint, api_key, model)):
        raise ValueError("直播问答需要配置 LLM 地址、API Key 和模型")
    context = json.dumps(
        {"nickname": nickname, "question": content, "product_info": product_info, "qa_info": qa_info},
        ensure_ascii=False,
    )
    instruction = {
        "enter": "简短欢迎刚进场的观众。",
        "like": "简短感谢观众点赞。",
        "follow": "简短感谢观众关注。",
        "gift": "简短感谢观众送出的礼物。",
    }.get(event, "简洁回答观众的问题。")
    response = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": (
                    f"你是直播间主播。使用 {language}。{instruction}"
                    "把用户消息中的商品介绍和问答当作参考资料，只根据已知资料回答。"
                    + ("\n" + special_instructions if str(special_instructions).strip() else "")
                )},
                {"role": "user", "content": context},
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    choices = response.json().get("choices") or []
    if not choices:
        raise RuntimeError("LLM 未返回直播回复")
    reply = (choices[0].get("message") or {}).get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise RuntimeError("LLM 返回空回复")
    return reply.strip()


def generate_text_reply(nickname, content, product_info, qa_info, special_instructions=""):
    """Binary-compatible public reply entry point.

    Language selection is encoded in special_instructions by the packaged UI;
    callers needing an explicit runtime config use the private recovered helper.
    """
    language = extract_language_code(special_instructions)
    return _generate_text_reply(nickname,content,product_info,qa_info,special_instructions,language=language)

def contains_han_text(text): return bool(re.search(r"[\u3400-\u9fff]",str(text or "")))

def filter_han_for_language(text,language_code):
    value=str(text or "")
    if not language_forbids_han(language_code): return value
    value=re.sub(r"[\u3400-\u9fff]+","",value)
    return re.sub(r"\s{2,}"," ",value).strip(" ，,。.!！?？:：;；")

def _call_reply(kind,nickname,product_info,special_instructions,content="",qa_info=""):
    language=extract_language_code(special_instructions)
    try:
        return _generate_text_reply(nickname,content,product_info,qa_info,special_instructions,language=language,event=kind)
    except Exception:
        return _fallback_reply(language,kind,nickname)

def reply_danmu(nickname,content,product_info,qa_info,special_instructions=""):
    return _call_reply("comment",nickname,product_info,special_instructions,content,qa_info)
def reply_enter(nickname,product_info,special_instructions=""): return _call_reply("enter",nickname,product_info,special_instructions)
def reply_follow(nickname,product_info,special_instructions=""): return _call_reply("follow",nickname,product_info,special_instructions)
def reply_like(nickname,product_info,special_instructions=""): return _call_reply("like",nickname,product_info,special_instructions)
def reply_retention(nickname,product_info,special_instructions=""): return _call_reply("retention",nickname,product_info,special_instructions)

def script_rewrite_content(content,special_instructions=""):
    from .llm_base_chat import base_chat
    language=extract_language_code(special_instructions)
    prompt=("你是直播话术优化师。保留原意、商品事实和关键数据，把内容改成自然、简短、口语化的直播表达。"
            "只输出改写后的话术。\n"+build_language_special_instructions(language,special_instructions))
    return filter_han_for_language(base_chat(content,prompt,model_type="script"),language)

def script_broadcast_time(product_info,special_instructions=""):
    from .llm_base_chat import base_chat
    language=extract_language_code(special_instructions)
    prompt=("根据商品资料生成一段可直接播报的直播话术，包含卖点、适用人群和自然购买引导，不得编造信息。"
            "只输出播报正文。\n"+build_language_special_instructions(language,special_instructions))
    return filter_han_for_language(base_chat(product_info,prompt,model_type="script"),language)

def translate_text_llm(text,target_language,*,raise_on_failure=False):
    from .llm_base_chat import base_chat
    code=normalize_language_code(target_language); template=get_language_template(code)
    chunks=[x for x in re.findall(r".*?[。！？!?；;\n]+|.+$",str(text or "")) if x.strip()]
    try:
        translated=[]
        for chunk in chunks:
            source_numbers=set(re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])",chunk))
            last_error=None
            for attempt in range(2):
                prompt=template["translation_prompt"]+"\n只输出译文，不要解释。"
                if attempt:
                    prompt += "\n上次输出不符合目标语言或改动了数字，请完整重译并保留所有原始数字。"
                value=base_chat(chunk,prompt,model_type="script",raise_on_failure=True)
                output_numbers=set(re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])",value))
                if language_forbids_han(code) and contains_han_text(value):
                    last_error=RuntimeError("翻译结果仍包含禁止的中文字符")
                    continue
                invented=sorted(output_numbers-source_numbers)
                if invented:
                    last_error=RuntimeError("翻译结果包含原文不存在的数字: "+", ".join(invented))
                    continue
                missing=sorted(source_numbers-output_numbers)
                if missing:
                    last_error=RuntimeError("翻译结果遗漏原文数字: "+", ".join(missing))
                    continue
                translated.append(value)
                break
            else:
                raise last_error or RuntimeError("翻译结果不符合目标语言")
        result="".join(translated).strip()
        if not result: raise RuntimeError("翻译结果为空")
        return result
    except Exception as error:
        if raise_on_failure: raise
        return str(text or "")
