#!/usr/bin/env python3
"""CI-only data round trip through the real Compose backup/restore commands.

The WAV and ready-job state are explicit persistence fixtures, not TTS or
LiveTalking acceptance. No model or platform service is called. Only a fresh,
uniquely named GitHub Actions Compose project may run this destructive test.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import wave


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8765"


class SmokeError(RuntimeError):
    """Messages are fixed test labels, never response bodies or credentials."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def require_isolated_ci(env: dict[str, str]) -> str:
    run = env.get("GITHUB_RUN_ID", "")
    attempt = env.get("GITHUB_RUN_ATTEMPT", "")
    project = f"shuziren-ci-{run}-{attempt}"
    require(
        env.get("GITHUB_ACTIONS") == "true"
        and re.fullmatch(r"[0-9]+", run) is not None
        and re.fullmatch(r"[0-9]+", attempt) is not None
        and env.get("COMPOSE_PROJECT_NAME") == project,
        "Refusing restore outside the uniquely named GitHub Actions CI project.",
    )
    require(
        not env.get("COMPOSE_FILE")
        and not env.get("COMPOSE_ENV_FILES")
        and env.get("APP_PORT", "8765") == "8765",
        "Refusing an overridden Compose file, environment file, or API port.",
    )
    require(len(env.get("APP_TOKEN", "")) >= 24, "The CI workspace token is missing.")
    return project


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def fixture_wav(frequency: int) -> bytes:
    """A short PCM tone solely for byte-exact filesystem persistence checks."""
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"".join(
            struct.pack("<h", round(4000 * math.sin(2 * math.pi * frequency * i / 16000)))
            for i in range(4000)
        ))
    return output.getvalue()


