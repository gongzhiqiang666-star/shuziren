# X10 三维 TalkingHead / Audio2Face 基线

日期：2026-11-14。任务：X10-01、X10-02 完成；X10-03 已完成原生 GPU、真实中文 WAV、页面取消恢复和主场次 epoch 绑定子项，3D 实际输出/OBS、人工质量和长稳待验；Audio2Face 条件缺失。

## 路线 A：浏览器轻量三维

历史分支 `codex/low-end-3d-preview` 的提交 `b43f8e1` 已实现独立 `/avatar3d`：Three.js/WebGL2 加载真实 GLB、Oculus/ARKit 兼容嘴形、牙齿/舌头/眨眼、本地 WAV/录音、HeadAudio 分析、轨道校验、播放拖动、绿幕及带音频 WebM 录制。

该分支记录 78 项前端测试和 9 组真实 Chromium 检查通过；固定 CC0 `mpfb.glb` 为 36,815,920 字节，SHA-256 `63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c`，含 8 个网格、约 8.37 万三角形和 66 个形变目标。浏览器验证使用软件渲染和合成音调，未证明 Windows GPU、中文口型、OBS、淘宝或长稳。

当前仓库只迁入独立 `web/` 3D 页和最小依赖，没有合并旧 Vue 工作台。生产构建由当前 Python 控制台在 `/avatar3d/` 同源提供，导航入口位于本地工作台；静态路径限制在 `web/dist`，CSP 只允许同源脚本、Worker 和 Blob 媒体。固定依赖经 pnpm 锁文件安装，HeadAudio MIT 模块及声学模型以可审计 Base64 静态资源随包并在 Worker 内校验。

本机 Chrome 157 对当前控制台完成 9/9 检查：固定 CC0 GLB 大小/哈希、真实 WebGL2 画布与相机旋转、六组嘴形像素差、本地声学 Worker、音频 SHA 绑定、播放/暂停/跳转、错误轨道拒绝、纯画面模式和原生 MediaRecorder 音视频导出。前端单元测试 35/35、生产构建和控制台 HTTP 回归 62 项通过（1 项外部条件跳过）。报告与截图位于 `test-results/avatar3d`，该目录是可重复生成的本机证据，不提交媒体。

X10-03 原生 GPU 子项在未指定 SwiftShader 的本机 Chrome 再跑 9/9，通过浏览器调试扩展取得渲染器 `ANGLE (NVIDIA GeForce RTX 3060, Direct3D11)`、WebGL 2.0，整轮 12.588 秒且页面、控制台和请求错误均为 0。随后使用 Windows 自带 `Microsoft Huihui Desktop` 合成无克隆授权依赖的 8.391 秒普通话 PCM WAV，再跑同一链 9/9：本地 Worker 输出 114 个口型提示、25 fps 页面记录，原生 MediaRecorder 生成 139,142 字节 VP9/Opus WebM；ffprobe 确认音视频流和包时间轴，页面/控制台错误为 0。证据在 `logs/validation/x10-avatar3d-zh-sapi-01`，音频 SHA-256 为 `02e65721…38fef`，录像 SHA-256 为 `0b1c46ba…229fa`。声明文本未经过 ASR 复核，浏览器自动检查只证明真实中文 WAV 被分析、绑定、播放和录制，不证明中文口型准确或人工观感。

异常与恢复子项增加真实浏览器竞争验证：60 秒 PCM 开始分析、Worker 创建后立即换入 3 秒音频，旧 Worker 的原生 `terminate()` 调用 1 次且未发布结果；新 Worker 成功发布绑定到替换音频 SHA 的轨道，之后重新载入主音频并恢复成功。整轮扩展为 10/10、12.822 秒、RTX 3060 D3D11，页面和控制台错误为 0，证据 `logs/validation/x10-avatar3d-cancel-recover-01`。这证明单页分析任务的替换取消与恢复，不等同于直播 session/epoch 的停止恢复。

主场次生命周期子项新增显式 `lifecycle_epoch`。同一个直播管理器每次普通或视频直驱启动都递增 epoch；3D 页默认保持独立预览，用户选择跟随主场次后，只在绑定的 session/epoch 为 running 时允许播放和录制。Chrome 真实页面使用已准备模型和 WAV：epoch 1 播放中收到 stopped 后音频暂停并归零、按钮禁用；替换为 session 2/epoch 2 后页面重新绑定且保留的音频可再次播放。证据 `logs/validation/x10-avatar3d-lifecycle-02/result.json` 和截图；轮播专项 14/14、前端 35/35、typecheck/build 及原独立浏览器 10/10 均通过。

这只证明预览页不会跨场次继续旧播放/录制。3D 渲染尚未接入主 `ContinuousSession`、虚拟摄像头或接收端时钟，因此“输出进入同一 session/epoch”仍只完成生命周期门禁，媒体输出协议本身继续待验。

