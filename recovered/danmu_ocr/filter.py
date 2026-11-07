"""Message construction recovered from the OCR DanmuFilter."""

from __future__ import annotations

import re

from collections.abc import Callable, Mapping, Sequence

CHINESE_KEYWORDS = {
    "enter": ("来了", "加入直播间"),
    "gift": ("送出了",),
    "follow": ("关注了你",),
    "share": ("分享了本次直播", "分享了直播"),
    "like": ("为主播点赞了", "点亮爱心"),
}


VIETNAM_KEYWORDS = {
    "enter": ("đã tham gia", "tham gia", "joined", "join"),
    "gift": ("đã tặng", "tặng", "sent a gift", "gift"),
    "follow": ("theo dõi", "followed", "follow"),
    "share": ("chia sẻ", "shared the live", "shared live", "shared"),
    "like": ("thích", "liked", "like"),
}


def step4_clean_user_content(username: str, content: str) -> tuple[str, str]:
    chinese_name = "".join(char for char in username if "\u4e00" <= char <= "\u9fff")
    cleaned_content = "".join(
        char for char in content
        if "\u4e00" <= char <= "\u9fff" or char.isalpha() or char.isdigit()
    )
    return (chinese_name or username).strip(), cleaned_content.strip()


def clean_and_build_message(
    username: str,
    content: str,
    msg_type: str = "danmu",
    *,
    clean_user_content: Callable[[str, str], tuple[str, str]] = step4_clean_user_content,
) -> dict[str, str]:
    cleaned_username, cleaned_content = clean_user_content(username, content)
    if not cleaned_username or not cleaned_content:
        return {}

    return {
        "type": msg_type,
        "username": cleaned_username,
        "content": cleaned_content,
        "raw_text": f"{username}:{content}",
    }


def step1_is_valid_text(text: object, keywords: Mapping[str, Sequence[str]]) -> bool:
    if not isinstance(text, str) or not text:
        return False
    if ":" in text or "：" in text:
        return True
    return any(keyword in text for group in keywords.values() for keyword in group)


def step2_get_message_type(text: str, keywords: Mapping[str, Sequence[str]]) -> str:
    for message_type, group in keywords.items():
        if any(keyword in text for keyword in group):
            return message_type
    if ":" in text or "：" in text:
        return "danmu"
    return ""


def extract_danmu_fields(text: str) -> tuple[str, str]:
    username, separator, content = text.replace("：", ":").partition(":")
    if not separator:
        return "", ""
    return username.strip(), content.strip()


def step3_extract_user_content(
    text: str, msg_type: str, keywords: Mapping[str, Sequence[str]]
) -> tuple[str, str]:
    if msg_type == "danmu":
        return extract_danmu_fields(text)
    for keyword in keywords.get(msg_type, ()):
        if keyword in text:
            username = text.replace(keyword, "").replace(":", "").replace("：", "")
            return username.strip(), keyword
    return "", ""


def process_message(
    text: str,
    keywords: Mapping[str, Sequence[str]] | None = None,
    *,
    vietnam_pack: bool = False,
) -> dict[str, str]:
    if keywords is None:
        keywords = VIETNAM_KEYWORDS if vietnam_pack else CHINESE_KEYWORDS
    if not step1_is_valid_text(text, keywords):
        return {}

    msg_type = step2_get_message_type(text, keywords)
    username, content = step3_extract_user_content(text, msg_type, keywords)
    message = clean_and_build_message(username, content, msg_type)
    if message:
        message["raw_text"] = text
    return message


_WEWORK_TIME = r"(\d{1,2}\s*[:：]\s*\d{2}\s*[:：]\s*\d{2})"
_WEWORK_HEADERS = (
    re.compile(r"^(.{1,40})\s*[@＠]\s*([\u4e00-\u9fa5A-Za-z0-9_]+)\s*" + _WEWORK_TIME),
    re.compile(r"^(.{1,40})\s*[@＠]\s*(\S+)\s*" + _WEWORK_TIME),
)


_FACEBOOK_ACTION_LABELS = {"like", "reply", "pin"}
_FACEBOOK_RELATIVE_TIME = re.compile(r"^\d+[smhdw]$")
_FACEBOOK_ACTION_ROW = re.compile(
    r"(?:\d+\s*[smhdw]\s+)?like(?:\s*[/·]\s*|\s+)reply"
    r"(?:(?:\s*[/·]\s*|\s+)pin)?"
)


class DanmuFilter:
    def __init__(self, vietnam_pack: bool = False):
        self.vietnam_pack = vietnam_pack
        words = VIETNAM_KEYWORDS if vietnam_pack else CHINESE_KEYWORDS
        self.keywords = {kind: list(group) for kind, group in words.items()}

    def process_message(self, text: str) -> dict[str, str]:
        return process_message(text, self.keywords)

    def step1_is_valid_text(self, text: str) -> bool:
        return step1_is_valid_text(text, self.keywords)

    def step2_get_message_type(self, text: str) -> str:
        return step2_get_message_type(text, self.keywords)

    def step3_extract_user_content(self, text: str, msg_type: str) -> tuple[str, str]:
        return step3_extract_user_content(text, msg_type, self.keywords)

    def step4_clean_user_content(self, username: str, content: str) -> tuple[str, str]:
        return step4_clean_user_content(username, content)

    def clean_and_build_message(
        self, username: str, content: str, msg_type: str = "danmu"
    ) -> dict[str, str]:
        return clean_and_build_message(
            username, content, msg_type,
            clean_user_content=self.step4_clean_user_content,
        )

    def try_parse_facebook_comments(self, texts: Sequence[str]) -> list[dict[str, str]]:
        results = []
        pending = []
        for text in texts:
            text = text.strip()
            if not text:
                continue
            lowered = text.casefold()
            if lowered in {"comments", "all comments", "top comments",
                           "expand comments", "write a comment"}:
                pending.clear()
                continue
            is_action_row = (
                lowered in _FACEBOOK_ACTION_LABELS
                or _FACEBOOK_RELATIVE_TIME.fullmatch(lowered)
                or _FACEBOOK_ACTION_ROW.fullmatch(lowered)
            )
            if is_action_row:
                if len(pending) >= 2:
                    message = clean_and_build_message(pending[0], " ".join(pending[1:]))
                    if message:
                        results.append(message)
                pending.clear()
                continue
            pending.append(text)
        return results

    def parse_wework_header(self, text: str):
        text = text.replace("\r", "").replace("\n", " ").strip()
        for pattern in _WEWORK_HEADERS:
            match = pattern.match(text)
            if match:
                return tuple(part.strip() for part in match.groups())
        return None

    def process_shopee_message(self, text: str) -> dict[str, str]:
        text = text.replace("\r", "").replace("\n", " ").strip()
        if not text:
            return {}
        lowered = text.lower()
        if "join" in lowered or "tham gia" in lowered:
            return parse_shopee_join(text, self.vietnam_pack)
        return {
            "type": "danmu",
            "username": "Người dùng" if self.vietnam_pack else "用户",
            "content": text,
            "raw_text": text,
        }


def parse_shopee_join(text: str, vietnam_pack: bool = False) -> dict[str, str]:
    username = re.split(r"join|tham gia", text, maxsplit=1, flags=re.IGNORECASE)[0]
    username = username.strip().strip(" :：-—|·,，")
    if not username:
        return {}
    return {
        "type": "enter",
        "username": username,
        "content": "đã tham gia phòng live" if vietnam_pack else "进入了直播间",
        "raw_text": text,
    }
