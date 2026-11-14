# A01-05 原视频 WeNet CPU 兼容验证

日期：2026-11-14
环境：`D:\TEMP\shuziren-origin-video-media-01` 独立媒体目录，PyTorch 2.6.0+cu118

## 结果

- 使用提供方公开入口 `load_ppg_model(..., "cpu")` 加载真实 WeNet 权重，枚举全部模型参数后设备集合严格为 `['cpu']`。
- 同一 CPU 模型通过 `get_weget` 处理真实 WAV，得到 `49×256` 特征；全部有限且包含非零值。
- 产品实际 `extract_audio_features` 路径再次独立加载 CPU 模型，得到 30 个 `20×256` 对齐窗口，模型参数仍全部位于 CPU。
- 热文件缓存下模型加载 0.346 秒、两条提取/对齐路径合计 1.563 秒。本项验证设备一致性，不把 CPU 速度写成实时放行结果。
- 输入和特征 SHA-256 已写入结构化报告，验证过程不复制模型或音频到 Git。

## 证据与复现

- 工具：`scripts/validate_wenet_cpu.py`。
- 报告：`logs/validation/a01-wenet-cpu-01/result.json`。
- 命令使用独立媒体目录自己的 Python；主控制台环境未被修改。

## 边界

离线形象提供方另有固定 CUDA 输入。重建层新增 `recovered.wenet_features`，复用提供方预处理和模型，但所有张量根据模型参数设备放置；单元回归覆盖 CPU 跟随及尾段裁剪。

修复后使用现有授权形象完成真实 CPU WeNet + CPU ONNX 短片：720×1280、25 fps、1.2 秒 H.264/AAC，FFmpeg `-xerror` 双轨完整解码。总耗时 36.596 秒，帧推理 31.298 秒，证据 `logs/validation/a01-cpu-avatar-02/result.json`。

同一兼容层在 RTX 3060 上用 `cuda:0`、批量 4 做回归，ONNX Runtime 实际提供者为 CUDA/CPU，生成相同规格的 1.2 秒双轨视频并完整解码，证据 `logs/validation/a01-cuda-avatar-compat-01/result.json`。本轮含冷加载且没有复用高级款常驻缓存，只证明设备跟随和 CUDA 功能未回退，不覆盖既有热态性能结论。

本项关闭此前“CPU 权重、CUDA 输入”导致卷积失败的设备兼容缺口，并证明完整 CPU 回退可运行；约 30.5 倍实时耗时明确不满足直播要求。它不替代 CUDA 实时链、人工口型质量或 30 分钟连续性验收；高级款仍使用 GPU/NVENC 主路径。
