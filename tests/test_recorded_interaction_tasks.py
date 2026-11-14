import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.recorded_interaction_tasks import RecordedInteractionError, RecordedInteractionTasks


RUNTIME_FFMPEG = Path(
    r"D:\TEMP\v122-minimum-proof-ready\runtime\yunchuang_v122\_internal\env\ffmpeg\bin\ffmpeg.exe"
)


class RecordedInteractionTasksTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ffmpeg = RUNTIME_FFMPEG
        if not self.ffmpeg.is_file():
            self.skipTest("需要随包 FFmpeg")

    def _media(self):
        source = self.root / "source.mp4"
        reply = self.root / "reply.wav"
        subprocess.run([
            str(self.ffmpeg), "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=25:d=1.6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1.6", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([
            str(self.ffmpeg), "-y", "-f", "lavfi", "-i", "sine=frequency=660:duration=0.35",
            "-c:a", "pcm_s16le", str(reply),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return source, reply

    def _wait(self, manager, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = manager.state()
            if state["status"] != "running":
                return state
            time.sleep(.05)
        self.fail("录播互动任务未在时限内结束")

    def test_real_ffmpeg_task_owns_inputs_and_publishes_verified_output(self):
        source, reply = self._media()
        manager = RecordedInteractionTasks(self.root / "data", self.ffmpeg)
        self.addCleanup(manager.close)
        state = manager.start(source, [{
            "start_ms": 500, "end_ms": 900, "reply_audio": str(reply), "source_id": "reply-1",
        }])
        source.unlink()
        reply.unlink()
        finished = self._wait(manager)
        self.assertEqual(finished["status"], "succeeded", finished)
        output = manager.output(state["id"])
        self.assertGreater(output.stat().st_size, 0)
        self.assertEqual([path.name for path in output.parent.iterdir()], ["result.mp4"])
        output.write_bytes(output.read_bytes() + b"changed")
        with self.assertRaisesRegex(RecordedInteractionError, "已变化"):
            manager.output(state["id"])

    def test_failure_is_recorded_and_owned_files_are_removed(self):
        source, reply = self._media()
        manager = RecordedInteractionTasks(self.root / "data", self.ffmpeg)
        self.addCleanup(manager.close)
        unsupported = self.root / "reply.mp3"
        unsupported.write_bytes(reply.read_bytes())
        with self.assertRaisesRegex(RecordedInteractionError, "仅支持 WAV"):
            manager.start(source, [{
                "start_ms": 100, "end_ms": 400, "reply_audio": str(unsupported), "source_id": "mp3",
            }])
        state = manager.start(source, [{
            "start_ms": 1200, "end_ms": 900, "reply_audio": str(reply), "source_id": "bad",
        }])
        finished = self._wait(manager)
        self.assertEqual(finished["status"], "failed")
        self.assertFalse((manager.root / state["id"]).exists())

    def test_cancel_and_restart_recovery_are_explicit(self):
        source, reply = self._media()

        def blocked_render(_source, _plan, _output, **options):
            while not options["cancel_check"]():
                time.sleep(.01)
            raise InterruptedError("任务已取消")

        with patch("scripts.recorded_interaction_tasks.render_replacements", blocked_render):
            manager = RecordedInteractionTasks(self.root / "data", self.ffmpeg)
            state = manager.start(source, [{
                "start_ms": 100, "end_ms": 400, "reply_audio": str(reply), "source_id": "cancel",
            }])
            manager.cancel(state["id"])
            self.assertEqual(self._wait(manager)["status"], "cancelled")
            manager.close()

        stale_id = "a" * 32
        stale = manager.root / stale_id
        stale.mkdir()
        (stale / "pending.bin").write_bytes(b"pending")
        manager.path.write_text(json.dumps({"id": stale_id, "status": "running"}), encoding="utf-8")
        recovered = RecordedInteractionTasks(self.root / "data", self.ffmpeg)
        self.assertEqual(recovered.state()["status"], "interrupted")
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
