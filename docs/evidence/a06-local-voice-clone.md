# MED-004 本地音色克隆预处理

验证日期：2026-11-14。环境：Windows、随包 Python/FFmpeg、FunASR 1.2.3。

使用已有 22.49 秒中文 WAV 调用恢复版 `clone_voice_local`，输出目录和音色名称均包含中文。真实链路完成 FFmpeg 16 kHz 单声道 PCM 标准化、FunASR 识别、参考音频和参考文本导出。最终参考文本 114 个字符；`ref_audio.wav` 为单声道、16 kHz、16-bit、359824 帧，SHA-256 为 `e33ce60e9095e892a2de07ec9485dec8b98d3c847f5799de76cbe0e7f4a41b8f`。manifest 含一项并引用发布后的最终路径，无暂存路径泄漏。

实测二次覆盖时捕获 Windows 媒体句柄短暂占用导致目录重命名 `WinError 5`。发布流程改为独立暂存目录生成、旧版本备份、Windows 短暂句柄锁重试、成功后切换；失败恢复旧目录并清理暂存。专项 3 项覆盖坏媒体保留旧音色、成功替换及最终 manifest 路径、Windows 瞬态锁重试，全部通过；恢复基线五关通过。真实二次发布后 pending/backup 目录均为 0。

本次证明预处理和发布生命周期可在本机真实运行，不替代后续各 TTS 引擎的人工音质、并发和直播验收。