class Smoke:
    def __init__(self, project: str, token: str):
        self.project = project
        self.token = token
        self.stage = "isolation checks"
        # Neither proxy configuration nor an HTTP redirect may forward a token.
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def command(self, args: list[str], *, data: bytes | None = None, timeout: int = 90) -> bytes:
        try:
            result = subprocess.run(args, input=data, capture_output=True, cwd=ROOT, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise SmokeError("A local test command was unavailable or timed out.") from None
        require(result.returncode == 0, "A local test command failed; captured output was not printed.")
        return result.stdout

    def compose(self, args: list[str], *, data: bytes | None = None) -> bytes:
        return self.command(["docker", "compose", *args], data=data)

    def sql(self, statement: str, **ids: str) -> str:
        args = ["exec", "-T", "db", "psql", "-X", "-q", "-A", "-t", "-U", "shuziren", "-d", "shuziren", "-v", "ON_ERROR_STOP=1"]
        for name, value in ids.items():
            require(re.fullmatch(r"[a-z_]+", name) is not None, "Invalid SQL fixture variable.")
            require(str(uuid.UUID(value)) == value, "Invalid fixture UUID.")
            args.extend(["-v", f"{name}={value}"])
        # psql quotes :'variables'; no credential or arbitrary string is SQL input.
        return self.compose(args, data=statement.encode()).decode().strip()

    def request(self, path: str, *, data: dict | None = None, method: str = "GET", token: str | None = None, expected: int = 200) -> bytes:
        headers = {"Authorization": "Bearer " + (self.token if token is None else token)}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data, ensure_ascii=False).encode()
        request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
        try:
            with self.http.open(request, timeout=10) as response:
                status, raw = response.status, response.read(1_048_577)
        except urllib.error.HTTPError as error:
            with error:
                status, raw = error.code, error.read(1_048_577)
        except (OSError, ValueError):
            raise SmokeError("The local API request failed.") from None
        require(status == expected, f"The local API returned HTTP {status}; expected {expected}.")
        require(len(raw) <= 1_048_576, "The local API response exceeded the test limit.")
        return raw

    def api(self, path: str, *, data: dict | None = None, method: str = "GET"):
        payload = json.loads(self.request("/api/v1" + path, data=data, method=method))
        require(isinstance(payload, dict) and "data" in payload, "The management API envelope was invalid.")
        return payload["data"]

    def output_status(self, token: str, receiver: str, *, revoked: bool = False) -> dict:
        payload = json.loads(self.request(
            "/output-api/v1/status?receiver_id=" + receiver,
            token=token, expected=401 if revoked else 200,
        ))
        if revoked:
            require(payload.get("error", {}).get("code") == "output_unauthorized", "The old output credential was not explicitly rejected.")
            return {}
        require(isinstance(payload.get("data"), dict), "The output API envelope was invalid.")
        return payload["data"]

    def wait_ready(self) -> None:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                status = self.api("/status")
                require(status["storage"] == "postgresql", "The application storage is not PostgreSQL.")
                require(not status["deepseek"]["configured"], "DeepSeek must be unconfigured for this persistence test.")
                require(not status["media"]["tts_configured"] and not status["media"]["live_configured"], "Media engines must be unconfigured for this persistence test.")
                return
            except (SmokeError, KeyError, ValueError):
                time.sleep(0.5)
        raise SmokeError("The application did not become ready with the isolated CI configuration.")

    def write_audio(self, filename: str, contents: bytes) -> None:
        require(re.fullmatch(r"[a-z0-9-]+\.wav", filename) is not None, "Invalid audio fixture filename.")
        self.compose(["exec", "-T", "app", "sh", "-c", 'cat > "$1"', "ci-audio-fixture", "/data/audio/" + filename], data=contents)

    def backup_command(self, command: str, destination: Path) -> None:
        args = [sys.executable, str(ROOT / "scripts/backup_restore.py"), command, str(destination)]
        if command == "restore":
            args.append("--confirm-replace")
        self.command(args, timeout=600)

    def run(self, destination: Path) -> None:
        # Confirm the app and DB really belong to the guarded project before
        # making any data changes or invoking --confirm-replace.
        for service in ("app", "db"):
            container = self.compose(["ps", "--quiet", service]).decode().strip()
            require(re.fullmatch(r"[a-f0-9]{12,64}", container) is not None, "The isolated CI service is missing.")
            label = self.command(["docker", "inspect", "--format", '{{ index .Config.Labels "com.docker.compose.project" }}', container]).decode().strip()
            require(label == self.project, "A container belongs to a different Compose project.")
        self.wait_ready()
        require(self.api("/shops") == [], "Refusing to overwrite a database that already has business data.")

        self.stage = "creating persistence fixtures"
        shop = self.api("/shops", method="POST", data={"name": "CI 备份恢复隔离店铺"})
        shop_id = shop["id"]
        fields = {
            "shop_id": shop_id, "title": "CI 备份基准商品", "sku": "CI-BACKUP-BASELINE",
            "description": "自动化备份恢复测试资料", "specs": "标准款",
            "price_cents": 1299, "stock": 17, "active": True, "expires_at": None,
        }
        product = self.api("/products", method="POST", data={**fields, "version": 0})
        session = self.api("/sessions", method="POST", data={"shop_id": shop_id, "title": "CI 恢复后必须暂停的场次"})
        session_id = session["id"]
        query = f"?shop_id={shop_id}&session_id={session_id}"
        config = {"width": 960, "height": 540, "fit": "contain", "background": "#123456"}
        output_path = f"/sessions/{session_id}/output"
        self.api(output_path, method="PUT", data={"shop_id": shop_id, **config})
        issued = self.api(output_path + "/issue", method="POST", data={"shop_id": shop_id})
        old_token = issued["token"]
        receiver = str(uuid.uuid4())
        require(self.output_status(old_token, receiver)["enabled"] is True, "The baseline output credential was not usable.")

        job = self.api("/jobs/manual", method="POST", data={
            "shop_id": shop_id, "session_id": session_id, "product_id": product["id"],
            "text": "这是备份恢复测试商品，仅用于本地自动化验收。",
        })
        job_id = job["id"]
        approved = self.api(f"/jobs/{job_id}/approve", method="POST", data={"shop_id": shop_id})
        require(approved["status"] == "approved", "The manual fixture could not be approved.")
        filename = job_id + ".wav"
        original_audio, changed_audio = fixture_wav(440), fixture_wav(880)
        self.write_audio(filename, original_audio)
        # CI has no GPU or model. Seed only the persistent ready state needed to
        # exercise a future schedule; no synthesis/send endpoint is invoked.
        updated = self.sql("""
UPDATE speech_jobs SET status='ready',audio_ready=true,updated_at=now()
WHERE id=:'job_id' AND shop_id=:'shop_id' AND status='approved' RETURNING id::text;
""", job_id=job_id, shop_id=shop_id)
        require(updated == job_id, "The explicit ready-job persistence fixture was not installed.")
        audio_path = f"/api/v1/jobs/{job_id}/audio?shop_id={shop_id}"
        require(self.request(audio_path) == original_audio, "The initial WAV was not readable through the protected API.")
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
        schedule = self.api(f"/jobs/{job_id}/schedule", method="POST", data={
            "shop_id": shop_id, "run_at": run_at.isoformat(),
            "expires_at": (run_at + dt.timedelta(minutes=5)).isoformat(),
        })
        require(schedule["status"] == "scheduled", "The future fixture schedule was not persisted.")

        self.stage = "backing up business data and WAV"
        self.backup_command("backup", destination)
        self.backup_command("verify", destination)
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        require(manifest["files"]["audio/" + filename]["sha256"] == hashlib.sha256(original_audio).hexdigest(), "The backup did not contain the original WAV.")
        require(manifest["environment_file_included"] is False, "The backup unexpectedly included an environment file.")
        self.wait_ready()
        # A backup's ordinary restart must not be mistaken for restore's
        # deliberate invalidation of otherwise valid future work and tokens.
        require(self.api("/sessions?shop_id=" + shop_id)[0]["status"] == "active", "Backup unexpectedly paused the active session.")
        require(self.api("/schedules" + query)[0] == schedule, "Backup unexpectedly changed the future schedule.")
        require(self.output_status(old_token, receiver)["enabled"] is True, "Backup unexpectedly revoked the output credential.")
        print("Backup captured actual business rows and a synthetic test WAV; ordinary restart retained the future schedule.")

        self.stage = "changing live data after the backup"
        changed_product = self.api(f"/products/{product['id']}", method="PUT", data={
            **fields, "version": product["version"], "title": "CI 备份之后的变更", "price_cents": 9999, "stock": 2,
        })
        require(changed_product["version"] == product["version"] + 1, "The product change did not advance its version.")
        self.api("/products", method="POST", data={**fields, "sku": "CI-POST-BACKUP-ONLY", "version": 0})
        require(len(self.api("/products?shop_id=" + shop_id)) == 2, "The post-backup product was not created.")
        self.write_audio(filename, changed_audio)
        self.write_audio("ci-post-backup-only.wav", changed_audio)
        require(self.request(audio_path) == changed_audio, "The live WAV did not actually change after backup.")
        self.api(output_path, method="PUT", data={"shop_id": shop_id, **config, "width": 1280})
        new_token = self.api(output_path + "/issue", method="POST", data={"shop_id": shop_id})["token"]
        self.output_status(old_token, receiver, revoked=True)
        require(self.output_status(new_token, receiver)["enabled"] is True, "The post-backup output credential was not usable.")

        self.stage = "restoring the real database and audio volume"
        self.backup_command("restore", destination)
        self.wait_ready()
        require(self.api("/shops") == [shop], "The original shop was not restored exactly.")
        require(self.api("/products?shop_id=" + shop_id) == [product], "Product facts/version or the post-backup row were not restored correctly.")
        require(self.request(audio_path) == original_audio, "The restored WAV differs from the backed-up bytes.")
        self.compose(["exec", "-T", "app", "sh", "-c", 'test ! -e "$1" && test -r "$2" && test -w "$2" && test -w /data/audio', "ci-restore-check", "/data/audio/ci-post-backup-only.wav", "/data/audio/" + filename])

        self.stage = "checking paused sessions and revoked old work"
        restored_session = self.api("/sessions?shop_id=" + shop_id)[0]
        require(restored_session["id"] == session_id and restored_session["status"] == "paused", "The restored session was not paused.")
        require(restored_session["epoch"] == session["epoch"] + 1 and restored_session["media_session_id"] is None, "The restored session retained its old epoch or media binding.")
        restored_job = self.api("/jobs" + query)[0]
        require(restored_job["id"] == job_id and restored_job["status"] == "cancelled" and restored_job["error_code"] == "backup_restored", "The restored ready job was not invalidated.")
        restored_schedule = self.api("/schedules" + query)[0]
        require(restored_schedule["id"] == schedule["id"] and restored_schedule["status"] == "cancelled" and restored_schedule["error_code"] == "backup_restored", "The restored future schedule was not invalidated.")
        output = self.api(output_path + "?shop_id=" + shop_id)
        require(output["config"] == config and output["generation"] == issued["output"]["generation"] + 1, "The output configuration or generation was not restored correctly.")
        require(output["enabled"] is False and output["online"] is False and output["session_status"] == "paused", "Restoration left output enabled or online.")
        self.output_status(old_token, receiver, revoked=True)
        self.output_status(new_token, receiver, revoked=True)
        # Read only booleans/counts, never token hashes or any secret value.
        checks = json.loads(self.sql("""
SELECT json_build_object(
 'output_reset', (SELECT NOT enabled AND token_hash IS NULL AND lease_id IS NULL
    AND receiver_id IS NULL AND lease_epoch IS NULL AND lease_expires_at IS NULL
    AND last_heartbeat_at IS NULL AND peer_state='closed' AND NOT video_ready
    AND NOT audio_ready AND media_session_id IS NULL
    FROM session_outputs WHERE session_id=:'session_id'),
 'history_count', (SELECT count(*) FROM product_history WHERE product_id=:'product_id'),
 'restore_audits', (SELECT count(*) FROM audit_events WHERE shop_id=:'shop_id' AND event='backup_restored')
);
""", session_id=session_id, product_id=product["id"], shop_id=shop_id))
        require(checks == {"output_reset": True, "history_count": 1, "restore_audits": 1}, "Restored history, output state, or restore audit was inconsistent.")
        print("Restore verified exact product facts/history and WAV bytes, removed post-backup data, paused the session, revoked both output tokens, and cancelled old jobs/schedules.")


def main() -> int:
    smoke = None
    try:
        project = require_isolated_ci(dict(os.environ))
        smoke = Smoke(project, os.environ["APP_TOKEN"])
        with tempfile.TemporaryDirectory(prefix="shuziren-ci-roundtrip-") as directory:
            smoke.run(Path(directory) / "snapshot")
        return 0
    except Exception as error:
        # Even unexpected parser/subprocess errors must not expose a response,
        # authorization header, command environment, or issued output URL.
        stage = smoke.stage if smoke is not None else "CI isolation guard"
        detail = str(error) if isinstance(error, SmokeError) else "Unexpected test failure; sensitive diagnostics were not printed."
        print(f"Backup/restore smoke failed during {stage}: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
