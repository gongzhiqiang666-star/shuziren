# yunchuang_v122 权威功能矩阵

更新日期：2026-11-14

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
| SYS-001 | Windows 一键启动与环境选择 | `launcher_temp`、PYZ 95 模块 | `recovered/launcher_temp.py` | 静态验证通过 | 普通/RTX 50环境选择、50环境缺失回退、缺Python/start.py诊断、FFmpeg环境和子进程退出码4项通过；本机授权双环境路径解析及RTX 3060探测通过，见 `evidence/a07-windows-launcher.md`。Win10/11、无NVIDIA和真实RTX 50整机启动待验 |
| SYS-002 | GPU/显存探测及运行环境初始化 | `main._initialize_environment` | `main_environment.py`, `gpu_probe.py` | 静态验证通过 | 本机 RTX 3060 的 nvidia-smi 与 Torch 双探针均返回12.0GiB并一致；普通NVIDIA、RTX50识别及命令缺失3项回归通过。真实RTX50、无NVIDIA物理整机和驱动故障仍待验，见 `evidence/a07-gpu-environment.md` |
| SYS-003 | 关闭 Windows 执行速度节流 | `win_power_throttling.pyd` Ghidra 证据 | `win_power_throttling.py` | Windows 验证通过 | 本机当前进程与受控子进程远程 PID 设置成功；keep-alive 启停、释放、重启、空句柄和退出错误语义 8 项专项及恢复五关通过，见 `evidence/a07-power-throttling.md`。Win10/11 多版本、低权限跨账号和企业组策略环境留待最终整机兼容验收 |
| SYS-004 | 系统配置、用户配置合并与私密配置迁移 | `main.pyd` 配置调用链 | `main_config.py` | Windows 验证通过 | 隔离 `%LOCALAPPDATA%` 完成旧私密字段迁移、交付配置清理和运行值恢复；损坏配置、迁移失败、原子替换失败均不覆盖或丢失上一份有效数据，6 项专项及恢复五关通过，见 `evidence/a07-user-config-migration.md`。物理断电、企业目录重定向和杀毒占用留待最终整机兼容验收 |
| SYS-005 | pywebview 主窗口及前后端 JS API | `main.main/_main/run_webview` | `main_webview.py`, `main.py`, `main_shutdown.py` | Windows 验证通过 | 本机 pywebview 真实创建“AI数字人直播”窗口，句柄非零且响应正常；系统关窗后 5 秒内退出并恰调用一次 shutdown。开发/生产 URL、JS API 绑定、窗口参数、信号和多资源故障隔离自动验证通过。Computer Use 原生管道仍缺失，页面内点击、任务管理器及异常窗口待补验，见 `evidence/v01-webview-lifecycle.md` |
| SYS-006 | 登录 Token、管理员/OEM 信息与背景资源 | Token `0x1800644b0/0x180064620`, `0x180064dd0/0x180065090`, `0x180065880/0x1800659f0`; 管理员/OEM/背景/版本原生主体 | `main.py` | Windows 验证通过 | Token 精确保存/清除、恰好 16 KiB 边界、超限及失败无副作用 3 项通过；授权 Windows 包真实管理员 ID 和 177,479 字节 PNG 背景读取成功，缺 OEM 安全返回空对象；资源路径与上限 3 项通过，见 `evidence/a07-token-persistence.md`。原 `.pyd` 文案、旧 OEM 样本和前端远端登录流待外部条件 |
| SYS-007 | 本地资源枚举、预览与删除 | main wrapper/body `get_local_resources` `0x1800b9320/0x1800b9490`、`delete_model` `0x1800b7980/0x1800b7c40`、`delete_voice` `0x1800b8650/0x1800b8910`；CloneManager 枚举/信息写入/预览主体见 `rea-output/main-local-resources-notes.md` | `main.py`, `clone_manager.py` | Windows 验证通过 | 隔离中文目录的真实 JPEG/WAV 完成枚举、预览、删除及后端刷新；Windows 独占句柄下删除明确失败并保留资源，释放后重试成功；路径逃逸被拒，3 项专项及恢复五关通过，见 `evidence/a07-local-resources.md`。页面点击、原 `.pyd` 文案和旧生产资源变体待外部条件 |
| SYS-008 | 文件/目录选择及打开目录 | `open_file_dialog/open_directory` wrapper/body `0x1800393c0/0x180039610`、`0x18003cb70/0x18003ce30`，见 `rea-output/main-file-dialog-notes.md` | `main.py` | 静态验证通过 | Windows 原 `.pyd` 响应差分、真实对话框、中文/长路径、Shell 关联程序及权限错误 |
| SYS-009 | 缓存清理 | `Api.clear_cache` | `main.py`, `cache_cleanup.py`, `audio_cache.py` | Windows 验证通过 | 直播中拒绝；仅清理 8 类已知缓存并统计文件/字节，Windows 占用文件保留且释放后重试成功；真实目录 junction 只移除联接、不进入外部客户目录，5 项专项及恢复五关通过，见 `evidence/a07-cache-cleanup.md`。页面点击和生产缓存规模仍待集中验收 |
| SYS-010 | 应用更新状态、下载/启动更新器 | `get_update_status/start_app_update` | `main.py`, `update_integrity.py`, `update_text.py` | Windows 验证通过 | 强制远端 HTTPS（回环测试除外）及每包 SHA-256，拒绝路径穿越/绝对路径/符号链接；本机服务版本解析、逐文件暂存/哈希/原子替换、单包覆盖与新增回滚通过。Windows 占用目标时旧文件不变且暂存清理，释放后重试成功，8 项专项及恢复五关通过。正式 HTTPS 服务、更新器窗口、物理断电和跨多包整场回滚待最终验收，见 `evidence/v09-legacy-updater-hardening.md` |
| SYS-011 | 插件安装与 OBA Live 工具 | `PluginInstallerService`、`launch_oba_live_tool` | `main.py`, `main_plugins.py` | 静态验证通过 | 随包安装器提权前强制受信目录、清单、大小和 SHA-256；OBA 下载强制 HTTPS、配置哈希、临时写入和原子发布，已安装 EXE 只接受三个批准根。7 项专项测试及 13 项完整性相关回归通过。授权 v122 旧包没有清单，会安全拒绝；自有打包清单、真实 UAC、安装/卸载及 OBA 正式签名仍待 Windows 验证，见 `evidence/v09-plugin-installer-integrity.md` |
| SYS-012 | Windows 安装包及可复现打包 | 原 PyInstaller 交付结构 | `scripts/console_package.py`, `scripts/media_runtime.py`, `packaging/*` | Windows 验证通过 | 固定提交 `2230614` 在 Windows 独立构建两次，均为 459 个受控文件且 ZIP SHA-256 同为 `127030fb…043ae`；独立 verify、全新 install 及 5258 隔离启动健康检查通过，状态不暴露 token。路径/哈希/大小门禁、原子版本指针与回滚已有回归。干净 Win10/11、完整离线依赖、卸载、驱动和完整媒体包待最终验收，见 `evidence/v09-current-package.md` |

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
| CNT-008 | 抖音/IP 对标视频提取 | `extract_douyin_benchmark` | `main.py`, `douyin_benchmark.py` | 静态验证通过 | 仅接受抖音官方 HTTPS 分享链接，下载产物必须位于工具目录、非空且为允许的视频扩展名，ASR 前用 FFprobe 验证真实视频轨；项目 benchmark 目录事务替换。4 项专项测试通过，本机 1 秒 H.264/AAC 媒体实测视频轨与时长有效。真实抖音登录/验证码/风控、失效短链及下载器升级待平台验证，见 `evidence/v02-douyin-benchmark.md` |
| CNT-009 | IP 发布标题、简介、标签生成 | `generate_ip_agent_publish_meta` wrapper/body `0x180142690/0x180142a40` | `main.py`, `generate_title.py` | 静态验证通过 | Windows 原 `.pyd` 差分和真实 LLM 输出质量 |
| CNT-010 | IP 一键成片流水线 | 音频→视频→字幕→精加工→发布 API | `main.py`, `ip_pipeline.py`, `ip_agent_post_process.py` | 静态验证通过 | 稳定指纹、逐步检查点、产物复核、跨进程锁、崩溃事务恢复、续跑和幂等通过 6 项专项及完整契约。RTX 3060 真实 IndexTTS→TensorRT 口型→字幕→后期链注入字幕故障后仅续跑剩余步骤，最终 720×1280 H.264/AAC 成片完整解码；未对外发布，见 `evidence/v02-ip-pipeline-checkpoint.md` |
| CNT-011 | IP 视频发布 | `publish_ip_agent_video` | `main.py`, `ip_publish.py` | 静态验证通过 | 四平台白名单；媒体与字段门禁、预演、幂等、任务先落盘、同项目并发拒绝、异常可重试、中断结果未知确认、删除前独立审计归档；控制台支持事务式成片导入和完整发布表单。专项 13 项（含创建到删除审计全链）、控制台 HTTP 59 项及前端语法通过，未对外发布。真实账号登录、草稿/立即/定时发布及失败重试待授权平台验证，见 `evidence/v02-ip-publish.md` |
| CNT-012 | 直播贴片项目管理 | main CRUD/helper wrapper/body 与 26 字段 YAML、五类固定输出、历史归档及旧项目迁移证据，见 `rea-output/main-live-sticker-project-notes.md` | `main.py` | 静态验证通过 | Windows 原 `.pyd` 响应差分、真实旧项目、连续生成归档、文件占用/权限错误和前端预览 |
| CNT-013 | 贴片提示词、房间标题和图片生成 | 对应 `live_sticker_*` 原生模块 | `live_sticker_prompts.py`, `live_sticker_titles.py`, `runninghub_image.py` | 静态验证通过 | 真实 LLM/图片服务、失败重试和图片比例 |
| CNT-014 | 云端数字人项目与音视频生成 | `cloud_dh` 项目 API | `main.py`, `runninghub_talk.py`, `cloud_dh_prompts.py` | 静态验证通过 | 无 URL 完成态、轮询边界、HTTPS/2GiB/MP4/原子下载、素材验证、版本归档、取消及重启中断 9 项通过，见 `evidence/v02-cloud-dh-transaction.md`。经授权真实 API 的图片生成、上传、队列轮询、超时和成片归档转 E03 外部验收 |
| CNT-015 | 短视频配音、合成、列表和删除 | `generate_audio_for_short_video/create_short_video` | `short_video_audio_synthesis.py`, `generate_lip_sync_video.py` | 静态验证通过 | Windows FFmpeg、各语言 TTS、真实长视频和失败清理 |
| CNT-016 | 字幕生成和烧录 | `add_subtitles_to_video.pyd`、SRT 链 | `add_subtitles_to_video.py`, `get_srt.py` | 静态验证通过 | 中文字体、长文本、时间轴、硬件编码和成片校验 |

