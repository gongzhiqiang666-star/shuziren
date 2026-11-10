import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock
from pathlib import Path

try:
    from scripts import v122_proof
except ImportError:
    v122_proof = None
try:
    from scripts import v122_proof_server
except ImportError:
    v122_proof_server = None
try:
    from scripts import build_v122_proof
except ImportError:
    build_v122_proof = None
try:
    from scripts import v122_adapter
except ImportError:
    v122_adapter = None
try:
    from scripts import v122_orchestrator
except ImportError:
    v122_orchestrator = None
try:
    from scripts import verify_v122_package
except ImportError:
    verify_v122_package = None
try:
    from scripts import v122_runtime_bridge
except ImportError:
    v122_runtime_bridge = None


PROJECT = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def test_runtime_map_names_every_required_stage(self):
        path = PROJECT / "docs/evidence/v122-runtime-map.md"
        self.assertTrue(path.is_file())
        source = path.read_text(encoding="utf-8")
        for stage in (
            "environment",
            "avatar_preprocess",
            "voice_generate",
            "avatar_drive",
            "mp4_output",
        ):
            with self.subTest(stage=stage):
                self.assertIn(f"`{stage}`", source)
        for field in ("入口", "输入", "输出", "证据", "置信状态"):
            with self.subTest(field=field):
                self.assertIn(field, source)


class ConfigTests(unittest.TestCase):
    def test_example_is_valid_and_selects_standard_environment_for_3060(self):
        self.assertIsNotNone(v122_proof)
        config = v122_proof.load_config(PROJECT / "config/v122-proof.example.json")
        v122_proof.validate_config(config)
        self.assertEqual(v122_proof.select_environment("NVIDIA GeForce RTX 3060"), "env")

    def test_rejects_unknown_sensitive_and_escaping_values(self):
        self.assertIsNotNone(v122_proof)
        base = v122_proof.example_config()
        for mutate in (
            lambda data: data.update({"unexpected": True}),
            lambda data: data.update({"api_key": "secret"}),
            lambda data: data["paths"].update({"runs": "../outside"}),
            lambda data: data["paths"].update({"runs": "C:/outside"}),
        ):
            data = json.loads(json.dumps(base))
            mutate(data)
            with self.assertRaises(v122_proof.ProofError):
                v122_proof.validate_config(data)

    def test_resolve_package_path_stays_beneath_root(self):
        self.assertIsNotNone(v122_proof)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(v122_proof.resolve_package_path(root, "runs/demo"), (root / "runs/demo").resolve())
            with self.assertRaises(v122_proof.ProofError):
                v122_proof.resolve_package_path(root, "../escape")


