# main 文件与目录对话框契约

## 原生入口

- `Api.open_file_dialog` wrapper/body：`0x1800393c0 / 0x180039610`
- `Api.open_directory` wrapper/body：`0x18003cb70 / 0x18003ce30`
- 方法签名来自 `main-method-docstrings.json`：
  - `open_file_dialog(self, allow_dir: bool = False) -> Dict[str, Any]`
  - `open_directory(self, unicode path: str) -> Dict[str, Any]`

主体由 Ghidra 12.1.4 工程 `rea-output/ghidra-main/main.gpr` 反编译。字符串槽由
`main-cython-string-table.tsv` 与 `main-state-names.tsv` 交叉确认：

- `0x4d60 webview`
- `0x0c98 OPEN_DIALOG`
- `0x0a08 FOLDER_DIALOG`
- `0x43f8 status`
- `0x45b8 success`
- `0x1de8 cancelled`
- `0x2818 files`
- `0x1900 打开文件对话框失败: `
- `0x1908 目录不存在`
- `0x37e0 os`、`0x3898 path`、`0x2660 exists`
- `0x4608 sys`、`0x38f8 platform`
- `0x4d90 win32`、`0x2150 darwin`
- `0x43d0 startfile`、`0x44d0 subprocess`、`0x0dc0 Popen`
- `0x3788 open`、`0x4e40 xdg-open`

## 恢复出的行为

`open_file_dialog` 对 `allow_dir` 使用普通 Python truthiness，而不是严格布尔检查。它调用
`webview.windows[0].create_file_dialog(...)`，并且不把返回值压缩成单一路径：

- 假值结果：`{"status": "cancelled", "files": []}`
- 真值结果：`{"status": "success", "files": <pywebview 原返回值>}`
- 异常：打印 `打开文件对话框失败: <异常>`，返回 `{"error": str(error)}`

`open_directory` 的 Cython wrapper 严格要求 Unicode 字符串。主体只用 `os.path.exists(path)`
检查存在性，不规范化路径，也不要求目标必须是目录：

- 不存在：`{"error": "目录不存在"}`
- Windows：`os.startfile(path)`
- macOS：`subprocess.Popen(["open", path])`
- 其他平台：`subprocess.Popen(["xdg-open", path])`
- 成功：`{"status": "success"}`
- 异常：`{"error": str(error)}`

## 验证边界

`recovered/verify_recovery.py::verify_main_file_dialog_contract` 隔离验证了选择类型、取消/成功/
异常响应、返回值保真、三个平台分支、中文路径、相对文件路径和严格字符串参数。真实 Windows
文件对话框、中文长路径、Shell 关联程序及权限错误仍需在 Windows 与原 `.pyd` 做差分验证。