## P0：音频、语音和形象生产

| ID | 用户功能 | 原入口/主要证据 | 当前重建模块 | 当前状态 | 完成前必须验证 |
|---|---|---|---|---|---|
| MED-001 | 音频设备枚举和播放 | `audio_devices/audio_player.pyd` | `audio_devices.py`, `audio_player.py` | 静态验证通过 | 修复 host 局部序号误作全局设备编号和单设备查询失败中止扫描；Windows 实测 2 输入、5 输出均可打开。播放器支持指定全局编号和幂等关闭，VB-Audio 连续两实例播放/释放通过且保留原构造签名。物理热插拔、独占冲突和播放中消失待验，见 `evidence/a06-audio-device-index.md` |
| MED-002 | 音频裁剪与编辑器 | `process_audio_clip/launch_audio_editor` | `audio_clip.py`, `edit_audio.py` | 静态验证通过 | PCM WAV 门禁、受限预览及 WAV/TXT 双文件事务；修复 ASR 模型路径并隔离任务目录。22.49秒同源 WAV/MP3 真实 FunASR 均生成4段一致文本，时间戳仅末端差30ms；失败隔离回归2项通过。Windows GUI、物理热插拔和独占冲突仍待验，见 `evidence/a06-audio-device-index.md` |
| MED-003 | Whisper/FunASR 识别及 SRT | 原生 ASR 模块调用链 | `whisper_runtime.py`, `funasr_runtime.py`, `get_srt.py`, `audio_clip.py` | 静态验证通过 | 真实 FunASR WAV/MP3 与 manifest；Whisper 唯一临时文件和原子文本；RTX 3060 large-v3 真实 8 秒英语识别及 MP4→SRT 全链通过，修复双句号、英文空格丢失和独立标点字幕，三段时间轴连续至8000ms。CPU、长音频和更多语言准确性待验，见 `evidence/a06-audio-device-index.md` |
| MED-004 | 本地音色克隆预处理 | `clone_voice_local` Ghidra 主体 | `voice_clone_infer_api.py`, `clone_manager.py` | 静态验证通过 | 真实 FFmpeg/ASR、模型资源、坏音频和中文路径 |
| MED-005 | ZipVoice 本地语音推理 | `voice_infer.pyd` | `voice_infer.py`、`scripts/tts_worker.py` | 静态验证通过 | A01-02 已有 Windows CPU/CUDA 合成、双参考音缓存隔离、显存清理及独立媒体任务证据。原程序差分、并发、人工音质和直播待验 |
| MED-006 | OmniVoice 本地语音推理 | `voice_infer_v2.pyd` | `voice_infer_v2.py`、`scripts/tts_worker.py` | 静态验证通过 | A01-02 已有 RTX 3060 合成、中英语言缓存隔离及独立媒体任务证据。原程序差分、显存量化、双参考音、人工音质和直播待验 |
| MED-007 | IndexTTS 本地语音推理 | `voice_infer_v3.pyd` | `voice_infer_v3.py` | 静态验证通过 | V03 真实 CUDA 新文本、缓存/取消/恢复、双参考 A/B/A 和 ASR/声纹核验已通过；637 字长文本分段、PCM 合并、原子发布和失败清理通过 4 项测试及 Windows RTX/CUDA 真实生成，见 `evidence/v03-indextts-long-text.md`。人工听感、高并发峰值、长稳及麦克风页面实录仍待最终验收 |
| MED-008 | 马来语/越南语本地语音 | 对应 `voice_infer_*_local.pyd` | `local_voice.py`, `voice_infer_v2.py`, `voice_infer_malai_local.py`, `voice_infer_vietnam_local.py` | 静态验证通过 | 产品主链的 `malai_local`/`vietnam_local` 统一路由常驻 OmniVoice，并固定 `ms-MY`/`vi-VN`；原 F5 服务客户端保留为兼容适配器。RTX 3060 两语言真实合成、缓存隔离及各约 70 秒轮播/插播/接管/双轨回采通过；2 项路由测试及完整契约通过，见 `evidence/a01-multilingual-local-voice.md`。人工发音听感、口音语料、CPU 性能和原 F5 服务差分仍待验 |
| MED-009 | Minimax/CosyVoice 在线音色克隆与生成 | `start_voice_clone_*`、在线语音模块 | `online_voice_generate.py`, `cosyvoice.py` | 静态验证通过 | 真实账号、区域端点、上传、鉴权和计费错误 |
| MED-010 | 离线形象克隆 | `start_clone_local/clone_video_local` | `clone_manager.py`, `image_clone_*`、`scripts/avatar_store.py`、`scripts/avatar_tasks.py`、`scripts/render_tasks.py`、`scripts/raw_video_writer.py` | 静态验证通过 | V04 真实 480p/720p/1080p 制作、原生关键点差分、生成/播放/取消/失效已有证据；形象安全删除完成。制作与导入边界新增多人、低于80%人脸覆盖、连续丢脸及位置越界门禁；真实50帧单人通过、受控多人50/50帧明确拒绝，专项19项通过，见 `evidence/v04-video-preparation.md`。人工动态质量、2K/4K、复杂侧脸/遮挡和 KT 板仍待最终验收 |
| MED-011 | 人脸检测、关键点、口型特征与遮挡处理 | SCRFD/S3FD/PFLD/WeNet/Hubert 链 | `image_*`, `s3fd_*`, `pfld_mobileone.py`, `hubert_extractor.py` | 静态验证通过 | 真实 SCRFD/PFLD 单人和受控多人输入已验，逐帧人脸数与覆盖门禁生效；复杂遮挡/侧脸、原 `.pyd` 阈值差分及性能仍待验，见 `evidence/v04-video-preparation.md` |
| MED-012 | 商品图抠图及 KT 板覆盖 | `product_cutout/product_kt_overlay.pyd` | `product_cutout.py`, `product_kt_overlay.py` | 静态验证通过 | RTX 真模型生成软 Alpha BGRA；KT 保留 PNG Alpha/比例，缓存原子保存和结构校验，直播启停、商品轮播切换、FramePlayer提交及关闭重开通过。商品工具33项与恢复基线通过。动态设备回采、真实商品主观边缘及长稳待首版集中验收，见 `evidence/a06-product-visual-tools.md` |

