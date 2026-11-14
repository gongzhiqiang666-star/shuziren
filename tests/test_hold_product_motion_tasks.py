import json
import tempfile
import threading
import unittest
import wave
import subprocess
import shutil
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.hold_product_motion_tasks import (
    HoldProductMotionError,
    HoldProductMotionTasks,
    _find_ffprobe,
    _probe_motion_video,
)


class HoldProductMotionTasksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image = self.root / "held.png"
        Image.new("RGB", (64, 96), "green").save(self.image)
        self.audio = self.root / "speech.wav"
        with wave.open(str(self.audio), "wb") as sound:
            sound.setparams((1, 2, 24000, 24000, "NONE", ""))
            sound.writeframes(bytes(48000))

    def tearDown(self):
        self.temporary.cleanup()

    def test_plan_and_success_keep_key_out_of_record(self):
        manager = HoldProductMotionTasks(self.root / "data", __file__)
        plan = manager.plan(image=self.image, audio=self.audio, resolution="720p", fps=25)
        self.assertEqual((plan["engine"], plan["max_res"], plan["instance_type"]),
                         ("ltx", 1280, "plus"))

        def generate(**kwargs):
            Path(kwargs["dest"]).write_bytes(b"\x00\x00\x00\x18ftypmp42motion")
            return {"video_path": str(kwargs["dest"]), "task_id": "provider-1"}

        media = {"duration_s": 1.0, "width": 720, "height": 1280, "codec": "h264"}
        with (patch("scripts.hold_product_motion_tasks.generate_ltx_video", side_effect=generate),
              patch("scripts.hold_product_motion_tasks._probe_motion_video", return_value=media)):
            state = manager.start(api_key="request-only-secret", image=self.image, audio=self.audio)
            manager.thread.join(5)
        state = manager.state()
        self.assertEqual(state["status"], "succeeded")
        self.assertEqual(state["media"], media)
        self.assertEqual(manager.output(state["id"]).read_bytes(), b"\x00\x00\x00\x18ftypmp42motion")
        self.assertNotIn("request-only-secret", manager.path.read_text(encoding="utf-8"))
        manager.output(state["id"]).write_bytes(b"changed")
        with self.assertRaisesRegex(HoldProductMotionError, "已变化"):
            manager.output(state["id"])

    def test_concurrent_cancel_and_restart_interruption(self):
        manager = HoldProductMotionTasks(self.root / "data", __file__)
        entered = threading.Event()

        def generate(**kwargs):
            entered.set()
            while not kwargs["cancel_check"]():
                threading.Event().wait(.01)
            raise InterruptedError("cancelled")

        with patch("scripts.hold_product_motion_tasks.generate_ltx_video", side_effect=generate):
            state = manager.start(api_key="key", image=self.image, audio=self.audio)
            self.assertTrue(entered.wait(2))
            with self.assertRaisesRegex(HoldProductMotionError, "已有"):
                manager.start(api_key="key", image=self.image, audio=self.audio)
            manager.cancel(state["id"])
            manager.thread.join(5)
        self.assertEqual(manager.state()["status"], "cancelled")
        self.assertFalse((manager.root / state["id"]).exists())

        manager.task = {"id": "orphan", "status": "running", "output": None}
        manager._save()
        (manager.root / "orphan").mkdir()
        recovered = HoldProductMotionTasks(self.root / "data")
        self.assertEqual(recovered.state()["status"], "interrupted")
        self.assertFalse((recovered.root / "orphan").exists())

    def test_invalid_inputs_fail_before_provider(self):
        manager = HoldProductMotionTasks(self.root / "data", __file__)
        with self.assertRaisesRegex(HoldProductMotionError, "手持商品图无效"):
            manager.plan(image=self.root / "missing.png", audio=self.audio)
        with self.assertRaisesRegex(HoldProductMotionError, "帧率"):
            manager.plan(image=self.image, audio=self.audio, fps=0)
        record = manager.root / "task.json"
        record.write_text(json.dumps({"status": "unknown"}), encoding="utf-8")
        with self.assertRaisesRegex(HoldProductMotionError, "记录损坏"):
            HoldProductMotionTasks(self.root / "data")

    def test_changed_input_during_snapshot_does_not_publish_task(self):
        manager = HoldProductMotionTasks(self.root / "data", __file__)
        original = __import__("shutil").copyfile

        def changing_copy(source, target):
            result = original(source, target)
            if Path(source) == self.image:
                Path(target).write_bytes(b"changed-after-plan")
            return result

        with patch("scripts.hold_product_motion_tasks.shutil.copyfile", side_effect=changing_copy):
            with self.assertRaisesRegex(HoldProductMotionError, "发生变化"):
                manager.start(api_key="key", image=self.image, audio=self.audio)
        self.assertIsNone(manager.state())
        self.assertFalse(manager.path.exists())

    def test_invalid_provider_media_fails_and_is_removed(self):
        manager = HoldProductMotionTasks(self.root / "data", __file__)

        def generate(**kwargs):
            Path(kwargs["dest"]).write_bytes(b"not-a-video")
            return {"video_path": str(kwargs["dest"]), "task_id": "provider-bad"}

        with (patch("scripts.hold_product_motion_tasks.generate_ltx_video", side_effect=generate),
              patch("scripts.hold_product_motion_tasks._probe_motion_video",
                    side_effect=HoldProductMotionError("手持商品动作视频无法完整解析"))):
            state = manager.start(api_key="key", image=self.image, audio=self.audio)
            manager.thread.join(5)
        state = manager.state()
        self.assertEqual(state["status"], "failed")
        self.assertIn("无法完整解析", state["error"])
        self.assertIsNone(state["output"])
        self.assertFalse((manager.root / state["id"]).exists())

    def test_real_ffprobe_rejects_text_and_accepts_video(self):
        probe = _find_ffprobe()
        if not probe:
            self.skipTest("Explicit real FFprobe required")
        probe_path = Path(probe)
        ffmpeg = probe_path.with_name("ffmpeg" + probe_path.suffix) if probe_path.parent != Path('.') else Path(shutil.which("ffmpeg") or "")
        if not ffmpeg.is_file():
            self.skipTest("Matching real FFmpeg required")
        video = self.root / "motion.mp4"
        subprocess.run([
            str(ffmpeg), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
            "color=c=green:s=96x128:r=25:d=0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(video),
        ], check=True, timeout=30)
        media = _probe_motion_video(video, probe)
        self.assertEqual((media["width"], media["height"], media["codec"]), (96, 128, "h264"))
        self.assertGreaterEqual(media["duration_s"], .39)
        invalid = self.root / "invalid.mp4"
        invalid.write_text("not video", encoding="utf-8")
        with self.assertRaisesRegex(HoldProductMotionError, "无法完整解析"):
            _probe_motion_video(invalid, probe)


if __name__ == "__main__":
    unittest.main()
