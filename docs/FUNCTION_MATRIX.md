# yunchuang_v122 权威功能矩阵

更新日期：2026-11-10

本文件是功能范围、开发顺序和最终验收的权威清单。它描述的是用户能够使用的产品能力，不以 `.pyd` 数量或函数数量代替功能完成度。

## 状态定义

- **未分析**：尚无足够证据确认完整行为。
- **已分析**：已找到入口、主要依赖和调用链，但实现或测试尚不完整。
- **开发中**：已有恢复/重建代码，仍有明确行为缺口。
- **静态验证通过**：源码、反编译证据和隔离测试相互印证；不代表 Windows 生产可用。
- **Windows 验证通过**：已在 Windows 上与原程序做关键接口或流程差分验证。
- **端到端验证通过**：已在目标硬件、真实平台和真实业务场景完成验收。

除“端到端验证通过”外，任何状态都不能解释为功能最终完成。`recovered/verify_recovery.py` 的 `128/128 PASS` 证明第一方模块映射、可导入性、签名和选定行为，不证明所有用户流程已经生产验收。

## P0：启动、配置与产品外壳

| ID | 用户功能 | 原入口/主要证据 | 当前重建模块 | 当前状态 | 完成前必须验证 |
|---|---|---|---|---|---|
| SYS-001 | Windows 一键启动与环境选择 | `launcher_temp`、PYZ 95 模块 | `recovered/launcher_temp.py` | 静态验证通过 | Win10/11 双环境启动、无 GPU、RTX 50 系分支、子进程退出码 |
| SYS-002 | GPU/显存探测及运行环境初始化 | `main._initialize_environment` | `main_environment.py`, `gpu_probe.py` | 静态验证通过 | NVIDIA/无 NVIDIA/命令失败三类 Windows 实机 |
| SYS-003 | 关闭 Windows 执行速度节流 | `win_power_throttling.pyd` Ghidra 证据 | `win_power_throttling.py` | 静态验证通过 | Windows API 权限、远程 PID、keep-alive 生命周期 |
| SYS-004 | 系统配置、用户配置合并与私密配置迁移 | `main.pyd` 配置调用链 | `main_config.py` | 静态验证通过 | `%LOCALAPPDATA%` 路径、旧配置迁移、异常断电原子写入 |
| SYS-005 | pywebview 主窗口及前后端 JS API | `main.main/_main/run_webview` | `main_webview.py`, `main.py` | 已分析 | Windows WebView2、生产/开发 URL、窗口关闭资源回收 |
| SYS-006 | 登录 Token、管理员/OEM 信息与背景资源 | Token `0x1800644b0/0x180064620`, `0x180064dd0/0x180065090`, `0x180065880/0x1800659f0`; 管理员/OEM/背景/版本原生主体 | `main.py` | 静态验证通过 | Windows 原 `.pyd`、真实旧配置/OEM 包和前端登录流差分 |
| SYS-007 | 本地资源枚举、预览与删除 | main wrapper/body `get_local_resources` `0x1800b9320/0x1800b9490`、`delete_model` `0x1800b7980/0x1800b7c40`、`delete_voice` `0x1800b8650/0x1800b8910`；CloneManager 枚举/信息写入/预览主体见 `rea-output/main-local-resources-notes.md` | `main.py`, `clone_manager.py` | 静态验证通过 | Windows 原 `.pyd` 响应差分、旧生产资源样本、文件占用/权限错误和删除后前端刷新 |
| SYS-008 | 文件/目录选择及打开目录 | `open_file_dialog/open_directory` wrapper/body `0x1800393c0/0x180039610`、`0x18003cb70/0x18003ce30`，见 `rea-output/main-file-dialog-notes.md` | `main.py` | 静态验证通过 | Windows 原 `.pyd` 响应差分、真实对话框、中文/长路径、Shell 关联程序及权限错误 |
| SYS-009 | 缓存清理 | `Api.clear_cache` | `main.py`, `audio_cache.py` | 已分析 | 正在直播、文件占用、部分清理失败 |
| SYS-010 | 应用更新状态、下载/启动更新器 | `get_update_status/start_app_update` | `main.py`, `update_integrity.py`, `update_text.py` | 已分析 | Windows 更新器、签名/完整性、失败回滚、进程退出 |
| SYS-011 | 插件安装与 OBA Live 工具 | `PluginInstallerService`、`launch_oba_live_tool` | `main.py`, `main_plugins.py` | 已分析 | 安装权限、下载失败、已安装发现和启动 |
| SYS-012 | Windows 安装包及可复现打包 | 原 PyInstaller 交付结构 | 依赖清单已恢复 | 已分析 | 从干净 Windows 构建、安装、卸载、升级和离线运行 |

## P0：项目、文案与内容生产

