# A07-05 运行资源与设备交付审计

日期：2026-11-14

## 本机已验证范围

- 对独立媒体目录 `D:\TEMP\shuziren-origin-video-media-01` 执行包含原视频直驱组件的 `media_runtime check`，环境 3 项、模型 17 项、提供方 2 项、原视频直驱 2 项，共 24/24 个关键入口存在，结果 `ready=true`。
- 随后生成仓库外指纹清单并立即执行 `verify`，24/24 个文件重新计算摘要后完全一致，`verified=true`、`mismatches=[]`。清单位于忽略目录 `logs/validation/a07-media-inventory-01.json`，模型、运行环境和摘要清单均不提交仓库。
- 独立媒体目录 FFmpeg 可执行文件存在；随包 SRS 报告版本 `5.0.213`。A07-04 已使用同一 SRS 完成真实推拉流，用显式真实环境补跑的 13 项全部通过。

以上证明本机对照媒体目录的关键文件集合完整且迁移前后可校验，不等于软件依赖已经发布放行。`a07-media-software-gate.md` 记录的 `pip check` 冲突仍使完整媒体软件门禁为未通过。

## 旧参考包插件目录结论

只读验证 `v122` 授权参考包的 `assets/plugin` 未通过自有发布清单规则。该目录没有自有 `installer-manifest.json`，并包含 Chrome 安装器、OBS 虚拟摄像头工具、VB-CABLE 控制面板以及 macOS 资源分叉文件等额外 EXE。验证器在任何 UAC 或安装动作前明确拒绝，退出码为 1。

这不是要求修改参考包。最终自有发布目录只能从官方来源单独准备 WebView2、VB-CABLE x64、.NET 8 和 .NET 9 四个批准安装器，审查 Authenticode 后生成清单；不得直接复用整个旧插件目录。真实 UAC、重启后设备发现和卸载仍留待干净 Windows 验收。

## 物理设备条件

DirectShow 当前只列出软件设备 `C920 (none)`、`Tblive Virtual Camera (video)` 和 `CABLE Output (audio)`。PnP 的 Camera/Image 类没有在场设备，音频输入只有 VB-Audio 虚拟端点；未发现物理摄像头或物理麦克风。

因此虚拟摄像头和虚拟声卡短测可以继续作为功能证据，但不得冒充物理设备验收。物理摄像头、物理麦克风、热插拔和真实采集画质记录为条件缺失，接入硬件后补验，不阻塞后续功能开发。

## 放行判断

- 本机内部源码候选：运行资源关键入口与指纹校验通过，可继续使用。
- 对外完整安装包：不放行。仍需闭合媒体依赖环境、准备自有签名驱动安装器、完成干净 Windows UAC/重启/卸载和物理设备验证。