OBS Browser Source 页面边界已补齐：`/avatar3d/?obs=1&background=green` 启动即固定为无控件全屏画面，Esc 不会误暴露工作台；`background` 只接受 `green`、`transparent`、`studio` 三个值。Chrome 157 使用真实 WebGL/CC0 GLB 对 1440×1100 合成结果取样，绿幕像素为 `[0,255,0,255]`，扩展验收 11/11 通过；前端 35/35、类型检查和生产构建通过。本机两个标准安装路径均无 OBS 主程序，所以未执行 OBS Browser Source 接收、音频监控或编码回采；现有麦克风按钮也是“录制后离线分析”，不能冒充实时声驱。该子项只证明 OBS 可加载的稳定画面入口，生产接收与实时音频驱动继续待验。

真实麦克风页面链执行后按设备条件未通过。可选验收脚本 `tests/browser/avatar3d-microphone.cjs` 在显式授权门禁下点击页面录音并禁止外部/API请求；Chrome 成功取得 `默认 - CABLE Output (VB-Audio Virtual Cable)` 的 48 kHz、单声道、16 bit 音轨，轨道 live/unmuted，持续 4 秒得到 81 个分析窗口，但最大 RMS 为 0，故脚本明确失败而未把静音 WAV 计作麦克风通过。Computer Use 原生管道同时缺失，不能代替用户操作系统权限界面。证据 `logs/validation/x10-avatar3d-microphone-01/result.json`；恢复条件是本机默认输入切到有信号的授权物理麦克风，无需改代码。

独立交付子项已闭合。补齐 `AVATAR3D_LOCAL.md` 与 `AVATAR3D_ASSETS.md` 后，`build_avatar3d_release.py` 连续两次生成 29,984,914 字节 ZIP，SHA-256 均为 `19932931…ce3e7`；清单含 24 个文件，隔离解包后逐文件大小与 SHA 校验无差异。在 `D:\TEMP` 隔离目录直接执行包内 `start.mjs --dir app` 后，RTX 3060/D3D11 浏览器扩展链 10/10、12.762 秒通过，页面和控制台错误为 0，证据 `logs/validation/x10-avatar3d-package-01`。因当前工作区按每日提交规则尚有未提交改动，清单诚实记录 `source_dirty=true`；本包只作为本机验证包，干净提交后的正式候选需重新构建并取得 `source_dirty=false`。

## 路线 B：NVIDIA Audio2Face-3D

Audio2Face-3D 属于 NVIDIA ACE/NIM 或 Unreal/Omniverse 插件能力，不按普通开源权重处理。采用前必须核对 NVIDIA 服务/容器许可、NGC 凭据、模型与角色资产条款、数据区域和禁止用途；官方文档明确不得把软件用于情绪识别。

当前 NIM 2.0 官方栈推荐 Ubuntu 24.04、CUDA 12.8～12.x、R570+ 驱动、TensorRT 10.13、Docker/NVIDIA Container Toolkit。非优化配置估算约 `9 GB + 0.15 GB × streams` 显存；完整渲染链要求更高。RTX 30 系可由自动选择映射到 A10G profile，但仍须本机验证。Windows Unreal 本地执行另有 Ampere 支持和约 2.9～4.4 GiB 显存说明，不能与 NIM 容器数据混用。

本机当前没有 NGC 凭据、NIM 容器、已绑定角色或 Unreal/Omniverse 工程，且 RTX 3060 同时承担现有 TTS/口型/编码，不能预承诺并发。Audio2Face X10-02 标记“条件缺失”。

## 共同验收和决策

- 两条路线是独立形象类型，不覆盖真人视频链；三维面部动画不等于手部、身体、商品手持或真人级外观。
- 使用已授权角色及中文数字/品牌/停顿语料，检查 blendshape/viseme、表情、头身动作、身份、音画和渲染资源。
- 输出进入同一 session/epoch、取消、接管、停止和接收端协议；30 分钟/8 小时门槛不降低。
- 轻量路线优先迁移到当前控制台并在 Windows/Chrome/OBS 实测；Audio2Face 只有在许可、凭据、角色绑定和独立高配条件齐备时评测。

X10-04 当前阶段决策：轻量路线“采用为入门款可选 3D 形象预览”，保持独立 `/avatar3d/` 入口与独立形象类型，不替换真人链；已具备原生 RTX 3060、真实中文 WAV、页面分析取消恢复和主场次 epoch 停止/重绑证据。3D 媒体进入主输出协议、OBS、人工中文口型质量和长稳未闭合前，不开放为生产直播输出。需要回退时移除导航入口即可，主直播、项目和媒体数据不迁移。Audio2Face-3D “延期到具备许可、NGC、绑定角色和独立高配资源的高级 3D 项目”，不进入当前发布依赖，也不阻塞真人高级款。
