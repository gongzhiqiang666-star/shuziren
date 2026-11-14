"""Validation and idempotency contracts for IP-agent social publishing."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_PLATFORMS = ("douyin", "kuaishou", "tencent", "xiaohongshu")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_account_names(value, platforms):
    raw = value if isinstance(value, dict) else {}
    accounts = {}
    for platform in platforms:
        name = str(raw.get(platform) or "default").strip() or "default"
        if re.fullmatch(r"[\w-]{1,80}", name, re.UNICODE) is None or name in (".", ".."):
            raise ValueError(f"{platform} 账号名称格式无效")
        accounts[platform] = name
    return accounts


def normalize_publish_date(value):
    if value in (None, "", 0, "0"):
        return 0
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("定时发布时间格式无效")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if value <= datetime.now(timezone.utc):
        raise ValueError("定时发布时间必须晚于当前时间")
    return value


def build_publish_plan(video_path, title, tags, platforms, account_names=None,
                       publish_date=0, thumbnail_path=None, request_id=None):
    video = Path(video_path).expanduser().resolve()
    if not video.is_file() or video.stat().st_size <= 0:
        raise FileNotFoundError("请先生成可用的视频成片")
    normalized_platforms = list(dict.fromkeys(str(item).strip().lower() for item in platforms or [] if str(item).strip()))
    if not normalized_platforms:
        raise ValueError("请至少选择一个发布平台")
    unsupported = [item for item in normalized_platforms if item not in SUPPORTED_PLATFORMS]
    if unsupported:
        raise ValueError("不支持的发布平台: " + ", ".join(unsupported))
    normalized_title = str(title or "").strip()
    if not normalized_title or len(normalized_title) > 100:
        raise ValueError("发布标题长度必须为 1~100 个字符")
    normalized_tags = list(dict.fromkeys(str(item).strip().lstrip("#") for item in tags or [] if str(item).strip().lstrip("#")))
    if len(normalized_tags) > 20 or any(len(item) > 30 for item in normalized_tags):
        raise ValueError("发布标签最多 20 个且每个不超过 30 个字符")
    thumbnail = ""
    if thumbnail_path:
        candidate = Path(thumbnail_path).expanduser().resolve()
        if not candidate.is_file():
            raise FileNotFoundError("发布封面不存在")
        thumbnail = str(candidate)
    scheduled = normalize_publish_date(publish_date)
    video_digest = file_sha256(video)
    accounts = normalize_account_names(account_names, normalized_platforms)
    stable = {
        "video_sha256": video_digest, "title": normalized_title, "tags": normalized_tags,
        "platforms": normalized_platforms, "account_names": accounts,
        "publish_date": scheduled.isoformat() if isinstance(scheduled, datetime) else 0,
        "thumbnail_path": thumbnail,
    }
    identifier = str(request_id or "").strip()
    if identifier and re.fullmatch(r"[A-Za-z0-9_-]{8,80}", identifier) is None:
        raise ValueError("发布请求编号格式无效")
    if not identifier:
        identifier = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {**stable, "video_path": str(video), "publish_date_value": scheduled, "request_id": identifier}
