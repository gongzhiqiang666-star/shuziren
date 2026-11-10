"""Local console settings. Never edits or executes the reference runtime."""
import json
import os
from pathlib import Path
import tempfile

from scripts.v122_package_policy import REQUIRED_RUNTIME_FILES


class ConfigError(ValueError):
    pass


def default_data_directory():
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "Shuziren"


def validate(value):
    if not isinstance(value, dict) or set(value) != {"version", "runtime_root", "port"}:
        raise ConfigError("配置字段不完整或包含未知字段")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ConfigError("不支持的配置版本")
    if type(value["port"]) is not int or not 1024 <= value["port"] <= 65535:
        raise ConfigError("端口必须为1024至65535的整数")
    root = value["runtime_root"]
    if not isinstance(root, str) or "\x00" in root:
        raise ConfigError("资源路径必须为字符串")
    if root and (not root.strip() or not Path(root).is_absolute()):
        raise ConfigError("资源路径必须为绝对路径，或留空等待选择")
    return dict(value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("配置含重复字段")
        result[key] = value
    return result


class ConfigStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else default_data_directory()
        self.path = self.directory / "console.json"

    def load(self):
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"version": 1, "runtime_root": "", "port": 5158}
        except (OSError, UnicodeError) as error:
            raise ConfigError("无法读取配置：%s" % error) from error
        try:
            return validate(json.loads(content, object_pairs_hook=_unique_object))
        except (ValueError, TypeError) as error:
            raise ConfigError("配置加载失败，原文件已保留：%s" % error) from error

    def save(self, value):
        value = validate(value)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             prefix="console-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return value


def preflight(value):
    """Presence only: no hashing, model loading, GPU or live-platform claim."""
    value = validate(value)
    root = Path(value["runtime_root"]) if value["runtime_root"] else None
    checks = []
    if root is not None and root.name == "_internal":
        root = root.parent
    for relative in REQUIRED_RUNTIME_FILES:
        try:
            present = root is not None and (root / relative).is_file()
            checks.append({"path": relative, "present": present})
        except OSError as error:
            checks.append({"path": relative, "present": False, "error": str(error)})
    return {"scope": "required-file-presence-only", "ready": all(x["present"] for x in checks),
            "runtime_root": str(root) if root is not None else "", "checks": checks,
            "inference_verified": False, "integrity_verified": False}
