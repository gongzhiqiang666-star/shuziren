# A07-02 插件安装包清单构建验证

日期：2026-11-14

## 完成范围

- 新增 `scripts.plugin_installer_manifest`，在仓库外的最终 `assets/plugin` 目录生成和复核安装器清单。
- 仅接受现有产品入口对应的 WebView2、VB-CABLE、.NET 8 和 .NET 9 四个固定相对路径。
- 构建时拒绝额外 EXE、符号链接/重解析点、空文件及超过 1 GiB 的文件。
- 清单记录版本、算法、逐文件大小和 SHA-256，以同目录暂存、`fsync` 和原子替换发布。
- `verify` 重新枚举实际文件并计算摘要，拒绝文件篡改、清单替换或清单与目录不一致。
- 安装执行端原有 `_verify_bundled_installer` 仍在提权前逐文件复核，构建端与执行端形成闭环。
- 构建前新增 `audit-signatures`：Windows Authenticode 必须为 `Valid`，WebView2/.NET 发布者必须包含 `Microsoft Corporation`，VB-CABLE 必须包含 `BUREL VINCENT`；签名主体和证书指纹只输出审计结果，不把安装器写入仓库。
- 审计固定调用系统 Windows PowerShell 及 Security 模块，显式隔离媒体 Python 继承的 `PSModulePath`；真实复测曾因此无法自动加载签名命令，修复后同环境通过。

安装器二进制不进入仓库。清单生成证明待发布目录内字节在构建后未变化，签名审计证明当前字节具备有效 Authenticode 且发布者名称符合白名单；来源下载地址、版本选型和证书轮换仍须由发布维护者从官方渠道独立审查。

## 验证结果

- 清单构建/签名专项：6/6 通过，覆盖两个合法文件、篡改、额外 EXE、清单替换、链接逃逸、有效发布者及无签名拒绝。
- 安装执行端完整性专项：4/4 通过，覆盖清单缺失、未登记、摘要变化、目录逃逸和校验后才提权。
- `D:\TEMP\shuziren-plugin-signature-audit-01` 对授权参考包四个目标安装器的只读副本实审通过：WebView2 和 .NET 8/9 为 Microsoft 发布者，VB-CABLE 为 BUREL VINCENT，四项状态均为 `Valid`。该目录不进入仓库，也不代表允许再分发。
- Python 编译与 `git diff --check` 通过。

本项完成插件安装器清单和构建期签名/发布者门禁。正式自有候选仍须从官方来源重新取得安装器并再次审计；UAC 安装、重启后设备/运行库发现、卸载及干净 Windows 整机流程保留至 A07-05。
