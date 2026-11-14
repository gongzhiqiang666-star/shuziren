"""Canonical platform names shared by live capture modes."""

_PLATFORM_ALIASES = {
    "pdd": "pinduoduo",
    "shoppe": "shopee",
    "xiapi": "shopee",
    "xiaopi": "shopee",
    "wechat": "shipinhao",
    "video_account": "shipinhao",
}


def normalize_live_platform(value, default="douyin"):
    platform = str(value or default).strip().lower()
    return _PLATFORM_ALIASES.get(platform, platform)
