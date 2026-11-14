# X10 三维 TalkingHead / Audio2Face 基线

日期：2026-11-14。任务：X10-01 完成；X10-02 轻量原型已有可复用证据，当前主线适配待开发；Audio2Face 条件缺失。

## 路线 A：浏览器轻量三维

历史分支 `codex/low-end-3d-preview` 的提交 `b43f8e1` 已实现独立 `/avatar3d`：Three.js/WebGL2 加载真实 GLB、Oculus/ARKit 兼容嘴形、牙齿/舌头/眨眼、本地 WAV/录音、HeadAudio 分析、轨道校验、播放拖动、绿幕及带音频 WebM 录制。

该分支记录 78 项前端测试和 9 组真实 Chromium 检查通过；固定 CC0 `mpfb.glb` 为 36,815,920 字节，SHA-256 `63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c`，含 8 个网格、约 8.37 万三角形和 66 个形变目标。浏览器验证使用软件渲染和合成音调，未证明 Windows GPU、中文口型、OBS、淘宝或长稳。

当前仓库架构已重建为 Python 本地控制台，该历史分支包含旧 Vue 工作台和大量独立依赖，不能整体合并。进入当前主线前只迁移协议和最小渲染资产：GLB 安全导入/哈希、音频绑定轨道、播放器时钟、纯画面输出和验证报告；商品、音色、场次及接管继续使用当前服务端状态。

## 路线 B：NVIDIA Audio2Face-3D

Audio2Face-3D 属于 NVIDIA ACE/NIM 或 Unreal/Omniverse 插件能力，不按普通开源权重处理。采用前必须核对 NVIDIA 服务/容器许可、NGC 凭据、模型与角色资产条款、数据区域和禁止用途；官方文档明确不得把软件用于情绪识别。

当前 NIM 2.0 官方栈推荐 Ubuntu 24.04、CUDA 12.8～12.x、R570+ 驱动、TensorRT 10.13、Docker/NVIDIA Container Toolkit。非优化配置估算约 `9 GB + 0.15 GB × streams` 显存；完整渲染链要求更高。RTX 30 系可由自动选择映射到 A10G profile，但仍须本机验证。Windows Unreal 本地执行另有 Ampere 支持和约 2.9～4.4 GiB 显存说明，不能与 NIM 容器数据混用。

本机当前没有 NGC 凭据、NIM 容器、已绑定角色或 Unreal/Omniverse 工程，且 RTX 3060 同时承担现有 TTS/口型/编码，不能预承诺并发。Audio2Face X10-02 标记“条件缺失”。

## 共同验收和决策

- 两条路线是独立形象类型，不覆盖真人视频链；三维面部动画不等于手部、身体、商品手持或真人级外观。
- 使用已授权角色及中文数字/品牌/停顿语料，检查 blendshape/viseme、表情、头身动作、身份、音画和渲染资源。
- 输出进入同一 session/epoch、取消、接管、停止和接收端协议；30 分钟/8 小时门槛不降低。
- 轻量路线优先迁移到当前控制台并在 Windows/Chrome/OBS 实测；Audio2Face 只有在许可、凭据、角色绑定和独立高配条件齐备时评测。

当前决策：保留轻量路线为入门/扩展形象候选，但不把历史分支测试标为当前产品完成；Audio2Face 延期到高配 3D 角色项目，不阻塞真人高级款。
