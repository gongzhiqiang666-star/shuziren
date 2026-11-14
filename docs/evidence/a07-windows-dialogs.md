# SYS-008 Windows 原生对话框验证

验证日期：2026-11-14
环境：Windows，本机随包 Python、pywebview

## 已验证行为

- 文件选择和目录选择均真实创建 Windows 原生 `#32770` 对话框。
- 验证器的自动取消只枚举当前验证进程拥有且可见的原生对话框；必须恰好找到一个才发送 `WM_CLOSE`，不会关闭其他应用窗口。
- 文件与目录两种模式关闭后均返回 `cancelled` 和空文件列表，pywebview 窗口及验证进程正常退出。

## 证据

- 可重复工具：`scripts/validate_windows_dialogs.py --auto-cancel`。
- 结构化结果：`logs/validation/a07-windows-dialogs-02/file-cancel.json`、`folder-cancel.json`。
- 两次结果分别记录系统对话框句柄和所属验证进程 PID，状态均为 `cancelled`。

## 尚未完成

- 中文、空格和长路径的实际文件/目录选择。
- 选择后调用 Shell 打开目录、关联程序以及权限错误的真实行为。
- 原 `.pyd` 相同输入的返回结构差分。

以上缺口继续列入 E01；当前证据只提升取消子路径，不把 SYS-008 整项标记为 Windows 验证通过。