## P0：直播与平台控制

| ID | 用户功能 | 原入口/主要证据 | 当前重建模块 | 当前状态 | 完成前必须验证 |
|---|---|---|---|---|---|
| LIV-001 | 数字人直播启动、停止和资源回收 | `Api.start_live`→`LiveManager` | `main.py`, `digital_live_manager.py`, `live_manager_runtime.py` | 静态验证通过 | V06 本机通过 20 次独立启停；G10-04 改稿场次完成轮播、接管恢复和停播，接收双轨完整解码。证据见 docs/PROGRESS.md 与 docs/PHASE4_GROWTH_PLAN.md。发布配置长稳、设备/模型异常及内存显存仍待完整验收 |
| LIV-002 | 文件/摄像头/视频/RTMP 驱动 | `VideoStreamManager` 各 reader | `image_*_reader.py`、`frame_player_*`、控制台 RTMP 媒体子进程 | 静态验证通过 | 本机 SRS 至控制台轮播、回采、解码中断及发布端停推复推均通过，见 A01-05。断流期间主动停播通过。摄像头有效画面和格式分辨率矩阵待验 |
| LIV-003 | TTS 队列、弹幕打断、淡入淡出和静音续接 | `live_manager.pyd` 调度链 | `live_manager_runtime.py`, `image_infer_audio.py`、`scripts/live_speech_ingress.py` | 静态验证通过 | V05-01b真实逐句交接局部通过；V05-02常驻WeNet/UNet驱动两句190帧、182272采样完整，形象序列连续、重组特征SHA一致；V05-03a累计采样/821帧PTS核验通过；03b形象预热与8帧有界原始帧接收/停止局部通过；实际定时音画输出、控制台/设备、实时压力、竞态、长稳及人工质量仍待验 |
| LIV-004 | 手动口播与模拟提问 | `Api.speak/simulate_question` | `main.py`, `digital_live_manager.py`, `face_hand_live_manager.py` | 静态验证通过 | 三种直播模式、停止竞态和前端反馈 |
| LIV-005 | 弹幕采集启动/停止 | `start_danmu_capture/stop_danmu_capture` | `danmu_bridge.py`, `ws_capture.py`, `digital_live_manager.py` | 静态验证通过 | 启动、自然结束、迭代异常、stop 异常的状态切断与重启通过 2 项专项测试；PDD 7 项和包含快手/淘宝/Shopee 协议的完整契约通过，见 `evidence/v07-danmu-lifecycle.md`。抖音/淘宝/快手/Shopee/PDD 真实账号与直播间仍待平台验收 |
| LIV-006 | 快手 WebSocket 协议、心跳和重连 | `KsLive/hq/ks.pyd` | `kuaishou_v2/*` | 静态验证通过 | 真实账号/直播间、协议变化、掉线重连 |
| LIV-007 | 淘宝弹幕、账号登录和商品同步 | `get/login/probe/sync_taobao_*` | `taobao_live_control.py`, `taobao_control_capture.py` | 静态验证通过 | 登录截止/取消、Playwright 线程所有权、商品 ID、快照去重、浏览器断线后带 storage state 退避重建以及登录失效不循环通过 7 项专项和完整契约，见 `evidence/v07-taobao-reconnect.md`。真实淘宝账号、验证码、商品页变化、弹卡和风控仍待平台验收 |
| LIV-008 | 淘宝自动讲解、点品及控制页自愈 | 淘宝控制 Ghidra 调用链 | `taobao_live_control.py`, `face_hand_live_manager.py` | 静态验证通过 | 淘宝真实直播控制台长稳验证 |
| LIV-009 | Shopee 登录态、商品轮播和控制恢复 | Shopee 控制 Ghidra 调用链 | `shopee_live_control.py`, `shopee_control_capture.py` | 静态验证通过 | 真实卖家账号、区域站点和页面升级 |
| LIV-010 | 拼多多弹幕采集 | `assets/ws_danmu_capture/pdd` | `danmu_bridge.py`, `digital_live_manager.py`, `recovered/assets/ws_danmu_capture/pdd/*` | 静态验证通过 | 管理器现启动自有 PDD wrapper，使用动态回环端口并发送经官方 HTTPS 域名校验的直播 URL；Cookie 位于用户数据目录，事件规范化，兼容同步/异步 broadcast，帧和 gzip 解压限制 8 MiB。7 项专项测试、真实 wrapper 动态端口连接/停止及既有 protobuf 样本通过。真实拼多多账号、扫码、直播间和协议变化待平台验证，见 `evidence/v07-pdd-capture.md` |
| LIV-011 | OCR 弹幕/自动操作/直播保护 | `auto_live_action`、OCR 模块 | `auto_live_action*.py`, `danmu_ocr/*` | 静态验证通过 | Windows DPI、多显示器、窗口遮挡和误触控制 |
| LIV-012 | 转播/录播本地视频和抖音源 | `RecordLiveManager.start_live` | `record_live_manager.py`, `stream_ingest.py` | 静态验证通过 | 本地 25FPS、真实抖音 URL、长稳和断流恢复 |
| LIV-013 | 实拍报时公告生成和插播 | `prepare_record_announcement` 调用链 | `record_live_manager.py`, `generate_broadcast_time_video.py` | 静态验证通过 | 真实 TTS/视频、取消竞态和临时文件所有权 |
| LIV-014 | 人脸人手直播与商品素材调度 | `FaceHandLiveManager`；2026-11-10 Windows原生切片对照见 `evidence/v00-baseline.md` | `face_hand_live_manager.py`, `face_hand_player.py`, `face_hand_vad_split.py`, `image_rtmp_face_reader.py` | 静态验证通过 | Windows切片、manifest v2、返回结构、默认参数、随机分段及 RTMP 首帧签名已与原 `.pyd` 差分对齐；完整恢复契约 128/128 通过。真实淘宝场次、长稳及商品切换仍待端到端验证 |
| LIV-015 | AI 互动回复和人工接管 | 互动 LLM/控制提交链 | `face_hand_live_manager.py`, `llm_reply.py` | 静态验证通过 | 真实弹幕、超时、审核、回退和接管恢复 |
| LIV-016 | 虚拟摄像头输出 | `virtual_cam.pyd` | `virtual_cam.py`、`scripts/live_device_output.py`、`scripts/live_av_device_sink.py` | 静态验证通过 | V05-04b 时钟消融确认平滑视频时钟对连续性必需；恢复后同配置真实 20 秒/500 帧复现通过，迟到 P95 1.654ms、超 5ms 比例 0.203%，两段回采相关性均大于 0.99999987、音画偏差约 11.4ms，语音区 198 帧零缺失/重复/乱序。全窗口仍有启动首帧重复 1；驱动安装、平台客户端、其他分辨率、零启动重复及长稳待集中验收，见 `evidence/v05-received-voices.md` |
| LIV-017 | SRS 本地流媒体服务和推流地址 | `assets/srs/srs-live.bat`、`get_stream_urls` | `main.py`, `srs_runtime.py` | 静态验证通过 | 已改为直接启动随包 `srs.exe`，验证缺文件、端口冲突、异常早退、三端口就绪及仅按本实例 PID 回收；本机真实 RTMP 推流、HTTP-FLV 拉流和 API 探活通过，见 `evidence/v00-srs-runtime.md`。打包后页面状态、长稳和异常断流仍待验 |
| LIV-018 | 输出分辨率五档及画面适配 | `output_resolution.pyd` | `output_resolution.py`, `image_position_compat.py` | 静态验证通过 | 各档真实输出、横竖屏、旋转和播放器兼容 |

## 当前统计

| 状态 | 数量 |
|---|---:|
| 静态验证通过 | 50 |
| 开发中 | 0 |
| 已分析 | 0 |
| Windows 验证通过 | 8 |
| 端到端验证通过 | 0 |
| 合计 | 58 |

当前已有局部 Windows 原生差分、一期至四期本机流程和候选包证据，仍不足以将完整原功能标为 Windows 或端到端通过。源码开发队列已清零；后续按 A07 的本机集中验收与外部队列继续提升真实状态，不用静态通过替代生产验收。

## 证据索引

- 总体逆向报告：`rea-output/yunchuang-v122-reverse-report.md`
- PYZ 清单：`rea-output/PYZ-modules.txt`
- 第一方原生模块清单：`rea-output/native-modules.txt`
- 恢复源码：`recovered/`
- 恢复验证器：`recovered/verify_recovery.py`
- Windows 待验证条件：总报告“Mac 已完成与 Windows 边界”章节

更新本矩阵时必须同时更新统计，并提供源码、测试、反编译证据或真实环境记录之一；不能仅凭计划把状态向前推进。
