"""Text filtering helpers recovered from tools.text_processing."""

import random
import re
from datetime import datetime


_SCRIPT_OPTIONS = re.compile(r"{([^{}]*\|[^{}]*)}")
_DEFAULT_PROHIBITED_WORDS = ["哎呀", "嘿", "哎哟", "哦", "喔"]



def contains_blocked(content, blocked_keywords):
    return any(keyword and keyword in content for keyword in blocked_keywords)


def is_user_blocked(nickname, blocked_users):
    return any(blocked_user and blocked_user in nickname for blocked_user in blocked_users)


def strip_prohibited_words(text, prohibited_words):
    for word in [*(prohibited_words or ()), *_DEFAULT_PROHIBITED_WORDS]:
        if word:
            text = text.replace(word, "")
    return text


def process_script_options(text):
    return _SCRIPT_OPTIONS.sub(
        lambda match: random.choice(match.group(1).split("|")), text
    )


def parse_qa_info(qa_pairs):
    result = {}
    for pair in qa_pairs or []:
        keywords = (pair.get("question") or "").strip().split()
        answers = (pair.get("answer") or "").strip().split()
        if keywords and answers:
            for keyword in keywords:
                result[keyword] = answers
    return result


def match_keywords(content, qa_dict):
    for keyword, answers in qa_dict.items():
        if keyword in content:
            return random.choice(answers) if answers else None
    return None


def parse_qa_info_from_text(qa_info):
    pairs = []
    for block in re.split(r"\n\n", qa_info):
        match = re.match(r"问：(.*?)\n答：(.*)", block, re.DOTALL)
        if match:
            pairs.append({"question": match[1].strip(), "answer": match[2].strip()})
    return pairs


def _num_to_chinese(num):
    digits = "零一二三四五六七八九"
    if 0 <= num < 10:
        return digits[num]
    if 10 <= num < 100:
        tens, units = divmod(num, 10)
        return (digits[tens] if tens > 1 else "") + "十" + (digits[units] if units else "")
    return str(num)


def process_special_variables(text):
    current = datetime.now()
    if "{time}" in text:
        time_str = _num_to_chinese(current.hour) + "点"
        if current.minute:
            time_str += _num_to_chinese(current.minute) + "分"
        text = text.replace("{time}", time_str)
    if "{min_left}" in text:
        min_left = (60 - current.minute) % 60
        text = text.replace("{min_left}", _num_to_chinese(min_left))
    if "{next_h}" in text:
        next_hour = (current.hour + 1) % 24
        text = text.replace("{next_h}", _num_to_chinese(next_hour) + "点")
    return process_script_options(text)