| ID | 用户功能 | 原入口/主要证据 | 当前重建模块 | 当前状态 | 完成前必须验证 |
|---|---|---|---|---|---|
| CNT-001 | LLM 配置保存和连通性测试 | `save_llm_config` `0x180068800/0x180068ac0`; `test_llm_availability` `0x180057640/0x180057900` | `main.py`, `llm_base_chat.py` | 静态验证通过 | Windows 原 `.pyd` 差分及各真实提供商鉴权/超时 |
| CNT-002 | 商品直播话术生成 | `generate_script` wrapper/body `0x180036950/0x180037230` | `main.py`, `generate_structured_speech.py` | 静态验证通过 | Windows 原 `.pyd` 差分和真实 LLM 输出质量 |
| CNT-003 | 文本翻译与多语言提示词 | `translate_text` wrapper/body `0x18004f510/0x18004f8c0` | `main.py`, `llm_reply.py`, `language_prompts.py` | 静态验证通过 | Windows 原 `.pyd` 差分、全语言真实模型输出质量 |
| CNT-004 | 话术泛化与标题生成 | `generalize_sentences_api` 及 Ghidra 契约 | `generalize_sentences.py`, `generate_title.py` | 静态验证通过 | 真实 LLM 差分、异常输出和重试 |
| CNT-005 | 违禁词检测/替换 | `forbidden_words.pyd`、`replace_forbidden_words.pyd` | `forbidden_words.py`, `replace_forbidden_words.py` | 静态验证通过 | 原词库、用户增补词、大小写/中英文边界 |
| CNT-006 | IP Agent 项目创建、查询、更新、删除 | `Api.create/get/update/delete_ip_agent_project` | `main.py`, `ip_agent_post_process.py` | 静态验证通过 | 旧项目迁移、并发保存、损坏项目恢复 |
| CNT-007 | IP 文案爆款拆解与多版本改写 | `rewrite_ip_script` 主体和常量表 | `main.py` | 静态验证通过 | Windows 原 `.pyd` 输出差分和真实 LLM 输出 |
| CNT-008 | 抖音/IP 对标视频提取 | `extract_douyin_benchmark` | `main.py` | 已分析 | Windows 下载工具、登录/风控、失效链接和媒体格式 |
| CNT-009 | IP 发布标题、简介、标签生成 | `generate_ip_agent_publish_meta` wrapper/body `0x180142690/0x180142a40` | `main.py`, `generate_title.py` | 静态验证通过 | Windows 原 `.pyd` 差分和真实 LLM 输出质量 |
| CNT-010 | IP 一键成片流水线 | 音频→视频→字幕→精加工→发布 API | `main.py`, `ip_agent_post_process.py` | 开发中 | 全链真实媒体、断点恢复、失败清理和结果一致性 |
| CNT-011 | IP 视频发布 | `publish_ip_agent_video` | `main.py` | 已分析 | 支持平台、账号登录、草稿/发布、失败重试 |
| CNT-012 | 直播贴片项目管理 | main CRUD/helper wrapper/body 与 26 字段 YAML、五类固定输出、历史归档及旧项目迁移证据，见 `rea-output/main-live-sticker-project-notes.md` | `main.py` | 静态验证通过 | Windows 原 `.pyd` 响应差分、真实旧项目、连续生成归档、文件占用/权限错误和前端预览 |
| CNT-013 | 贴片提示词、房间标题和图片生成 | 对应 `live_sticker_*` 原生模块 | `live_sticker_prompts.py`, `live_sticker_titles.py`, `runninghub_image.py` | 静态验证通过 | 真实 LLM/图片服务、失败重试和图片比例 |
| CNT-014 | 云端数字人项目与音视频生成 | `cloud_dh` 项目 API | `main.py`, `runninghub_talk.py`, `cloud_dh_prompts.py` | 开发中 | 真实 API、上传、轮询、超时、产物归档 |
| CNT-015 | 短视频配音、合成、列表和删除 | `generate_audio_for_short_video/create_short_video` | `short_video_audio_synthesis.py`, `generate_lip_sync_video.py` | 静态验证通过 | Windows FFmpeg、各语言 TTS、真实长视频和失败清理 |
| CNT-016 | 字幕生成和烧录 | `add_subtitles_to_video.pyd`、SRT 链 | `add_subtitles_to_video.py`, `get_srt.py` | 静态验证通过 | 中文字体、长文本、时间轴、硬件编码和成片校验 |

## P0：音频、语音和形象生产

