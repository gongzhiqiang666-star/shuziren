# v122 第一阶段运行入口证据图

本文件只记录接口和证据位置，不复制商业二进制、模型权重或完整恢复源码。静态证据可用于实现适配器，但在RTX 3060 Windows电脑执行前不能标记为Windows验证通过。

| 阶段 | 入口 | 输入 | 输出 | 证据 | 置信状态 |
|---|---|---|---|---|---|
| `environment` | `_internal/env/python.exe`；RTX 3060使用普通`env`，不使用`env_50` | v122运行目录、`config/config.yaml` | 可导入的CPython 3.10运行环境 | 原包中同时存在`env/python.exe`、`env_50/python.exe`；配置指定`device: cuda` | confirmed-static |
| `avatar_preprocess` | `live.clone_manager.CloneManager.clone_video_local(video_path, model_name, model_id, resolution="720p", enable_kt_board=False)` | 标准化人物视频、名称、服务端生成ID | `assets/characters/images/<model_id>/`，含帧、位置、预览和`model_info.yaml` | 原`clone_manager.pyd`导出签名；`recovered/clone_manager.py`和`recovered/image_clone_api.py`恢复调用链 | confirmed-static |
| `voice_generate` | 先调用`CloneManager.clone_voice_local(...)`建立本地音色，再调用`tools.generate_short_video.audio_synthesis.synthesize_text_to_audio(...)` | 参考WAV、参考文本/ASR结果、voice ID、新话术、速度和语言 | 新生成PCM WAV及语音版本信息 | 原`clone_manager.pyd`导出签名；`recovered/voice_clone_infer_api.py`和`recovered/short_video_audio_synthesis.py` | confirmed-static；准确逐字稿如何覆盖原ASR结果需适配器明确处理 |
| `avatar_drive` | `bin.image_clone.infer_api.generate_video(processed_data_dir, audio_path, output_path, ...)` | 已预处理人物目录、同一本次WAV、Wenet和UNet模型路径、CUDA设备 | 带口型的视频输出文件 | `recovered/image_clone_api.py`中的`generate_video`和`VideoSynthesizer.process_single_file` | confirmed-static |
| `mp4_output` | 人物推理输出后使用FFmpeg校验/合成音视频；若推理文件已含音轨仍以ffprobe结果为准 | avatar-drive输出、本次WAV | 可播放且含音视频双流的MP4 | 恢复代码确认视频输出路径，但原包最终封装行为尚未在Windows执行 | inferred；必须Windows动态确认 |

## 已确认的资源目录

- 人物根目录：`_internal/assets/characters/images`。
- 声音根目录：`_internal/assets/characters/voices`。
- 当前两个目录为空，因此第一次验证必须执行人物和声音录入。
- 模型根目录：`_internal/assets/pretrained_models`，现有包约14GB。

## 适配器约束

1. 只通过`_internal/env/python.exe`加载原包CPython 3.10模块。
2. 所有ID由服务端生成并限制为安全文件名，不能直接使用网页输入作为目录名。
3. 人物预处理、声音建立、TTS、人物驱动必须分阶段记录退出状态和输出哈希。
4. `avatar_drive`必须接收`voice_generate`本次产生的同一路径和SHA-256。
5. `mp4_output`在Windows动态探测前保持`inferred`，适配器不得用固定成功结果代替真实文件和ffprobe证据。
