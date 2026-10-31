#!/usr/bin/env python3
"""Local preflight. Only safe status fields are emitted; no keys or upstream bodies."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_env(path: Path) -> dict[str, str]:
    result = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key):
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            result[key] = value
    result.update(os.environ)
    return result


def safe_json_get(base: str, path: str, token: str = "", *, timeout: float = 8) -> tuple[int, dict]:
    try:
        parsed = urllib.parse.urlsplit(base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            return 0, {}
        req = urllib.request.Request(base.rstrip("/") + path, headers={"Accept": "application/json"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                return response.status, {}
            try:
                payload = json.loads(raw)
            except ValueError:
                return response.status, {}
            return response.status, payload if isinstance(payload, dict) else {}
    except urllib.error.HTTPError as error:
        with error:
            return error.code, {}
    except (OSError, ValueError, urllib.error.URLError):
        return 0, {}


def model_diagnostics(code: int, body: dict) -> dict[str, str]:
    """Accept the complete backend check shape; never forward its detail text."""
    if code != 200 or not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        return {}
    checks = body["data"].get("checks")
    if not isinstance(checks, list):
        return {}
    statuses = {}
    for check in checks:
        if not isinstance(check, dict):
            return {}
        name, status = check.get("name"), check.get("status")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) or name in statuses:
            return {}
        if not isinstance(status, str) or status not in {"ok", "failed", "unconfigured", "configured"}:
            return {}
        statuses[name] = status
    if not {"tts_model", "bge_model"}.issubset(statuses):
        return {}
    return {name: statuses[name] for name in ("tts_model", "bge_model")}


def command(args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=15, check=False)
        return result.returncode == 0, result.stdout[:8192]
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--mode", choices=("compose", "native"), default="compose")
    parser.add_argument("--url", default="")
    parser.add_argument("--models", action="store_true", help="Probe TTS and configured BGE through the authenticated backend; also require host media HTTP, FFmpeg, and NVIDIA diagnostics")
    parser.add_argument("--media-url", default="", help="Host-reachable LiveTalking base URL for --models (e.g. http://127.0.0.1:8010); overrides LIVETALKING_BASE_URL for this HTTP check when its hostname is container-only")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    project = args.project.resolve()
    env = read_env(project / ".env")
    base = args.url or "http://127.0.0.1:" + env.get("APP_PORT", "8765")
    checks = []

    def add(key, passed, required, note, **fields):
        checks.append({"check": key, "passed": bool(passed), "required": required, "note": note, **fields})

    add("python", sys.version_info >= (3, 11), True, "Python 3.11+", version=".".join(map(str, sys.version_info[:3])))
    free = shutil.disk_usage(project).free
    add("disk", free >= 5 * 1024**3, True, "工作台最低保留5 GiB可用空间；模型权重与录制另计。", free_gib=round(free / 1024**3, 2))
    if args.mode == "compose":
        ready, _ = command(["docker", "compose", "version"], project)
        add("compose_cli", ready, True, "Docker Compose CLI可执行。")
        daemon, _ = command(["docker", "info", "--format", "{{.ServerVersion}}"], project)
        add("docker_daemon", daemon, True, "Docker服务可达。")
        valid, _ = command(["docker", "compose", "config", "--quiet"], project)
        add("compose_config", valid, True, "Compose配置可解析；未打印插值后的凭据。")
    else:
        for executable in ("go", "node"):
            found = shutil.which(executable) is not None
            add(executable, found, False, "仅源码开发需要；预编译工作台不依赖该命令。")
    code, body = safe_json_get(base, "/healthz")
    add("app_health", code == 200 and body.get("status") == "ok", True, "工作台HTTP存活检查。", http_status=code)
    token = env.get("APP_TOKEN", "")
    add("app_token", len(token) >= 24, True, "从本机配置读取；报告不包含口令。")
    code, body = safe_json_get(base, "/api/v1/status", token)
    data = body.get("data", {}) if isinstance(body.get("data"), dict) else {}
    add("app_database", code == 200 and data.get("storage") == "postgresql", True, "认证管理接口及数据库可用。", http_status=code, version=data.get("version", "unknown"))
    add("deepseek_configuration", bool(env.get("DEEPSEEK_API_KEY")), False, "只检查是否配置，未发起计费请求。人工草稿无需DeepSeek。")
    ffmpeg, _ = command(["ffmpeg", "-version"], project)
    add("ffmpeg", ffmpeg, args.models, "用于音画传输校准与录制分析。")
    gpu, gpu_data = command(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"], project)
    add("nvidia_gpu", gpu, args.models, "驱动信息不能证明模型吞吐或画质通过。", devices=[line.strip() for line in gpu_data.splitlines()[:8]] if gpu else [])
    if args.models:
        # The workers may use Compose-only DNS or host.docker.internal. Let the
        # actual backend resolve/probe them, using APP_TOKEN only for the app.
        # Its probe budget is 8 s; leave time for the authenticated HTTP response.
        diagnostics_code, diagnostics_body = safe_json_get(base, "/api/v1/diagnostics", token, timeout=15)
        statuses = model_diagnostics(diagnostics_code, diagnostics_body)
        tts_status = statuses.get("tts_model", "unverified")
        add("tts_engine", tts_status == "ok", True, "通过工作台后端网络核验TTS已加载及内容指纹，只有诊断status=ok通过；不进行语音合成。", http_status=diagnostics_code, diagnostic_status=tts_status)
        live = args.media_url or env.get("LIVETALKING_BASE_URL", "")
        # Its root may be HTML. A reachable 200 only proves HTTP transport,
        # not model readiness, WebRTC connectivity, or a published stream.
        code, _ = safe_json_get(live, "/") if live else (0, {})
        live_note = "只验证宿主机HTTP可达；请在独立输出页建立真实WebRTC并人工检查音画。" if code == 200 else "宿主机无法访问LiveTalking HTTP。若默认地址仅容器可达，使用 --media-url 指定宿主可达地址，例如 http://127.0.0.1:8010；该参数只覆盖本次HTTP检查。"
        add("livetalking_http", code == 200, True, live_note, http_status=code)
        bge_status = statuses.get("bge_model", "unverified")
        # Keyword mode remains optional only when the backend explicitly says
        # unconfigured and the operator has not declared a BGE configuration.
        bge_required = bge_status != "unconfigured" or bool(env.get("BGE_BASE_URL") or env.get("BGE_API_KEY"))
        bge_note = "通过工作台后端网络核验BGE模型，只有诊断status=ok通过；不直接从宿主机访问容器内部地址。" if bge_required else "工作台诊断确认未配置BGE，采用关键词模式；本项未通过模型就绪验收。"
        add("bge_engine", bge_status == "ok", bge_required, bge_note, http_status=diagnostics_code, diagnostic_status=bge_status)
    result = {"schema": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "mode": args.mode, "models_requested": args.models, "ready_for_requested_checks": all(c["passed"] for c in checks if c["required"]), "checks": checks, "not_measured": ["GPU实际模型性能", "人物失真与口型", "真实淘宝接收与账号权限", "八小时稳定性"]}
    output = args.output or project / "test-results" / ("doctor-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for check in checks:
        print(("PASS" if check["passed"] else "FAIL" if check["required"] else "INFO") + " " + check["check"] + " — " + check["note"])
    print("Report: " + str(output))
    return 0 if result["ready_for_requested_checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
