"""Failure-path maintenance tests and real FFmpeg calibration round-trips."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import backup_restore as backup
import doctor
import media_calibrate as media


class DoctorTests(unittest.TestCase):
    @staticmethod
    def diagnostics(tts="ok", bge="ok"):
        return {"data": {"checks": [
            {"name": "tts_model", "status": tts, "detail": "private-worker-detail"},
            {"name": "bge_model", "status": bge, "detail": "private-worker-detail"},
        ]}}

    def run_doctor(self, diagnostics, *, status=200, env_override=None, models=True, media_url="http://127.0.0.1:8010", media_status=200):
        env = {
            "APP_TOKEN": "unit-only-app-token-do-not-print",
            "TTS_BASE_URL": "http://host.docker.internal:9880", "TTS_API_KEY": "unit-only-tts-secret",
            "BGE_BASE_URL": "http://bge:8010", "BGE_API_KEY": "unit-only-bge-secret",
            "LIVETALKING_BASE_URL": "http://host.docker.internal:8010",
        }
        env.update(env_override or {})
        app = "http://127.0.0.1:8765"
        calls = []

        def get(base, path, token="", *, timeout=8):
            calls.append((base, path, token, timeout))
            if base == app and path == "/healthz":
                return 200, {"status": "ok"}
            if base == app and path == "/api/v1/status":
                return 200, {"data": {"storage": "postgresql", "version": "0.2.0"}}
            if base == app and path == "/api/v1/diagnostics":
                return status, diagnostics
            if base == (media_url or env["LIVETALKING_BASE_URL"]) and path == "/":
                return media_status, {}
            self.fail("Doctor attempted an unexpected host-network request.")

        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "doctor.json"
            args = ["--project", directory, "--mode", "native", "--url", app, "--output", str(report)]
            if models:
                args.append("--models")
            if media_url:
                args.extend(["--media-url", media_url])
            output = io.StringIO()
            with (
                patch.object(doctor, "read_env", return_value=env),
                patch.object(doctor, "safe_json_get", side_effect=get),
                patch.object(doctor, "command", return_value=(True, "unit GPU fixture")),
                patch.object(doctor.shutil, "which", return_value="/test/executable"),
                patch.object(doctor.shutil, "disk_usage", return_value=SimpleNamespace(free=10 * 1024**3)),
                redirect_stdout(output),
            ):
                result = doctor.main(args)
            payload = json.loads(report.read_text(encoding="utf-8"))
        return result, payload, calls, output.getvalue()

    def test_model_checks_use_authenticated_backend_and_host_media_override(self):
        result, payload, calls, output = self.run_doctor(self.diagnostics())
        self.assertEqual(result, 0)
        checks = {check["check"]: check for check in payload["checks"]}
        self.assertTrue(checks["tts_engine"]["passed"])
        self.assertTrue(checks["bge_engine"]["passed"])
        self.assertEqual([call for call in calls if call[1] == "/api/v1/diagnostics"], [
            ("http://127.0.0.1:8765", "/api/v1/diagnostics", "unit-only-app-token-do-not-print", 15),
        ])
        self.assertEqual([call for call in calls if call[0] != "http://127.0.0.1:8765"], [
            ("http://127.0.0.1:8010", "/", "", 8),
        ])
        serialized = json.dumps(payload, ensure_ascii=False) + output
        for private in ("host.docker.internal", "http://bge:8010", "private-worker-detail", "unit-only-app-token-do-not-print", "unit-only-tts-secret", "unit-only-bge-secret"):
            self.assertNotIn(private, serialized)

    def test_model_configuration_and_failure_never_count_as_ready(self):
        for name in ("tts", "bge"):
            for status in ("configured", "unconfigured", "failed"):
                with self.subTest(model=name, status=status):
                    result, payload, _, _ = self.run_doctor(self.diagnostics(**{name: status}))
                    checks = {check["check"]: check for check in payload["checks"]}
                    self.assertEqual(result, 1)
                    self.assertFalse(checks[name + "_engine"]["passed"])
                    self.assertTrue(checks[name + "_engine"]["required"])
                    self.assertEqual(checks[name + "_engine"]["diagnostic_status"], status)

    def test_malformed_or_unsuccessful_diagnostics_fail_closed(self):
        valid = self.diagnostics()
        bodies = [
            None, [], {}, {"data": None}, {"data": []},
            {"data": {"checks": {}}}, {"data": {"checks": []}},
            {"data": {"checks": [None]}},
            {"data": {"checks": [{"name": "tts_model", "status": "ok"}]}},
            {"data": {"checks": valid["data"]["checks"] + [{"name": "tts_model", "status": "failed"}]}},
            {"data": {"checks": [{"name": "tts_model", "status": True}, valid["data"]["checks"][1]]}},
            {"data": {"checks": [{"name": "tts_model", "status": "private-worker-detail"}, valid["data"]["checks"][1]]}},
        ]
        for index, body in enumerate(bodies):
            with self.subTest(shape=index):
                result, payload, _, output = self.run_doctor(body)
                checks = {check["check"]: check for check in payload["checks"]}
                self.assertEqual(result, 1)
                for key in ("tts_engine", "bge_engine"):
                    self.assertFalse(checks[key]["passed"])
                    self.assertTrue(checks[key]["required"])
                    self.assertEqual(checks[key]["diagnostic_status"], "unverified")
                self.assertNotIn("private-worker-detail", output + json.dumps(payload))
        for code in (0, 401, 503):
            with self.subTest(http_status=code):
                result, payload, _, _ = self.run_doctor(valid, status=code)
                self.assertEqual(result, 1)
                self.assertTrue(all(not check["passed"] for check in payload["checks"] if check["check"] in ("tts_engine", "bge_engine")))

    def test_bge_keyword_mode_is_optional_but_never_reported_ready(self):
        result, payload, _, _ = self.run_doctor(self.diagnostics(bge="unconfigured"), env_override={"BGE_BASE_URL": "", "BGE_API_KEY": ""})
        check = next(check for check in payload["checks"] if check["check"] == "bge_engine")
        self.assertEqual(result, 0)
        self.assertFalse(check["passed"])
        self.assertFalse(check["required"])
        self.assertIn("关键词", check["note"])
        # Backend configuration is authoritative even when host .env lacks it.
        result, payload, _, _ = self.run_doctor(self.diagnostics(bge="failed"), env_override={"BGE_BASE_URL": "", "BGE_API_KEY": ""})
        check = next(check for check in payload["checks"] if check["check"] == "bge_engine")
        self.assertEqual(result, 1)
        self.assertFalse(check["passed"])
        self.assertTrue(check["required"])

    def test_model_probes_are_not_made_without_models_option(self):
        result, _, calls, _ = self.run_doctor(self.diagnostics(), models=False)
        self.assertEqual(result, 0)
        self.assertEqual([call[1] for call in calls], ["/healthz", "/api/v1/status"])

    def test_unreachable_default_media_address_has_actionable_host_override(self):
        result, payload, calls, output = self.run_doctor(self.diagnostics(), media_url="", media_status=0)
        check = next(check for check in payload["checks"] if check["check"] == "livetalking_http")
        self.assertEqual(result, 1)
        self.assertFalse(check["passed"])
        self.assertIn("--media-url", check["note"])
        self.assertIn("宿主", check["note"])
        self.assertNotIn("host.docker.internal", output + json.dumps(payload))
        self.assertIn(("http://host.docker.internal:8010", "/", "", 8), calls)

    def test_safe_json_get_timeout_and_nonobject_response_handling(self):
        for raw, expected in ((b'{"data":{}}', {"data": {}}), (b"[]", {}), (b"null", {}), (b"true", {}), (b"not json", {}), (b"x" * (1024 * 1024 + 1), {})):
            with self.subTest(length=len(raw)):
                response = io.BytesIO(raw)
                response.status = 200
                opener = Mock()
                opener.open.return_value = response
                with patch.object(doctor.urllib.request, "build_opener", return_value=opener):
                    self.assertEqual(doctor.safe_json_get("http://127.0.0.1:8765", "/api/v1/diagnostics", "unit-only-app-token", timeout=15), (200, expected))
                self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.get_header("Authorization"), "Bearer unit-only-app-token")
                self.assertNotIn("unit-only-app-token", request.full_url)

    def test_safe_json_get_rejects_invalid_or_credential_urls_before_request(self):
        for base in ("http://[invalid", "file:///tmp/model", "http://user:secret@localhost:8000", "http://localhost:8000?token=secret", "http://localhost:8000#secret"):
            with self.subTest(base=base), patch.object(doctor.urllib.request, "build_opener") as opener:
                self.assertEqual(doctor.safe_json_get(base, "/healthz"), (0, {}))
                opener.assert_not_called()


class FixtureCompose:
    def __init__(self):
        self.started = True
        self.events = []
        self.fail_dump = False
        self.fail_restores = 0

    def running(self):
        return self.started

    def stop(self):
        self.started = False
        self.events.append("stop")

    def start(self):
        self.started = True
        self.events.append("start")

    def image(self):
        return "sha256:" + "a" * 64

    def dump(self, path):
        if self.started:
            raise AssertionError("dump raced a running app")
        if self.fail_dump:
            raise backup.BackupError("injected dump failure")
        path.write_bytes(b"PGDMP unit fixture, not a restorable database")

    def copy_audio_out(self, path):
        if self.started:
            raise AssertionError("audio copy raced a running app")
        path.mkdir()
        (path / "fixture.wav").write_bytes(b"unit fixture, not model speech")

    def restore(self, source):
        if self.started:
            raise AssertionError("restore raced a running app")
        self.events.append("restore:" + source.name)
        if self.fail_restores:
            self.fail_restores -= 1
            raise backup.BackupError("injected restore failure")


class BackupTests(unittest.TestCase):
    def test_failed_backup_always_restores_previously_running_app(self):
        with tempfile.TemporaryDirectory() as directory:
            compose = FixtureCompose()
            compose.fail_dump = True
            with self.assertRaises(backup.BackupError):
                backup.backup(compose, Path(directory) / "snapshot")
            self.assertTrue(compose.started)
            self.assertFalse((Path(directory) / "snapshot").exists())
            self.assertEqual(compose.events, ["stop", "start"])

    def test_corrupt_backup_and_missing_confirmation_are_rejected_before_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose = FixtureCompose()
            backup.backup(compose, root / "source")
            backup.verify_backup(root / "source")
            compose.events.clear()
            with self.assertRaises(backup.BackupError):
                backup.restore(compose, root / "source", root / "safety", False)
            self.assertEqual(compose.events, [])
            (root / "source/audio/fixture.wav").write_bytes(b"tampered")
            with self.assertRaises(backup.BackupError):
                backup.restore(compose, root / "source", root / "safety", True)
            self.assertEqual(compose.events, [])

    def test_restore_failure_rolls_back_database_and_audio_before_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose = FixtureCompose()
            backup.backup(compose, root / "source")
            compose.events.clear()
            compose.fail_restores = 1
            with self.assertRaisesRegex(backup.BackupError, "已用操作前快照自动回退"):
                backup.restore(compose, root / "source", root / "safety", True)
            self.assertEqual(compose.events, ["stop", "restore:source", "restore:safety", "start"])
            backup.verify_backup(root / "safety")

    def test_double_failure_leaves_app_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose = FixtureCompose()
            backup.backup(compose, root / "source")
            compose.events.clear()
            compose.fail_restores = 2
            with self.assertRaisesRegex(backup.BackupError, "app保持停止"):
                backup.restore(compose, root / "source", root / "safety", True)
            self.assertFalse(compose.started)

    def test_path_traversal_and_concurrent_maintenance_are_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose = FixtureCompose()
            backup.backup(compose, root / "source")
            path = root / "source/manifest.json"
            manifest = json.loads(path.read_text())
            manifest["files"]["../outside"] = {"sha256": "a" * 64, "bytes": 1}
            path.write_text(json.dumps(manifest))
            with self.assertRaises(backup.BackupError):
                backup.verify_backup(root / "source")
            with backup.maintenance_lock(root):
                with self.assertRaises(backup.BackupError):
                    with backup.maintenance_lock(root):
                        pass
            self.assertFalse((root / ".backup-restore.lock").exists())


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for actual calibration round-trip tests")
class CalibrationTests(unittest.TestCase):
    def test_known_zero_and_positive_and_negative_offsets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for offset in (0, 120, -120):
                path = root / (str(offset) + ".mkv")
                media.generate(path, offset_ms=offset)
                result = media.analyze(path)
                self.assertAlmostEqual(result["median_audio_minus_video_ms"], offset, delta=5)
                self.assertEqual(result["within_target"], abs(offset) <= 80)

    def test_container_audio_pts_offset_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, shifted = root / "reference.mkv", root / "shifted.mkv"
            media.generate(source)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(source), "-itsoffset", "0.12", "-i", str(source), "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", str(shifted)], check=True, capture_output=True)
            result = media.analyze(shifted)
            self.assertAlmostEqual(result["median_audio_minus_video_ms"], 120, delta=5)


if __name__ == "__main__":
    unittest.main()
