import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ConsoleEntrypointTests(unittest.TestCase):
    def test_direct_file_help_works_outside_repository(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "local_console.py"
        with tempfile.TemporaryDirectory() as working_directory:
            result = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--data-directory", result.stdout)


if __name__ == "__main__":
    unittest.main()
