from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recovered import launcher_temp


class LauncherTests(unittest.TestCase):
    def layout(self, *, default=True, gpu50=False):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        executable = root / "yunchuang_v122.exe"
        executable.write_bytes(b"launcher")
        internal = root / "_internal"
        internal.mkdir()
        (internal / "start.py").write_text("pass\n", encoding="utf-8")
        for enabled, name in ((default, "env"), (gpu50, "env_50")):
            if enabled:
                directory = internal / name
                directory.mkdir()
                (directory / "python.exe").write_bytes(b"python")
        return temporary, executable

    def test_selects_gpu50_and_falls_back_to_default(self):
        temporary, executable = self.layout(gpu50=True)
        with temporary:
            plan = launcher_temp.resolve_launch_plan(executable, gpu_50=True)
            self.assertEqual(plan["environment"], "env_50")
        temporary, executable = self.layout()
        with temporary:
            plan = launcher_temp.resolve_launch_plan(executable, gpu_50=True)
            self.assertEqual(plan["environment"], "env")

    def test_missing_runtime_or_start_script_is_diagnostic(self):
        temporary, executable = self.layout(default=False)
        with temporary, self.assertRaisesRegex(FileNotFoundError, r"env\\python.exe"):
            launcher_temp.resolve_launch_plan(executable, gpu_50=False)
        temporary, executable = self.layout()
        with temporary:
            (executable.parent / "_internal/start.py").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "start.py"):
                launcher_temp.resolve_launch_plan(executable, gpu_50=False)

    def test_main_passes_environment_and_child_exit_code(self):
        temporary, executable = self.layout()
        process = unittest.mock.Mock(pid=1234)
        process.wait.return_value = 17
        with temporary, patch.object(launcher_temp.sys, "executable", str(executable)), \
                patch.object(launcher_temp, "get_gpu_info", return_value=False), \
                patch.object(launcher_temp, "disable_execution_speed_throttling") as power, \
                patch.object(launcher_temp.subprocess, "Popen", return_value=process) as spawn:
            self.assertEqual(launcher_temp.main(), 17)
        command = spawn.call_args.args[0]
        self.assertEqual(Path(command[0]).name, "python.exe")
        self.assertEqual(Path(command[1]).name, "start.py")
        self.assertTrue(spawn.call_args.kwargs["env"]["FFMPEG_HOME"].endswith("env\\ffmpeg"))
        self.assertEqual(power.call_count, 2)

    def test_main_reports_launch_failure(self):
        temporary, executable = self.layout(default=False)
        error = io.StringIO()
        with temporary, patch.object(launcher_temp.sys, "executable", str(executable)), \
                patch.object(launcher_temp, "get_gpu_info", return_value=False), redirect_stderr(error):
            self.assertEqual(launcher_temp.main(), 1)
        self.assertIn("启动文件缺失", error.getvalue())


if __name__ == "__main__":
    unittest.main()
