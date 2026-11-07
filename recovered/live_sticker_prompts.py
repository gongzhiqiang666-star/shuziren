"""Recovered prompt construction and room-title parsing."""

from __future__ import annotations

import json
import re


ROOM_TITLE_SYSTEM_PROMPT = (
    "你是淘宝直播间标题助手。根据商品信息生成可直接复制的直播间标题。硬性要求："
    "1. 只输出 JSON 数组，包含恰好 3 条中文标题字符串，不要解释。"
    "2. 每条控制在 8～16 个汉字（可含少量数字），优先约 12 字内说清亮点。"
    "3. 突出品类 + 核心利益点，语气像直播开播标题。"
    "4. 与商品真实信息一致，不编造证书，不写绝对化用语。"
    "5. 不写外链、不写联系方式、不用过多标点。"
)

BACKGROUND_PREFIX = "电商竖屏直播间背景场景图，9:16手机竖屏。商品气质："
BACKGROUND_SUFFIX = "。围绕气质自由设计干净有氛围的直播底层场景，中央主播站位保持开阔干净的平面空间。无人物、无人影、无假人、无商品实物堆砌、无任何文字、无logo、无价格、无促销贴片、无角标、无棋盘格。整体可直接当直播底层场景底图。"
FOREGROUND_PREFIX = "电商竖屏直播间前景贴片层，非贴片区域为均匀纯绿#00FF00绿幕，便于色键抠图。商品气质："
FOREGROUND_SUFFIX = "。以视觉装饰为主、文字为辅，自由设计前景贴片：顶部栏贴齐最上边，底部栏贴齐最下边，左右两侧都要有贴片，中间大块纯绿留给主播站位。左右贴片都要有，体量轻，不要做成等宽等高的对称对联。文字极少，可用品牌名或两三个短词点题；严禁价格、折扣、原价现价、¥符号、占位价、下单按钮长文案、福利条目列表、大段说明文字。贴片本体不要使用纯绿或近绿色填充。整体可绿色色键抠图，中文清晰可读。"
COVER_PREFIX = "淘宝直播间封面图，正方形1:1构图，适合电商直播列表缩略展示。商品气质："
COVER_SUFFIX = "。根据商品气质设计一张干净、明亮、主体突出的商品主视觉封面：商品本体居中或居中略偏上，背景简洁有品类氛围但不抢主体，画面完整、层次少、适合缩小后仍能看清商品。无文字、无数字、无价格、无促销角标、无logo、无边框、无拼接拼图、无人物、无人脸、无假人模特、无二维码、无棋盘格、无播放按钮、无大面积纯黑。整体可直接作为淘宝直播间封面上传使用。"


_SPAM_TOKENS = (
    "券后价", "直播间专属", "限时秒杀", "正品保障", "正品", "全国联保",
    "包邮", "七天无理由", "秒杀", "官方正品", "假一赔十", "到手价", "政府补贴",
    "支持花呗", "旗舰店", "官方旗舰", "以旧换新", "爆款价",
)


def _clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _strip_spam(text: str) -> str:
    cleaned = _clean_space(text)
    for token in _SPAM_TOKENS:
        cleaned = cleaned.replace(token, "")
    cleaned = re.sub(r"[!！?？~～]+", "", cleaned)
    cleaned = re.sub(r"[【】\[\]（）()]", "", cleaned)
    return _clean_space(cleaned)


def _clip(text: str, limit: int) -> str:
    cleaned = _clean_space(text)
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip("，,、/|- ")


def build_product_vibe(product):
    name = _strip_spam(str(product.get("product_name") or product.get("itemName") or ""))
    points = _strip_spam(str(product.get("product_selling_points") or ""))
    content = _strip_spam(str(product.get("product_content") or product.get("content") or ""))
    parts = []
    if name:
        parts.append(_clip(name, 28))
    if points:
        chunks = [_clean_space(item) for item in re.split(r"[，,、/;；|\n]+", points)]
        cleaned = [item for item in chunks if item and item not in parts][:2]
        if cleaned:
            parts.append("、".join(cleaned))
    if content and content != points:
        parts.append(_clip(content, 18))
    return "，".join(parts) if parts else ""


def build_product_line(product):
    return build_product_vibe(product)


def build_product_brief(product):
    lines = []
    for label, keys in (
        ("商品名称：", ("product_name", "name")),
        ("卖点：", ("product_selling_points", "selling_points")),
        ("价格：", ("product_price", "price")),
        ("补充信息：", ("product_content", "description")),
    ):
        value = next((product.get(key) for key in keys if product.get(key)), None)
        if value:
            lines.append(label + _clean_space(value))
    return "\n".join(lines) if lines else "未提供商品信息"


def build_background_prompt(product):
    return BACKGROUND_PREFIX + build_product_vibe(product) + BACKGROUND_SUFFIX


def build_foreground_prompt(product):
    return FOREGROUND_PREFIX + build_product_vibe(product) + FOREGROUND_SUFFIX


def build_cover_prompt(product):
    return COVER_PREFIX + build_product_vibe(product) + COVER_SUFFIX


def build_room_title_user_prompt(product):
    return "商品信息：\n" + build_product_brief(product)


def parse_room_titles(content: str):
    text = re.sub(r"```(?:json|text)?|```", "", str(content or ""), flags=re.I)
    try:
        value = json.loads(text); items = value.get("titles", []) if isinstance(value, dict) else value
    except Exception:
        items = re.split(r"[\r\n]+", text)
    output = []
    for item in items or []:
        title = re.sub(r"^\s*(?:[-*•]|\d+[.)、])\s*", "", str(item)).strip(" \"'，,")
        if title and title not in output: output.append(_clip(title, 30))
    if not output:
        raise ValueError("标题解析结果为空")
    return output


def build_prompt_pair(product):
    return {"background_prompt": build_background_prompt(product),
            "foreground_prompt": build_foreground_prompt(product),
            "cover_prompt": build_cover_prompt(product)}
