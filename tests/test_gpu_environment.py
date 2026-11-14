import subprocess
import unittest
from unittest import mock

from recovered import main_environment


class GpuEnvironmentTests(unittest.TestCase):
    def test_standard_nvidia_gpu_reports_memory_and_uses_normal_environment(self):
        completed = subprocess.CompletedProcess(
            [], 0, stdout="NVIDIA GeForce RTX 3060, 12288\n", stderr=""
        )
        with mock.patch.object(main_environment.subprocess, "run", return_value=completed):
            info = main_environment.get_gpu_info()
        self.assertEqual(info, {
            "cuda_available": True,
            "device_name": "NVIDIA GeForce RTX 3060",
            "total_vram_gb": 12.0,
            "is_50_series": False,
            "error": None,
        })

    def test_rtx_50_series_is_detected(self):
        completed = subprocess.CompletedProcess(
            [], 0, stdout="NVIDIA GeForce RTX 5090, 32768\n", stderr=""
        )
        with mock.patch.object(main_environment.subprocess, "run", return_value=completed):
            self.assertTrue(main_environment.get_gpu_info()["is_50_series"])

    def test_missing_nvidia_command_returns_diagnostic_without_claiming_cuda(self):
        with mock.patch.object(
            main_environment.subprocess, "run", side_effect=FileNotFoundError("nvidia-smi missing")
        ):
            info = main_environment.get_gpu_info()
        self.assertFalse(info["cuda_available"])
        self.assertIsNone(info["device_name"])
        self.assertEqual(info["total_vram_gb"], 0)
        self.assertIn("nvidia-smi missing", info["error"])


if __name__ == "__main__":
    unittest.main()
