# A07-05 安装诊断快照

日期：2026-11-14

## 实现

`scripts.console_package diagnose --root <安装根目录>` 现在可以生成有界的 JSON 支持快照，一次检查版本选择、数据架构、已安装发布文件完整性、用户数据目录和媒体运行时配置。诊断结果不枚举用户文件，不读取 Token，不回显接口密钥或完整控制台配置。

## 验证

- 新增专项以真实 `token.txt` 敏感值作为负向夹具，确认 JSON 中不出现敏感值或文件名。
- `test_console_package.py` 19/19 通过，覆盖诊断、发布切换、备份恢复、数据架构门禁、店铺隔离和 v122 迁移。
- 对 `logs/validation/a07-release-lifecycle-01` 的已安装生命周期根目录运行真实 CLI，返回 `ready=true`；当前版本、上一版本、架构 1、451 个已安装文件及可写数据目录均通过。该生命周期根未配置媒体运行时，报告如实显示 `configured=false`，不冒充完整媒体包。
- 发布包内的 `packaging/README.md` 已补充诊断命令、可分享范围、非零退出处理和禁止手工改写版本/架构状态的运维说明。
- 高级包可使用 `--require-media` 强制媒体环境门禁。未配置媒体的真实安装根返回 `ready=false` 和退出码 1；将同一已安装版本配置到 `D:\TEMP\shuziren-origin-video-media-01` 后，版本/架构/451 个发布文件/数据目录及 24/24 个高级媒体关键入口通过，返回 `ready=true`。脱敏报告为 `logs/validation/a07-diagnose-media-01.json`。
- 文件布局不等于软件依赖闭合。新增 `--require-media-software` 同时执行文件门禁、精确锁定包、核心环境隔离及 `pip check`，且仅输出聚合计数。正式核心入口使用的 Pandas、PyCUDA 和 Ultralytics 已锁定，快手 ddddocr/headless OpenCV 改为独立工具锁。真实对照环境的核心 40/40 直接版本匹配，但 ddddocr 及另 4 个禁止工具包仍在核心环境，且依赖检查失败，因此诊断正确返回 `ready=false`/退出 1，见 `logs/validation/a07-diagnose-media-software-03.json`。
- 新增 `--wheelhouse` 和 `--wheelhouse-profile core|kuaishou-ocr`，把离线资源解析接入同一支持快照。报告只给出 wheel 文件数、直接锁总数、已有/缺失数和完整解析数量，不回显 pip 的本机路径输出，也不安装任何包。真实生命周期安装根副本配置到独立媒体目录后，以空 wheelhouse 实测返回退出码 1：核心 40 个直接锁已有 0、缺失 40，见 `logs/validation/a07-diagnose-wheelhouse-01.json`。发布诊断 22/22、媒体门禁 17/17 通过。

## 结论

该入口用于运维和客服快速定位安装/升级问题；`--require-media` 只是文件布局门禁，完整高级包必须再通过 `--require-media-software`。当前对照环境仍未软件放行，也不替代干净 Windows、驱动/UAC、物理设备、8 小时长稳或真实平台验收。
