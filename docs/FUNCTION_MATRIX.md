# yunchuang_v122 功能矩阵

状态仅使用：未分析、已分析、开发中、静态验证通过、Windows验证通过、端到端验证通过。

| 原功能 | 入口/依赖 | 重建模块 | 实现状态 | 证据来源 | 测试状态 | Windows/GPU状态 |
|---|---|---|---|---|---|---|
| 网页录制人物视频 | 浏览器摄像头、MediaRecorder | 本地录入网页 | 静态验证通过 | 第一阶段规格 | 网页契约测试通过 | 未验证 |
| 网页录制参考声音 | 浏览器麦克风、MediaRecorder | 本地录入网页 | 静态验证通过 | 第一阶段规格 | 网页契约测试通过 | 未验证 |
| 人物素材检查与转换 | FFmpeg、ffprobe | 素材规范化 | 静态验证通过 | v122配置和恢复调用链 | 参数与边界测试通过 | 未验证 |
| 人物创建/预处理 | `CloneManager.clone_video_local` | v122运行桥接器 | 静态验证通过 | `docs/evidence/v122-runtime-map.md` | 命令与编排测试通过 | 未验证 |
| 声音建立 | `CloneManager.clone_voice_local` | v122运行桥接器 | 静态验证通过 | `docs/evidence/v122-runtime-map.md` | 命令与编排测试通过 | 未验证 |
| 新话术生成WAV | `synthesize_text_to_audio` | v122运行桥接器 | 静态验证通过 | `docs/evidence/v122-runtime-map.md` | 新鲜度与同WAV测试通过 | 未验证 |
| 同一WAV驱动人物 | `generate_video`、CUDA、Wenet、UNet | v122编排器 | 静态验证通过 | `docs/evidence/v122-runtime-map.md` | 同WAV调用链测试通过 | 未验证 |
| 最终MP4校验与播放 | FFmpeg、ffprobe、浏览器 | 网页结果区 | 静态验证通过 | 恢复代码和第一阶段规格 | 音视频合成编排测试通过 | 未验证 |
| OBS/虚拟摄像头输出 | OBS、SRS或虚拟摄像头 | 后续直播阶段 | 未分析 | 不属于第一阶段完成门槛 | 未开始 | 未验证 |