class WebWizardTests(unittest.TestCase):
    def test_wizard_contains_recording_fallback_progress_and_result_controls(self):
        web = PROJECT / "scripts/v122-proof/web"
        html = (web / "index.html").read_text(encoding="utf-8")
        script = (web / "app.js").read_text(encoding="utf-8")
        for text in (
            "开始摄像头录制", "选择已有视频", "开始麦克风录音", "选择已有音频",
            "检查并开始生成", "删除本次素材", "参考录音逐字稿", "新验证话术",
        ):
            self.assertIn(text, html)
        for token in ("getUserMedia", "MediaRecorder", "__v122Test", "/api/state", "/api/generate"):
            self.assertIn(token, script)
        combined = (html + script).lower()
        for forbidden in ("https://", "http://", "cdn", "analytics", "websocket"):
            self.assertNotIn(forbidden, combined)

    def test_recording_transitions_are_explicit(self):
        script = (PROJECT / "scripts/v122-proof/web/app.js").read_text(encoding="utf-8")
        for state in ("idle", "countdown", "recording", "preview", "confirmed", "fallback"):
            self.assertIn(f"'{state}'", script)
        self.assertIn("$('person-stop').disabled=enrollment.person!=='recording'", script)
        self.assertIn("$('voice-stop').disabled=enrollment.voice!=='recording'", script)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(v122_proof_server)
        self.temp = tempfile.TemporaryDirectory()
        web = PROJECT / "scripts/v122-proof/web"
        self.server = v122_proof_server.create_server(Path(self.temp.name), web, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        if hasattr(self, "server"):
            self.server.shutdown(); self.server.server_close()
        if hasattr(self, "temp"):
            self.temp.cleanup()

    def request(self, path, method="GET", body=None, content_type="application/json"):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"Content-Type": content_type, "X-V122-Proof": "1",
                                                  "Origin": self.base})
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())

    def test_state_upload_confirm_and_text_flow(self):
        status, state = self.request("/api/state")
        self.assertEqual(status, 200); self.assertEqual(state["bind"], "127.0.0.1")
        self.request("/api/materials/person", "POST", b"video", "video/webm")
        self.request("/api/materials/voice", "POST", b"audio", "audio/webm")
        self.request("/api/materials/person/confirm", "POST")
        self.request("/api/materials/voice/confirm", "POST")
        self.request("/api/text", "PUT", {"reference_transcript": "参考文字", "new_script": "新话术"})
        _, state = self.request("/api/state")
        self.assertTrue(state["materials"]["person"]["confirmed"])
        self.assertEqual(state["text"]["new_script"], "新话术")

    def test_generate_rejects_incomplete_and_delete_requires_confirmation(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/generate", "POST")
        self.assertEqual(caught.exception.code, 409)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("/api/current-run", "DELETE", {"confirm": False})
        self.assertEqual(caught.exception.code, 400)
        status, _ = self.request("/api/current-run", "DELETE", {"confirm": True})
        self.assertEqual(status, 200)

    def test_running_generation_cannot_be_claimed_twice_or_deleted(self):
        store = v122_proof_server.ProofStore(Path(self.temp.name))
        state = store.state()
        state["materials"] = {"person": {"confirmed": True}, "voice": {"confirmed": True}}
        state["text"] = {"reference_transcript": "参考", "new_script": "新话术"}
        store.save(state)
        store.claim_generation()
        with self.assertRaisesRegex(RuntimeError, "正在运行"):
            store.claim_generation()
        with self.assertRaisesRegex(RuntimeError, "不能删除"):
            store.delete_current()


class NormalizationTests(unittest.TestCase):
    def test_builds_fixed_argument_arrays_without_shell(self):
        video = v122_proof.normalization_command("ffmpeg", "person.webm", "person.mp4", "person")
        voice = v122_proof.normalization_command("ffmpeg", "voice.webm", "voice.wav", "voice")
        self.assertEqual(video[0], "ffmpeg"); self.assertIn("libx264", video); self.assertIn("yuv420p", video)
        self.assertEqual(voice[0], "ffmpeg"); self.assertIn("pcm_s16le", voice); self.assertIn("24000", voice)
        self.assertNotIn("shell", " ".join(video + voice).lower())

    def test_material_rules_reject_out_of_range_media(self):
        with self.assertRaisesRegex(v122_proof.ProofError, "MAT_VIDEO_DURATION"):
            v122_proof.validate_video_probe({"duration": 5, "width": 1920, "height": 1080, "fps": 25, "video_streams": 1})
        with self.assertRaisesRegex(v122_proof.ProofError, "MAT_AUDIO_DURATION"):
            v122_proof.validate_audio_probe({"duration": 4, "channels": 1, "codec": "pcm_s16le"})
        with self.assertRaisesRegex(v122_proof.ProofError, "MAT_AUDIO_DURATION"):
            v122_proof.validate_audio_probe({"duration": 16, "channels": 1, "codec": "pcm_s16le"})
        self.assertTrue(v122_proof.validate_video_probe({"duration": 30, "width": 1080, "height": 1920, "fps": 25, "video_streams": 1}))
        self.assertTrue(v122_proof.validate_audio_probe({"duration": 15, "channels": 1, "codec": "pcm_s16le"}))

    def test_parses_ffprobe_streams_for_video_audio_and_final_mp4(self):
        video = v122_proof.parse_ffprobe({"format":{"duration":"30"},"streams":[{"codec_type":"video","width":1080,"height":1920,"avg_frame_rate":"25/1"}]})
        audio = v122_proof.parse_ffprobe({"format":{"duration":"15"},"streams":[{"codec_type":"audio","channels":1,"codec_name":"pcm_s16le"}]})
        final = v122_proof.parse_ffprobe({"format":{"duration":"15"},"streams":[{"codec_type":"video"},{"codec_type":"audio"}]})
        self.assertEqual(video["video_streams"], 1); self.assertEqual(video["fps"], 25)
        self.assertEqual(audio["codec"], "pcm_s16le"); self.assertTrue(final["has_audio_video"])


class BuilderTests(unittest.TestCase):
    def test_builder_refuses_nonempty_destination_and_symlinks(self):
        self.assertIsNotNone(build_v122_proof)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "source"; source.mkdir(); (source / "required.txt").write_text("ok")
            proof = root / "proof"; proof.mkdir(); (proof / "tool.py").write_text("ok")
            destination = root / "destination"; destination.mkdir(); (destination / "keep.txt").write_text("mine")
            with self.assertRaises(build_v122_proof.BuildError):
                build_v122_proof.build_package(source, proof, destination, required=("required.txt",))
            destination = root / "fresh"
            (source / "link").symlink_to(source / "required.txt")
            with self.assertRaises(build_v122_proof.BuildError):
                build_v122_proof.build_package(source, proof, destination, required=("required.txt",))

    def test_builder_writes_sorted_hash_manifest(self):
        self.assertIsNotNone(build_v122_proof)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = root / "source"; source.mkdir(); (source / "required.txt").write_text("runtime")
            proof = root / "proof"; proof.mkdir(); (proof / "tool.py").write_text("proof")
            destination = root / "destination"
            manifest = build_v122_proof.build_package(source, proof, destination, required=("required.txt",))
            paths = [item["path"] for item in manifest["files"]]
            self.assertEqual(paths, sorted(paths)); self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["files"]))

    def test_release_manifest_includes_root_launchers(self):
        source = Path(build_v122_proof.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); runtime = root / "runtime"
            for name in ("数字人直播.exe", "_internal/start.py", "_internal/main.cp310-win_amd64.pyd",
                         "_internal/live/clone_manager.cp310-win_amd64.pyd", "_internal/config/config.yaml",
                         "_internal/env/python.exe", "_internal/env/ffmpeg/bin/ffmpeg.exe", "_internal/env/ffmpeg/bin/ffprobe.exe"):
                path = runtime / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"x")
            manifest = build_v122_proof.build_release(source, runtime, root / "release")
            paths = {item["path"] for item in manifest["files"]}
            self.assertIn("00_开始验证.cmd", paths); self.assertIn("99_停止验证.cmd", paths)

    def test_verifier_detects_changed_and_missing_files(self):
        self.assertIsNotNone(verify_v122_package)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "proof/manifests").mkdir(parents=True); item = root / "file.bin"; item.write_bytes(b"ok")
            manifest = {"format": 1, "files": [{"path": "file.bin", "bytes": 2,
                         "sha256": __import__("hashlib").sha256(b"ok").hexdigest()}]}
            (root / "proof/manifests/package.json").write_text(json.dumps(manifest))
            self.assertEqual(verify_v122_package.verify(root)["status"], "passed")
            item.write_bytes(b"changed")
            self.assertEqual(verify_v122_package.verify(root)["status"], "failed")
            item.unlink()
            result = verify_v122_package.verify(root)
            self.assertEqual(result["missing"], ["file.bin"])

    def test_refresh_tools_preserves_runtime_and_updates_proof_manifest(self):
        source = Path(build_v122_proof.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); runtime = root / "runtime"
            for name in ("数字人直播.exe", "_internal/start.py", "_internal/main.cp310-win_amd64.pyd",
                         "_internal/live/clone_manager.cp310-win_amd64.pyd", "_internal/config/config.yaml",
                         "_internal/env/python.exe", "_internal/env/ffmpeg/bin/ffmpeg.exe", "_internal/env/ffmpeg/bin/ffprobe.exe"):
                path = runtime / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"x")
            release = root / "release"; before = build_v122_proof.build_release(source, runtime, release)
            runtime_records = [item for item in before["files"] if item["path"].startswith("runtime/")]
            after = build_v122_proof.refresh_release_tools(source, release)
            self.assertEqual(runtime_records, [item for item in after["files"] if item["path"].startswith("runtime/")])
            self.assertEqual(verify_v122_package.verify(release)["status"], "passed")


