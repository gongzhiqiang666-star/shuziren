"""Recovered prompt helpers for the cloud digital-human pipeline."""

from __future__ import annotations


DEFAULT_HALFBODY_GREENSCREEN_PROMPT = (
    "一张适合口播直播的数字人主播照片。年轻中国女性，职业装，站姿正面面对镜头，眼神看向镜头，"
    "表情自然亲和。构图必须是中景半身像：从头顶到腰部完整入镜，双手自然垂放或轻搭身前，能看到上半身服装和手臂，"
    "人物在画面中占比约百分之五十到六十，头顶留白，脚下到腰际，绝对不是大头特写，绝对不是只有脸和肩膀的近景。"
    "纯绿幕背景，均匀纯绿 chroma key #00FF00，背景无任何物品、灯光架、家具、窗户、文字。固定机位、无运镜、无透视夸张，"
    "竖屏 9:16，棚拍柔光，面部清晰，照片级写实。"
)


def build_avatar_prompt(user_description: str = "") -> str:
    """Build the Seedream prompt used for a green-screen half-body avatar."""
    description = str(user_description or "").strip()
    if not description:
        return DEFAULT_HALFBODY_GREENSCREEN_PROMPT
    return f"{DEFAULT_HALFBODY_GREENSCREEN_PROMPT}人物外观补充要求：{description}。"
