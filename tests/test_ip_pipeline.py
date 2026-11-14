import tempfile
import subprocess
import sys
import time
import unittest
from pathlib import Path

from recovered.ip_pipeline import (StepFileCheckpoint, completed_step_ready,
                                   pipeline_fingerprint, project_pipeline_lock)
from recovered.main import Api


class PipelineApi(Api):
    def __init__(self, root, fail_once=None):
        self.root = Path(root)
        self.project = {
            "id": "p1", "name": "项目", "rewritten_script": "文案",
            "audio_path": str(self.root / "audio.wav"),
            "video_path": str(self.root / "video.mp4"),
            "subtitle_path": str(self.root / "subtitle.srt"),
            "subtitle_video_path": str(self.root / "subtitle.mp4"),
            "final_video_path": str(self.root / "final.mp4"),
        }
        self.calls = []
        self.fail_once = fail_once

    def _load_ip_agent_project(self, project_id):
        return dict(self.project)

    def _save_ip_agent_project(self, project_id, info):
        self.project = dict(info)
        return dict(self.project)

    def get_ip_agent_project(self, project_id):
        return {"status": "success", "project": dict(self.project)}

    def _step(self, name, fields):
        self.calls.append(name)
        for field in fields:
            Path(self.project[field]).write_text(name, encoding="utf-8")
        if self.fail_once == name:
            self.fail_once = None
            return {"status": "error", "message": f"{name} failed"}
        self.project["publish_title"] = "标题" if name == "publish_meta" else self.project.get("publish_title")
        return {"status": "success", "project": dict(self.project)}

    def generate_audio_for_ip_agent_project(self, project_id, data): return self._step("audio", ("audio_path",))
    def create_ip_agent_video(self, project_id, data): return self._step("video", ("video_path",))
    def add_subtitles_to_ip_agent_video(self, project_id, data): return self._step("subtitles", ("subtitle_path", "subtitle_video_path"))
    def apply_ip_agent_finishing(self, project_id, data): return self._step("finishing", ("final_video_path",))
    def generate_ip_agent_publish_meta(self, project_id, data): return self._step("publish_meta", ())


class IpPipelineTests(unittest.TestCase):
    def test_project_lock_serializes_other_process_and_recovers_after_exit(self):
        project_id = "cross-process-test"
        code = (
            "import time; from recovered.ip_pipeline import project_pipeline_lock; "
            f"lock=project_pipeline_lock({project_id!r}); lock.__enter__(); "
            "print('ready',flush=True); time.sleep(.8); lock.__exit__(None,None,None)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "ready")
            started = time.monotonic()
            with project_pipeline_lock(project_id):
                waited = time.monotonic() - started
            self.assertGreaterEqual(waited, .5)
            process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0)
            started = time.monotonic()
            with project_pipeline_lock(project_id):
                pass
            self.assertLess(time.monotonic() - started, .3)

            crash = subprocess.Popen(
                [sys.executable, "-c", code.replace("time.sleep(.8)", "time.sleep(30)")],
                cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(crash.stdout.readline().strip(), "ready")
            crash.kill()
            crash.communicate(timeout=3)
            started = time.monotonic()
            with project_pipeline_lock(project_id):
                pass
            self.assertLess(time.monotonic() - started, .3)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()

    def test_fingerprint_is_stable_and_changes_with_input(self):
        project = {"name": "项目", "rewritten_script": "文案"}
        first = pipeline_fingerprint("p1", {"voice": "a"}, project)
        self.assertEqual(first, pipeline_fingerprint("p1", {"voice": "a"}, project))
        self.assertNotEqual(first, pipeline_fingerprint("p1", {"voice": "b"}, project))
        before = pipeline_fingerprint("p1", {"text": "新文案", "voice_id": "v1"}, project)
        project.update({"rewritten_script": "新文案", "voice_id": "v1", "language": "zh-CN"})
        self.assertEqual(before, pipeline_fingerprint("p1", {"text": "新文案", "voice_id": "v1"}, project))

    def test_file_checkpoint_restores_old_output_and_removes_new_output(self):
        with tempfile.TemporaryDirectory() as root:
            old = Path(root) / "old.wav"; old.write_text("old", encoding="utf-8")
            new = Path(root) / "new.srt"
            checkpoint = StepFileCheckpoint({"subtitle_path": str(old), "subtitle_video_path": str(new)}, "subtitles")
            old.write_text("changed", encoding="utf-8"); new.write_text("partial", encoding="utf-8")
            self.assertEqual(checkpoint.rollback(), [])
            self.assertEqual(old.read_text(encoding="utf-8"), "old")
            self.assertFalse(new.exists())

    def test_next_checkpoint_recovers_files_left_by_crashed_process(self):
        with tempfile.TemporaryDirectory() as root:
            old = Path(root) / "old.wav"; old.write_text("old", encoding="utf-8")
            new = Path(root) / "new.srt"
            project = {"subtitle_path": str(old), "subtitle_video_path": str(new)}
            payload = repr(project)
            code = (
                "import os; from pathlib import Path; "
                "from recovered.ip_pipeline import StepFileCheckpoint; "
                f"p={payload}; StepFileCheckpoint(p,'subtitles'); "
                "Path(p['subtitle_path']).write_text('corrupt',encoding='utf-8'); "
                "Path(p['subtitle_video_path']).write_text('partial',encoding='utf-8'); os._exit(9)"
            )
            crashed = subprocess.run([sys.executable, "-c", code],
                                     cwd=Path(__file__).resolve().parents[1])
            self.assertEqual(crashed.returncode, 9)
            checkpoint = StepFileCheckpoint(project, "subtitles")
            self.assertEqual(old.read_text(encoding="utf-8"), "old")
            self.assertFalse(new.exists())
            checkpoint.close()

    def test_failure_is_persisted_and_next_call_resumes_after_completed_steps(self):
        with tempfile.TemporaryDirectory() as root:
            api = PipelineApi(root, fail_once="subtitles")
            first = api.one_click_create_ip_agent_video("p1", {"voice": "a"})
            self.assertEqual(first["failed_step"], "subtitles")
            self.assertTrue(first["resumable"])
            self.assertEqual(api.project["one_click_pipeline"]["completed_steps"], ["audio", "video"])
            self.assertFalse(Path(api.project["subtitle_path"]).exists())
            second = api.one_click_create_ip_agent_video("p1", {"voice": "a"})
            self.assertEqual(second["status"], "success")
            self.assertEqual(api.calls, ["audio", "video", "subtitles", "subtitles", "finishing", "publish_meta"])
            third = api.one_click_create_ip_agent_video("p1", {"voice": "a"})
            self.assertTrue(third["already_complete"])


if __name__ == "__main__":
    unittest.main()
