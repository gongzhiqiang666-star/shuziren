"""Platform names accepted by the OCR capture settings."""

_PLATFORM_ALIASES = {
    "other": "general",
    "虾皮": "shopee",
    "xiapi": "shopee",
    "xiaopi": "shopee",
    "shoppe": "shopee",
}


def normalize_platform(value):
    name = str(value or "general").strip().lower()
    return _PLATFORM_ALIASES.get(name, name)
