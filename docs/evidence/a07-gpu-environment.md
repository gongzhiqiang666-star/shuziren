# SYS-002 GPU 与环境探测

日期：2026-11-14，Windows 本机。

真实 `nvidia-smi` 返回 NVIDIA GeForce RTX 3060、12288 MiB、驱动 621.14；`main_environment.get_gpu_info()` 独立返回 CUDA 可用、RTX 3060、12.0 GiB、非 50 系、无错误。随包媒体 Python 的 Torch 探针也返回 CUDA 可用、同一设备和 12.0 GiB，两条实现结果一致。

新增 3 项确定性回归覆盖普通 NVIDIA、RTX 5090 的 50 系判定和 `nvidia-smi` 缺失；无 NVIDIA 分支不会声称 CUDA 可用，并保留诊断。真实 RTX 50、无 NVIDIA 物理整机和驱动故障仍需外部机器，不由 mock 分支替代。