| ID | 用户功能 | 原入口/主要证据 | 当前重建模块 | 当前状态 | 完成前必须验证 |
|---|---|---|---|---|---|
| MED-001 | 音频设备枚举和播放 | `audio_devices/audio_player.pyd` | `audio_devices.py`, `audio_player.py` | 静态验证通过 | Windows 多声卡、设备热插拔和独占冲突 |
| MED-002 | 音频裁剪与编辑器 | `process_audio_clip/launch_audio_editor` | `audio_clip.py`, `edit_audio.py` | 静态验证通过 | Windows GUI、MP3/WAV、边界时长和编码失败 |
| MED-003 | Whisper/FunASR 识别及 SRT | 原生 ASR 模块调用链 | `whisper_runtime.py`, `funasr_runtime.py`, `get_srt.py` | 静态验证通过 | 真实模型、CPU/GPU、长音频、多语言准确性 |
| MED-004 | 本地音色克隆预处理 | `clone_voice_local` Ghidra 主体 | `voice_clone_infer_api.py`, `clone_manager.py` | 静态验证通过 | 真实 FFmpeg/ASR、模型资源、坏音频和中文路径 |
| MED-005 | ZipVoice 本地语音推理 | `voice_infer.pyd` | `voice_infer.py` | 静态验证通过 | 真实权重、CPU/GPU、缓存、并发和音质 |
| MED-006 | OmniVoice 本地语音推理 | `voice_infer_v2.pyd` | `voice_infer_v2.py` | 静态验证通过 | 真实权重、显存、参考音隔离、缓存和音质 |
| MED-007 | IndexTTS 本地语音推理 | `voice_infer_v3.pyd` | `voice_infer_v3.py` | 开发中 | V03真实CUDA新文本、缓存/取消/恢复、双参考A/B/A和ASR/声纹自动核验已通过对应范围；人工听感、长文本、峰值/长稳及录音实机仍待验收 |
| MED-008 | 马来语/越南语本地语音 | 对应 `voice_infer_*_local.pyd` | `voice_infer_malai_local.py`, `voice_infer_vietnam_local.py` | 开发中 | 真实模型、语言发音、CPU/GPU |
| MED-009 | Minimax/CosyVoice 在线音色克隆与生成 | `start_voice_clone_*`、在线语音模块 | `online_voice_generate.py`, `cosyvoice.py` | 静态验证通过 | 真实账号、区域端点、上传、鉴权和计费错误 |
| MED-010 | 离线形象克隆 | `start_clone_local/clone_video_local` | `clone_manager.py`, `image_clone_*`、`scripts/avatar_store.py`、`scripts/avatar_tasks.py`、`scripts/render_tasks.py`、`scripts/raw_video_writer.py` | 开发中 | V04真实720p制作、原生关键点差分、形象管理及页面生成/完整播放/取消/失效通过对应范围；直接NVENC候选两后端各50条完整媒体、精度及旧编码数值筛查通过，TRT热态32.818fps/P95 33.027ms达标。主ASR分歧保留、人工质量/多分辨率/KT板、实际持续输出仍待验收；V04-04f产品方案选择/绑定/真实编码取消与页面恢复已通过对应范围 |
| MED-011 | 人脸检测、关键点、口型特征与遮挡处理 | SCRFD/S3FD/PFLD/WeNet/Hubert 链 | `image_*`, `s3fd_*`, `pfld_mobileone.py`, `hubert_extractor.py` | 静态验证通过 | 真实权重、GPU、遮挡/侧脸/多人和性能 |
| MED-012 | 商品图抠图及 KT 板覆盖 | `product_cutout/product_kt_overlay.pyd` | `product_cutout.py`, `product_kt_overlay.py` | 静态验证通过 | 真实模型、透明边缘、尺寸/旋转和直播叠加 |

## P0：直播与平台控制