class AdapterTests(unittest.TestCase):
    def test_commands_use_runtime_python_and_argument_arrays(self):
        self.assertIsNotNone(v122_adapter)
        adapter = v122_adapter.V122Adapter(Path("C:/proof/runtime/yunchuang_v122"), Path("C:/proof/proof/scripts/v122_runtime_bridge.py"))
        command = adapter.avatar_preprocess("in.mp4", "person", "person-id")
        self.assertEqual(Path(command[0]).parts[-3:], ("_internal", "env", "python.exe"))
        self.assertEqual(command[2], "avatar-preprocess"); self.assertNotIn("shell", " ".join(map(str, command)).lower())
        voice = adapter.voice_create("ref.wav", "逐字稿", "voice", "voice-id")
        self.assertIn("voice-create", voice); self.assertIn("逐字稿", voice)
        drive = adapter.avatar_drive("person-id", "fresh.wav", "result-video.mp4")
        self.assertIn("fresh.wav", drive); self.assertIn("result-video.mp4", drive)

    def test_bridge_finds_runtime_from_bundled_python_and_preserves_exact_reference_pair(self):
        self.assertIsNotNone(v122_runtime_bridge)
        executable = Path("C:/proof/runtime/yunchuang_v122/_internal/env/python.exe")
        self.assertEqual(v122_runtime_bridge.resolve_runtime("", executable, Path("C:/proof")),
                         Path("C:/proof/runtime/yunchuang_v122"))
        source = (PROJECT / "scripts/v122_runtime_bridge.py").read_text(encoding="utf-8")
        self.assertIn('result / "normalized_input.wav"', source)
        self.assertIn('result / "ref_audio.wav"', source)


