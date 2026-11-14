import unittest
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import nullcontext
import sys
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

from recovered.record_live_manager import RecordLiveManager
from recovered.record_live_manager import _mix_real_shot_audio
from recovered.record_live_manager import _mux_real_shot_video


class _Resource:
    def __init__(self, error=None):
        self.error = error
        self.stops = 0

    def stop(self):
        self.stops += 1
        if self.error:
            raise self.error


class RecordLiveLifecycleTests(unittest.TestCase):
    def test_player_failure_does_not_skip_ingest_or_announcement_cleanup(self):
        manager = RecordLiveManager({})
        player = _Resource(OSError("player close failed"))
        ingest = _Resource()
        manager.video_player = player
        manager.stream_ingest = ingest
        manager.is_broadcasting = True
        manager.announcement_session = {
            "is_active": True,
            "temp_files": [],
            "worker_thread": object(),
        }

        self.assertFalse(manager.stop_live())

        self.assertEqual(player.stops, 1)
        self.assertEqual(ingest.stops, 1)
        self.assertFalse(manager.announcement_session["is_active"])
        self.assertIsNone(manager.video_player)
        self.assertIsNone(manager.stream_ingest)
        self.assertFalse(manager.is_broadcasting)
        self.assertEqual(
            manager.last_error,
            "停止录播直播时发生错误: player close failed",
        )

    def test_inactive_broadcast_still_cleans_active_announcement(self):
        manager = RecordLiveManager({})
        manager.is_broadcasting = False
        manager.announcement_session = {
            "is_active": True,
            "temp_files": [],
            "worker_thread": object(),
        }

        self.assertTrue(manager.stop_live())
        self.assertFalse(manager.announcement_session["is_active"])
        self.assertIsNone(manager.announcement_session["worker_thread"])

    def test_corrupt_local_video_fails_before_broadcast_success(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "broken.mp4"
            source.write_bytes(b"not-a-video")
            manager = RecordLiveManager({})

            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = manager.start_live(str(source), output_mode="vcam")

            self.assertFalse(result)
            self.assertIn("视频源解码失败", manager.last_error)
            self.assertFalse(manager.is_broadcasting)
            self.assertIsNone(manager.video_player)

    def test_cancelled_announcement_removes_late_output(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            narration = root / "narration.wav"
            source.write_bytes(b"source")
            narration.write_bytes(b"narration")
            manager = RecordLiveManager({})
            owner = object()
            manager.announcement_session = {
                "is_active": True,
                "temp_files": [],
                "worker_thread": owner,
            }
            outputs = []

            def synthesize(**_kwargs):
                manager.announcement_session["is_active"] = False
                manager.announcement_session["worker_thread"] = None
                return str(narration)

            def mux(_video, _audio, output, _startupinfo=None):
                Path(output).write_bytes(b"late-output")
                outputs.append(Path(output))

            mixed = SimpleNamespace(export=lambda *_args, **_kwargs: nullcontext())
            audio_segment = SimpleNamespace(
                from_wav=lambda _path: object(),
                from_file=lambda _path: object(),
            )
            manager._synthesize_local_audio = synthesize
            with patch.dict(sys.modules, {"pydub": SimpleNamespace(AudioSegment=audio_segment)}), patch(
                    "recovered.record_live_manager._extract_real_shot_audio"), patch(
                    "recovered.record_live_manager._mix_real_shot_audio", return_value=mixed), patch(
                    "recovered.record_live_manager._mux_real_shot_video", side_effect=mux):
                manager._process_real_shot_task(
                    str(source), 0, 1, {"voice_id": "test", "audio_text": "test"}
                )

            self.assertEqual(len(outputs), 1)
            self.assertFalse(outputs[0].exists())
            self.assertEqual(manager.announcement_session["temp_files"], [])

    def test_announcement_interval_is_validated_before_worker_start(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.mp4"
            source.write_bytes(b"source")
            manager = RecordLiveManager({})
            manager.video_player = object()
            manager.is_broadcasting = True

            result = manager.prepare_announcement({
                "real_shot": {
                    "video_path": str(source),
                    "audio_replace_start": 2,
                    "audio_replace_end": 1,
                }
            })

            self.assertEqual(result["status"], "error")
            self.assertIn("结束时间必须大于开始时间", result["message"])
            self.assertFalse(manager.announcement_session["is_active"])
            self.assertIsNone(manager.announcement_session["worker_thread"])

    def test_audio_replacement_is_clamped_to_original_timeline(self):
        from pydub import AudioSegment

        original = AudioSegment.silent(duration=1000, frame_rate=44100)
        narration = AudioSegment.silent(duration=500, frame_rate=44100)
        mixed = _mix_real_shot_audio(original, narration, 0.8, 2.0)

        self.assertEqual(len(mixed), len(original))
        with self.assertRaisesRegex(ValueError, "位于原音轨内"):
            _mix_real_shot_audio(original, narration, 2.0, 3.0)

    def test_announcement_mux_stops_at_original_video_timeline(self):
        completed = Mock(returncode=0)
        with patch(
                "recovered.record_live_manager.subprocess.run",
                return_value=completed) as run:
            _mux_real_shot_video("video.mp4", "mixed.wav", "output.mp4")

        command = run.call_args.args[0]
        self.assertIn("-shortest", command)
        self.assertLess(command.index("-shortest"), command.index("output.mp4"))


if __name__ == "__main__":
    unittest.main()