| ID | 用户功能 | 原入口/主要证据 | 当前重建模块 | 当前状态 | 完成前必须验证 |
|---|---|---|---|---|---|
| LIV-001 | 数字人直播启动、停止和资源回收 | `Api.start_live`→`LiveManager` | `main.py`, `digital_live_manager.py`, `live_manager_runtime.py` | 静态验证通过 | Windows 长稳、反复启停、设备/模型异常和内存显存 |
| LIV-002 | 文件/摄像头/视频/RTMP 驱动 | `VideoStreamManager` 各 reader | `image_*_reader.py`, `frame_player_*` | 静态验证通过 | Windows 摄像头、RTMP 断流、格式和分辨率矩阵 |
| LIV-003 | TTS 队列、弹幕打断、淡入淡出和静音续接 | `live_manager.pyd` 调度链 | `live_manager_runtime.py`, `image_infer_audio.py`、`scripts/live_speech_ingress.py` | 静态验证通过 | V05-01b真实逐句交接局部通过；V05-02常驻WeNet/UNet驱动两句190帧、182272采样完整，形象序列连续、重组特征SHA一致；统一播放时钟、控制台/设备、实时压力、竞态、长稳及人工质量仍待验 |
| LIV-004 | 手动口播与模拟提问 | `Api.speak/simulate_question` | `main.py`, `digital_live_manager.py`, `face_hand_live_manager.py` | 静态验证通过 | 三种直播模式、停止竞态和前端反馈 |
| LIV-005 | 弹幕采集启动/停止 | `start_danmu_capture/stop_danmu_capture` | `danmu_bridge.py`, `ws_capture.py` | 开发中 | 抖音/淘宝/快手/Shopee/PDD 真实房间 |
| LIV-006 | 快手 WebSocket 协议、心跳和重连 | `KsLive/hq/ks.pyd` | `kuaishou_v2/*` | 静态验证通过 | 真实账号/直播间、协议变化、掉线重连 |
| LIV-007 | 淘宝弹幕、账号登录和商品同步 | `get/login/probe/sync_taobao_*` | `taobao_live_control.py`, `taobao_control_capture.py` | 开发中 | 淘宝账号、验证码、商品页变化、风控和断线恢复 |
| LIV-008 | 淘宝自动讲解、点品及控制页自愈 | 淘宝控制 Ghidra 调用链 | `taobao_live_control.py`, `face_hand_live_manager.py` | 静态验证通过 | 淘宝真实直播控制台长稳验证 |
| LIV-009 | Shopee 登录态、商品轮播和控制恢复 | Shopee 控制 Ghidra 调用链 | `shopee_live_control.py`, `shopee_control_capture.py` | 静态验证通过 | 真实卖家账号、区域站点和页面升级 |
| LIV-010 | 拼多多弹幕采集 | `assets/ws_danmu_capture/pdd` | `recovered/assets/ws_danmu_capture/pdd/*` | 已分析 | 真实直播间、登录态和协议变化 |
| LIV-011 | OCR 弹幕/自动操作/直播保护 | `auto_live_action`、OCR 模块 | `auto_live_action*.py`, `danmu_ocr/*` | 静态验证通过 | Windows DPI、多显示器、窗口遮挡和误触控制 |
| LIV-012 | 转播/录播本地视频和抖音源 | `RecordLiveManager.start_live` | `record_live_manager.py`, `stream_ingest.py` | 静态验证通过 | 本地 25FPS、真实抖音 URL、长稳和断流恢复 |
| LIV-013 | 实拍报时公告生成和插播 | `prepare_record_announcement` 调用链 | `record_live_manager.py`, `generate_broadcast_time_video.py` | 静态验证通过 | 真实 TTS/视频、取消竞态和临时文件所有权 |
| LIV-014 | 人脸人手直播与商品素材调度 | `FaceHandLiveManager`；2026-11-10 Windows原生切片对照见 `evidence/v00-baseline.md` | `face_hand_live_manager.py`, `face_hand_player.py`, `face_hand_vad_split.py` | 开发中 | Windows切片路径已修复；原版manifest v2/返回结构/默认参数存在待对齐差异，随后验证淘宝、长稳及商品切换 |
| LIV-015 | AI 互动回复和人工接管 | 互动 LLM/控制提交链 | `face_hand_live_manager.py`, `llm_reply.py` | 静态验证通过 | 真实弹幕、超时、审核、回退和接管恢复 |
| LIV-016 | 虚拟摄像头输出 | `virtual_cam.pyd` | `virtual_cam.py` | 已分析 | Windows 驱动安装、OBS/直播伴侣、分辨率和音画同步 |
| LIV-017 | SRS 本地流媒体服务和推流地址 | `assets/srs/srs-live.bat`、`get_stream_urls` | `main.py` | 已分析 | Windows 启停、端口冲突、异常退出和推流拉流 |
| LIV-018 | 输出分辨率五档及画面适配 | `output_resolution.pyd` | `output_resolution.py`, `image_position_compat.py` | 静态验证通过 | 各档真实输出、横竖屏、旋转和播放器兼容 |

## 当前统计

| 状态 | 数量 |
|---|---:|
| 静态验证通过 | 40 |
| 开发中 | 8 |
| 已分析 | 10 |
| Windows 验证通过 | 0 |
| 端到端验证通过 | 0 |
| 合计 | 58 |

当前已有局部Windows原生差分和V00～V02本机流程证据，仍不足以将完整原功能标为端到端通过。下一阶段优先闭环 P0 主路径：`SYS-001~005`、`LIV-001~005`、`MED-001~010`，并为“开发中/已分析”条目补齐真实测试。

## 证据索引

- 总体逆向报告：`rea-output/yunchuang-v122-reverse-report.md`
- PYZ 清单：`rea-output/PYZ-modules.txt`
- 第一方原生模块清单：`rea-output/native-modules.txt`
- 恢复源码：`recovered/`
- 恢复验证器：`recovered/verify_recovery.py`
- Windows 待验证条件：总报告“Mac 已完成与 Windows 边界”章节

更新本矩阵时必须同时更新统计，并提供源码、测试、反编译证据或真实环境记录之一；不能仅凭计划把状态向前推进。
