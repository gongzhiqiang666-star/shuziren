# 第一版发布检查表

更新：2026-11-14

| 检查项 | 当前状态 | 证据或下一步 |
| --- | --- | --- |
| 源码包确定性构建 | 通过 | 候选01两次ZIP摘要一致；当前 `3413e2c` 候选02为458文件，完成构建/校验/隔离安装及直接入口启动，见 `evidence/v09-current-package.md` |
| 清单、路径、逐文件哈希 | 通过 | `console_package verify` |
| 全新目录部署和HTTP健康检查 | 通过 | 普通路径及中文/空格路径各一次 |
| 升级、回滚、数据备份与恢复 | 通过 | `evidence/a07-release-lifecycle-real.md` |
| 数据架构不兼容阻断 | 通过 | `evidence/a07-data-schema-gate.md` |
| Windows短时自动回归 | 通过 | 当前全仓实跑 648 项，633 通过、15 项显式环境条件跳过、0 失败，用时 266.535 秒。随后用随包 FFmpeg/运行根补跑其中14项全部通过（手持动作、编码、TTS worker、音频尾部、音色及HTTP导入）；当前随包 SRS 已占用端口，未强停服务，沿用本轮唯一流 API、RTMP 推送、HTTP-FLV 拉取及双轨解码和既有启停/端口释放证据。648 个唯一项均有当前代码或等价真实链证据。长稳、人工质量和外部平台仍单独验收 |
| 独立媒体环境版本锁定 | 门禁完成、环境未通过 | 核心 40/40 直接版本匹配，Pandas/PyCUDA/Ultralytics 明确锁定；快手 ddddocr/headless OpenCV 已分离为独立工具锁。本机无可用完整 wheel 缓存，间接依赖及五个应隔离包已分类，准备受控 wheelhouse 后分别重建并逐引擎实测 |
| 完整模型/FFmpeg/SRS/驱动交付 | 资源与签名门禁通过、对外包待验 | 独立媒体目录24/24关键文件及指纹复核通过，SRS真实推拉流通过；旧参考插件目录被清单规则安全拒绝。构建步骤现强制先执行 `audit-signatures` 再生成/复核哈希清单，四个授权参考文件实审 Valid，但正式包仍须从官方来源重新取得且不得复用参考商业文件；UAC/重启/卸载待干净机验证，见 `evidence/a07-runtime-delivery-audit.md` 与 `evidence/a07-plugin-installer-manifest.md` |
| 轻量3D独立验证包 | 本机验证通过、正式候选待提交后重建 | 29,984,914字节ZIP两次摘要一致，24文件隔离校验及`D:\TEMP`直接启动后Chrome 10/10通过；当前清单诚实标记`source_dirty=true`，每日集中提交后重建干净候选，见`evidence/x10-3d-avatar-baseline.md` |
| 动态口型与KT设备回采 | 待集中验收 | 短时功能已过。KT 实测已向 `OBS Virtual Camera` 发送 175 帧移动 Alpha 商品覆盖，同时从 DirectShow 的 `Tblive Virtual Camera` 成功回采 165 帧并完整解码，但回采为静态灰画面，证明两者不是同一路设备；本机没有 OBS 对应接收端，记录 `logs/validation/a06-kt-device-capture-03/result.json` 后跳过。人工口型画质和匹配驱动下的动态回采后置 |
| 物理设备和真实平台 | 条件缺失 | PnP/DirectShow确认当前只有虚拟视频和虚拟音频端点，无物理摄像头/麦克风；平台账号/房间、UAC干净机仍待提供 |
| 30分钟及8小时稳定性 | 按计划后置 | 第一版流程完成后执行，不阻塞功能开发 |
| 干净Win10/Win11安装卸载 | 待完成 | 最终媒体与驱动包固定后执行 |

放行口径：当前可放行“本机内部第一版源码候选”，不可标记为“完整对外生产安装包”。待完成项不得从功能矩阵删除。
