"""Configuration path handling recovered from main.pyd."""

import logging
import os
from copy import deepcopy
import tempfile


class UserConfigError(ValueError):
    pass


def resolve_user_config_path():
    base_dir = os.environ.get("LOCALAPPDATA")
    if not base_dir:
        base_dir = os.path.join(os.path.expanduser("~"), ".huanjing_live")
    return os.path.join(base_dir, "HuanjingLive", "user_config.yaml")


def write_user_config(path, config):
    """Write a prepared user configuration using the recovered replacement sequence."""
    import yaml

    if not isinstance(config, dict):
        raise UserConfigError("用户配置必须是字典")
    path = os.path.abspath(os.fspath(path))
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yaml.safe_dump(config, stream, allow_unicode=True, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            if os.path.exists(temporary):
                os.unlink(temporary)
        except OSError:
            pass


def load_user_config(path):
    import yaml

    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError):
        # YAML parser errors may quote the damaged line, which can contain a
        # credential. Keep the user-facing failure explicit without chaining
        # secret-bearing parser diagnostics into application logs.
        raise UserConfigError("用户配置损坏或无法读取，请先备份后修复") from None
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise UserConfigError("用户配置根节点必须是字典")
    return config


def save_user_config(path, updates):
    config = load_user_config(path)
    config.update(updates)
    write_user_config(path, config)


def merge_config(target, updates):
    """Apply the recovered recursive dictionary and indexed list update rules."""
    for key, value in updates.items():
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merge_config(current, value)
        elif isinstance(current, list) and isinstance(value, list):
            for index, item in enumerate(value):
                if item in (None, "", [], {}):
                    continue
                if index >= len(current):
                    current.append(deepcopy(item))
                elif isinstance(current[index], dict) and isinstance(item, dict):
                    merge_config(current[index], item)
                else:
                    current[index] = deepcopy(item)
        else:
            target[key] = deepcopy(value)


def load_effective_config(runtime_dir, user_config_path):
    """Load the base configuration and apply existing user overrides."""
    import yaml

    from .main_webview import normalize_environment_config

    path = os.path.join(runtime_dir, "config", "config.yaml")
    with open(path, "r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream) or {}
    user_config = load_user_config(user_config_path)
    user_private = user_config.get("private_config")
    migrated = merge_legacy_private_config(config, user_private)
    if migrated is not None:
        try:
            save_user_config(user_config_path, {"private_config": migrated})
        except Exception:
            logging.getLogger(__name__).warning("迁移旧版账号配置失败，将保留原配置", exc_info=True)
        else:
            user_private = migrated
            clear_private_config(config)
            try:
                write_user_config(path, config)
            except Exception:
                logging.getLogger(__name__).warning("清理旧版交付配置失败，将继续使用用户配置", exc_info=True)

    if isinstance(user_private, dict):
        merge_config(config, user_private)
    for key in ("token", "llm_config", "volcengine_image_config"):
        if key in user_config:
            config[key] = user_config[key]
    return normalize_environment_config(config)


USER_PRIVATE_CONFIG_KEYS = frozenset({
    "access_key", "access_key_id", "access_key_secret", "access_token",
    "api_key", "authorization", "cookie", "group_id", "password",
    "passwd", "refresh_token", "secret", "secret_key", "token",
    "api_secret", "app_secret", "ark_api_key", "client_secret", "id_token",
    "minimax_api_key", "private_key", "runninghub_api_key", "session_token",
})


def _is_private_key(key):
    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in USER_PRIVATE_CONFIG_KEYS or normalized.endswith((
        "_api_key", "_secret", "_password", "_passwd", "_token", "_cookie",
    ))


def clear_private_config(value):
    """Blank private fields in an in-memory configuration tree."""
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_private_key(key):
                value[key] = ""
            else:
                clear_private_config(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            clear_private_config(item)


def _has_private_value(value):
    return value != None and value != "" and value != [] and value != {}


def extract_private_config(value):
    """Extract private configuration values while preserving sequence indices."""
    if isinstance(value, dict):
        extracted = {}
        for key, item in value.items():
            if _is_private_key(key):
                if _has_private_value(item):
                    extracted[key] = deepcopy(item)
            else:
                nested = extract_private_config(item)
                if _has_private_value(nested):
                    extracted[key] = nested
        return extracted

    if isinstance(value, (list, tuple)):
        extracted = [extract_private_config(item) for item in value]
        return extracted if any(_has_private_value(item) for item in extracted) else []

    return None


def merge_legacy_private_config(base_config, user_private_config):
    """Prepare the private configuration for the startup migration."""
    legacy = extract_private_config(base_config)
    if not legacy:
        return None
    if isinstance(user_private_config, dict):
        merge_config(legacy, user_private_config)
    return legacy
