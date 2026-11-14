# SYS-003 Windows 执行速度节流验证

验证日期：2026-11-14  
环境：Windows，本机随包 Python

## 已验证行为

- 当前进程调用 `SetProcessInformation(ProcessPowerThrottling=4)` 成功，返回 `true`。
- 启动一个受控 Python 子进程后，以 `PROCESS_SET_INFORMATION` 打开其 PID 并设置成功，返回 `true`；测试结束后子进程正常回收。
- `ensure_high_performance(keep_alive=True)` 创建唯一的 `win-power-throttling-keepalive` 后台线程。
- 应用退出路径会设置停止事件、等待线程退出并清空线程引用；停止后可以再次启动新线程。
- `OpenProcess` 返回空句柄时直接报告失败，不再把无效句柄交给 `SetProcessInformation`。
- keep-alive 未在超时内退出时不会伪报成功，应用统一退出结果会记录该错误。

## 自动化证据

- `tests/test_win_power_throttling.py`：4 项通过。
- `tests/test_main_webview_lifecycle.py`：4 项通过，覆盖应用退出调用。
- `scripts/check-recovery-baseline.ps1`：runtime path、package policy、function matrix、recovery、proof tools 五关全部退出 0。

## 尚未扩大证明的范围

- 本轮不证明低权限用户对其他账号或受保护进程具有远程设置权限；权限不足按产品契约返回失败。
- Win10/Win11 多版本及企业组策略环境留在最终整机兼容验收，不阻塞当前一期流程开发。
