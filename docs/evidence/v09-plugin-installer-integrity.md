# SYS-011 插件与 OBA 执行完整性

验证日期：2026-11-14

## 随包安装器

`PluginInstallerService` 启动 VB-CABLE、WebView2、.NET 安装器前，现强制执行：

1. 文件必须位于 `assets/plugin` 真实路径之下。
2. 发布包必须包含 `assets/plugin/installer-manifest.json`。
3. 清单必须按相对路径登记正整数大小和 64 位 SHA-256。
4. 实际大小与哈希必须同时相等，之后才允许调用 UAC 提权。

授权 v122 旧运行包没有该清单，所以不会被当成已安全验收的自有发布包。自有打包流程必须从审核通过的安装器生成并随包固化清单；不得在用户机器上对任意现有文件临时生成信任记录。

## OBA Live 工具

- 下载 URL 必须为 HTTPS；仅本机回环测试地址允许 HTTP。
- 配置必须同时提供 `oba_live_installer_sha256`。
- 下载写入 `.download`，校验大小非零及 SHA-256 后才原子替换正式安装器；失败始终清理临时文件。
- 已下载且哈希一致时复用，不重复联网。
- 已安装程序只接受 `%LOCALAPPDATA%/Programs/oba-live-tool`、`%PROGRAMFILES%/oba-live-tool` 或运行目录 `oba-live-tool` 三个根；被篡改的状态文件不能指向任意 EXE。
- 授权参考环境仅配置 HTTPS 下载地址，没有 `oba_live_installer_sha256`；本机也未发现三个批准根中的已安装程序。因此当前实现会在任何网络请求或执行前明确拒绝该旧配置，不能沿用不带摘要的参考下载地址。

## 验证结果

- `tests/test_main_plugins_integrity.py`：4 项通过，覆盖正常清单、缺清单、未登记、篡改、越界及“校验失败绝不提权”。
- `tests/test_oba_integrity.py`：4 项通过，覆盖可信下载/复用、错误/缺失哈希、非 HTTPS、缺摘要时禁止联网、临时文件清理及安装根约束。
- 与更新器完整性测试合计 13 项通过。

真实 UAC、驱动安装/卸载、WebView2/.NET 静默参数、OBA Authenticode 发布签名和安装后启动仍需在自有正式候选包上验证。涉及系统驱动的安装不能在未确认目标机器恢复点和维护窗口时自动执行。
