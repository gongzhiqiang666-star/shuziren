# A07-02 Windows 启动外壳验证

日期：2026-11-14

## 完成范围

- 将环境选择提取为可独立验证的 `resolve_launch_plan`，实际启动仍保持原入口和子进程退出码语义。
- 普通显卡选择 `_internal/env`；识别到 RTX 50 系且 `_internal/env_50/python.exe` 存在时选择 `env_50`；50 系环境不完整时回退普通环境。
- 启动前同时验证所选 `python.exe` 和 `_internal/start.py`，失败时在标准错误中报告确切缺失路径并返回 1。
- `FFMPEG_HOME` 绑定所选环境，存在 `ffmpeg/bin` 时置于子进程 PATH 首位；子进程工作目录固定为 `_internal`。
- 继续对父、子进程请求关闭 Windows 执行速度节流，并原样返回应用子进程退出码。

## 验证结果

- 启动外壳专项 4/4 通过：50 系选择、缺失时回退、缺 Python/start.py 诊断、环境传递及退出码。
- 本机授权运行目录实际解析普通环境为 `_internal/env`，50 系模拟解析为现有 `_internal/env_50`；两个环境的 Python 和共同 `start.py` 均存在。
- 本机 RTX 3060 探测结果为非 50 系，符合硬件实际情况。

Win10/Win11 双系统、无 NVIDIA 显卡和真实 RTX 50 系机器启动仍需要相应整机条件；本轮没有启动原商业 GUI，也不以路径解析替代最终干净安装验收。
