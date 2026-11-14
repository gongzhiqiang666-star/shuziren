# X06 SoulX-FlashHead Lite / Pro 基线

日期：2026-11-14。任务：X06-01 完成；X06-02 条件缺失。

## 固定版本与资源

- 官方源码：`Soul-AILab/SoulX-FlashHead`，提交 `9bc03de06bb0de82cd6bc477804512ae06144bf2`；源码许可证 Apache-2.0。
- 官方模型：`Soul-AILab/SoulX-FlashHead-1_3B`，快照 `5fbd2e44ba08ab2deb28bd55cff2c15523e51ba5`，API 列出的文件约 14.33 GB。
- Lite DiT 权重约 6.11 GB，另需 LTX VAE 约 1.68 GB；模型卡明确 LTX VAE 为 Open-RAIL-M，发行时必须保留该许可证和限制。Pro DiT 约 6.03 GB，Wan VAE 约 0.51 GB；模型卡说明 Pro 工作流组件为 Apache-2.0。两者还依赖 `wav2vec2-base-960h`。
- 官方环境为 Python 3.10、PyTorch 2.7.1、torchvision 0.22.1、CUDA 12.8、FlashAttention 2.8.0.post2；SageAttention 2.2.0 可选。必须使用独立目录，不改现有媒体环境。

## 硬件结论与门槛

官方只报告 Lite 在单 RTX 4090 上 96 FPS/三路 25+ FPS，Pro 在单 4090 上 10.8 FPS、双 RTX 5090 才达到 25+ FPS。这些不是 RTX 3060 实测结果。

Lite 才进入 RTX 3060 原型；Pro 保持高配条件缺失，恢复条件为独立双 RTX 5090 或经批准的等价多卡环境。Lite 原型必须记录源码/模型摘要、驱动、CUDA、精度、分辨率、冷启动、首帧、最终 FPS、RSS/显存、音视频长度、退出码和完整产物。

同一授权人物图、同一 16 kHz 输入音频和同一接收/编码条件与现有真人链比较。最低进入 X06-03 条件：真实产物完整解码；720p/25fps 产品输出不靠离线预计算；身份、嘴周、动作和长序列无阻断缺陷；取消、失败后显存/进程可恢复；不降低 V05-T1 时序和缓冲门槛。模型原生 512×512 结果不得直接冒充 720×1280 产品输出质量。

## 本机探测和决策

`D:\TEMP`、两个参考项目、已授权 v122 运行目录及常见模型缓存未发现 FlashHead 源码或权重。本次仅把官方源码浅克隆到 Git 忽略的 `D:\TEMP\soulx-flashhead-source-20261114` 核对，未下载约 14.33 GB 模型，不修改已验环境。

X06-02 Lite 标记“条件缺失”：固定权重未下载，独立 CUDA 12.8/FlashAttention 环境未闭合；Pro 同时缺高配硬件。默认数字人链不变，X06-03/04 延期并继续 X07。恢复时先做 Lite 单样本显存预检；若加载即超 RTX 3060 预算，保存失败证据后停止扩大下载/调参，不以作者 4090 数据替代。