class WindowsContractTests(unittest.TestCase):
    def test_launchers_open_local_page_and_never_kill_all_python(self):
        root = PROJECT / "scripts/v122-proof/windows"
        start = (root / "00_开始验证.cmd").read_text(encoding="utf-8")
        stop = (root / "99_停止验证.cmd").read_text(encoding="utf-8")
        helper = (root / "start-server.ps1").read_text(encoding="utf-8")
        combined = (start + stop + helper).lower()
        self.assertIn("127.0.0.1:5157", start); self.assertIn("v122_proof_server.py", helper)
        self.assertNotIn("taskkill /im", combined); self.assertNotIn("invoke-expression", combined)
        self.assertNotIn("executionpolicy", combined)
        self.assertIn("quote-argument", helper.lower())
        self.assertIn("stop-owned.ps1", stop)

    def test_preflight_checks_gpu_cuda_media_and_disk(self):
        root = PROJECT / "scripts/v122-proof/windows"
        source = (root / "preflight.ps1").read_text(encoding="utf-8").lower()
        for token in ("nvidia-smi", "torch.cuda.is_available", "onnxruntime", "ffmpeg.exe", "ffprobe.exe", "freespace", "package-integrity-$integrityprofile.json", "--profile $integrityprofile", "$integrityprofile = 'archive'"):
            self.assertIn(token, source)
        self.assertNotIn("get-childitem env:", source)


class OrchestrationTests(unittest.TestCase):
    def test_pipeline_uses_fresh_wav_for_drive_and_creates_mp4(self):
        self.assertIsNotNone(v122_orchestrator)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); run = root / "runs/r1"; materials = run / "materials"; materials.mkdir(parents=True)
            (materials / "person.webm").write_bytes(b"person"); (materials / "voice.webm").write_bytes(b"voice")
            calls = []
            class FakeAdapter:
                def avatar_preprocess(self, *args): return ["python", "bridge", "avatar-preprocess", *map(str,args)]
                def voice_create(self, *args): return ["python", "bridge", "voice-create", *map(str,args)]
                def speech_generate(self, *args): return ["python", "bridge", "speech-generate", *map(str,args)]
                def avatar_drive(self, *args): return ["python", "bridge", "avatar-drive", *map(str,args)]
            def fake_run(command, **kwargs):
                calls.append(list(map(str, command)))
                if Path(str(command[0])).name == "ffprobe":
                    target = str(command[-1]); audio = target.endswith(".wav")
                    streams = [{"codec_type":"audio","channels":1,"codec_name":"pcm_s16le"}] if audio else [{"codec_type":"video","width":1080,"height":1920,"avg_frame_rate":"25/1"}]
                    if target.endswith("final.mp4"): streams.append({"codec_type":"audio","channels":1,"codec_name":"aac"})
                    duration = "15" if audio else "30"
                    return mock.Mock(returncode=0, stdout=json.dumps({"format":{"duration":duration},"streams":streams}), stderr="")
                action = command[2] if len(command)>2 and command[1]=="bridge" else "ffmpeg"
                if action in ("speech-generate", "avatar-drive") or action == "ffmpeg":
                    target = Path(command[-1]); target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(b"output-" + action.encode())
                return mock.Mock(returncode=0, stdout="", stderr="")
            state = {"run_id":"r1", "materials":{"person":{"path":"materials/person.webm"},"voice":{"path":"materials/voice.webm"}},
                     "text":{"reference_transcript":"参考","new_script":"新话术"},
                     "stages":{name:{"status":"pending","error":""} for name in v122_orchestrator.STAGES}, "outputs":{}}
            result = v122_orchestrator.run_pipeline(root, state, FakeAdapter(), "ffmpeg", fake_run)
            speech = next(call for call in calls if "speech-generate" in call)
            drive = next(call for call in calls if "avatar-drive" in call)
            self.assertEqual(speech[-1], drive[-2])
            self.assertTrue((run / "outputs/final.mp4").is_file())
            self.assertEqual(result["stages"]["mp4"]["status"], "passed")

    def test_unexpected_process_error_marks_current_stage_failed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); run = root / "runs/r2/materials"; run.mkdir(parents=True)
            (run / "person.webm").write_bytes(b"person"); (run / "voice.webm").write_bytes(b"voice")
            state = {"run_id":"r2", "materials":{"person":{"path":"materials/person.webm"},"voice":{"path":"materials/voice.webm"}},
                     "text":{"reference_transcript":"参考","new_script":"话术"},
                     "stages":{name:{"status":"pending","error":""} for name in v122_orchestrator.STAGES}, "outputs":{}}
            class Adapter: pass
            def broken(command, **kwargs): raise OSError("process unavailable")
            result = v122_orchestrator.run_pipeline(root, state, Adapter(), "ffmpeg", broken)
            self.assertEqual(result["stages"]["materials"]["status"], "failed")
            self.assertEqual(result["stages"]["materials"]["error"], "V122_MATERIALS_UNEXPECTED")


if __name__ == "__main__":
    unittest.main()
