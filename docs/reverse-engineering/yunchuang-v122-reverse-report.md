# yunchuang_v122 逆向梳理

## 当前结论

- 外层是 PyInstaller 启动器，内嵌的 `launcher_temp` 负责选择运行环境并拉起 `_internal/start.py`。
- `launcher_temp` 的 PYZ 清单已解出，共 95 个模块，主要是 Python 3.10 标准库；完整清单见 `PYZ-modules.txt`。
- `_internal` 内已识别 128 个第一方 `.pyd`，恢复目录中已有 128 个一一对应的 `.py`，且全部可导入。
- 主应用是 `pywebview + js_api` 架构。`main.pyd` 初始化配置和三个直播管理器，再把 `Api` 暴露给远端或本地 Web 前端。
- 数字人主推理链为 `Api.start_live` → `DigitalLiveManager` → `VideoStreamManager` → `FrameSynthesizer` → `Player`。

## 1. 外层启动流程

```text
yunchuang_v122.exe
  └─ PyInstaller bootloader
      └─ launcher_temp
          ├─ 关闭 Windows ExecutionSpeed 电源节流
          ├─ nvidia-smi / WMIC 探测 RTX 50xx
          ├─ 选择 _internal/env_50 或 _internal/env
          ├─ 设置 FFMPEG_HOME 与 PATH
          └─ 启动 _internal/env/python.exe _internal/start.py
              └─ main.main()
```

`launcher_temp` 的恢复源码在 `recovered/launcher_temp.py`；原始反汇编保留在 `launcher_temp.dis.txt`。当 `env_50/python.exe` 不存在时会回退到 `env/python.exe`。父进程会等待子进程退出，并再次对其关闭执行速度节流。

`tools/win_power_throttling.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-win-power/power`，并导出四个业务函数及 keep-alive 闭包主体。原生 Win32 调用使用 `PROCESS_POWER_THROTTLING_STATE(1, 1, 0)`、信息类 4 和 `PROCESS_SET_INFORMATION=0x0200`；远程 pid 真实句柄需关闭，当前进程伪句柄不关闭。

周期状态的原始名称为 `_KEEP_ALIVE_LOCK/_STOP/_THREAD`，假值间隔回退 30.0 秒、最小 5.0 秒，后台线程名固定为 `win-power-throttling-keepalive`。Windows 上只要 `keep_alive=True` 就会启动重试线程，即使首次设置失败也不例外；旧恢复版把线程启动错误依赖首次成功，会使瞬时失败后永不重试。已用模拟 Windows 平台锁定失败重试、关闭 keep-alive、最小间隔、线程名与 daemon 属性，全量验证保持 `128/128 PASS`。证据见 `rea-output/win-power-throttling-notes.md`。

进一步确认底层异常边界：私有 `_set_process_power_throttling` 不吞掉 `SetProcessInformation` 的配置/调用异常，公开入口 `disable_execution_speed_throttling` 才统一捕获并返回 `False`；原生函数还将四项 ABI 类型以 `list` 赋给 `argtypes`。恢复代码和 Mac 上的假 Win32 API 回归均已按此收紧。

## 2. main.pyd 启动链

恢复后的入口位于 `recovered/main.py`：

主扩展现已建立独立 Ghidra 12.1.4 工程 `rea-output/ghidra-main/main`，不再只依赖早期 REA 汇编和字符串引用。首次全程序分析完成后导出了函数清单及 `PluginInstallerService.__init__`、`Api.__init__`、`Api._start_live_locked`、`Api._stop_live_locked` 的包装器和真实主体；其中 `Api.__init__` 主体为 `0x180024390`，直播启动主体为 `0x18006c7b0`，停止主体为 `0x180072850`。

构造器状态槽确认原版持久保存 `_plugin_installer`、三个直播管理器、`_clone_manager`、`_live_lifecycle_lock` 与 `_live_action_assistant_process`。锁严格来自 `threading.RLock()`，而不是普通 `Lock`；恢复版已删除自创 `_live_lock`，所有启动、停止、手动口播、弹幕启停和模拟提问入口统一使用 `_live_lifecycle_lock`。同时补回持久 `_clone_manager`，CosyVoice 录音优化不再每次临时构造管理器；助手进程初值恢复为 `None`。构造测试验证四个管理器的初始化顺序、SRS 句柄写回以及同线程连续两次获取锁，完整门禁保持 `128/128 PASS`。

`_start_live_locked` 主体的前三个分支已校准：`local_media` 调用 `_start_local_media_live(config)`，`face_hand_live` 调用 `_start_face_hand_live(data, config)`，其他值（包括缺省和未来扩展值）均进入数字人路径；原生实现没有“未知 live_type”错误分支，恢复版已删除该自创限制。数字人路径补回 Minimax/CosyVoice 开播前校验：Minimax 必须有 api_key，且 `api_host` 包含 `minimax.io` 时必须同时有 group_id；CosyVoice 必须有 api_key，失败文案均按二进制常量恢复。

数字人启动成功响应也已从主体尾部恢复为三键结构：`status="success"`、管理器 `current_session_id` 对应的 `session_id`、以及 `bool(manager.is_capturing)` 对应的 `danmu_capturing`。恢复版 `DigitalLiveManager` 补入这两个原生状态接口，在运行时启动/停止时同步 session，并以弹幕 capture 是否存在报告采集状态。分支、两类配置错误和完整成功响应均有回归，门禁继续为 `128/128 PASS`。

`Api._initialize` 的原生实例也已校正为完整的 `live.live_manager.LiveManager(config)`，而不是仅含底层播放链的 `DigitalLiveManager`适配器。数字人启动前的原生预热条件也已恢复：`voice_infer_version` 属于 `v2/malai_local/vietnam_local`、文本输入且未开启原始待机视频时，调用 `prepare_multilingual_audio_cache` 并传入 scripts、主/助播音色、换班表、多商品配置、语言、语速与推理版本；返回假值时立即返回“多语种话术音频缓存准备失败”。

```text
main()
  └─ _main(runtime_dir)
      ├─ _initialize_environment(runtime_dir)
      │   ├─ nvidia-smi 获取 GPU 名称、显存与 50 系标记
      │   └─ 注入 ffmpeg、DLLs、Library/bin 到运行环境
      ├─ ensure_high_performance(keep_alive=True)
      ├─ load_effective_config(...)
      │   ├─ config/config.yaml
      │   ├─ %LOCALAPPDATA%/HuanjingLive/user_config.yaml
      │   └─ 迁移并清理交付包中的私密配置
      ├─ Api._create(runtime_dir, config)
      │   ├─ DigitalLiveManager
      │   ├─ RecordLiveManager
      │   ├─ FaceHandLiveManager
      │   └─ Windows 下启动 assets/srs/srs-live.bat
      └─ run_webview(api, config, runtime_dir)
          ├─ webview.create_window(..., js_api=api)
          ├─ 开发/生产环境 URL 选择
          └─ 关闭窗口时停止直播、SRS 和后台资源
```

配置逻辑分别恢复在 `recovered/main_environment.py`、`recovered/main_config.py` 和 `recovered/main_webview.py`。

## 3. 三条核心业务链

### 数字人直播

```text
前端 JS → Api.start_live / _start_digital_live
  → build_local_params
  → DigitalLiveManager.start_live
  → VideoStreamManager
      ├─ 驱动帧：文件 / 摄像头 / 视频 / RTMP
      ├─ 音频：normal 与 danmu 两级队列
      ├─ WeNet 特征提取
      ├─ FrameSynthesizer.synthesize_batch
      └─ Player 上传画面与音频
```

弹幕可打断普通话术。V2 调度器在打断模式下优先 `danmu`；非打断模式只有 `<stable_silence>` 会续接含同一路径记录的原队列。普通话术到弹幕、弹幕回普通话术分别有淡出和淡入状态。

### 转播/录播

```text
Api._start_local_media_live
  → 校验本地 25 FPS 视频或抖音直播 URL
  → RecordLiveManager.start_live
  → 解码、去重/画面处理、公告音频
  → 窗口或推流输出
```

### 人脸人手直播

```text
Api._start_face_hand_live
  → 校验淘宝平台、视频组、音色和商品话术
  → FaceHandLiveManager.start_live
  → 人脸/人手素材分组调度
  → 互动弹幕生成 TTS 任务
  → 播放与直播输出
```

## 4. 打包模块清单

- `PYZ-modules.txt`：外层启动器 PYZ 的 95 个模块。
- `digital-image-runtime-signatures.tsv`：两代数字人推理模块的方法签名。
- `digital-interaction-signatures.tsv`：互动与直播接口签名。
- `recovered/`：128 个第一方扩展模块的可导入 Python 对应实现。

恢复树的持续校验入口是 `recovered/verify_recovery.py`，覆盖 128/128 文件映射和导入、公开 callable 清单、核心类方法、直播管理器、控制器工作线程、音频队列/淡入淡出以及淘宝、拼多多、快手协议。

### 本地音色克隆预处理

`bin/voice_clone/infer_api.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-voice-clone`。核心入口 `clone_voice_local` 的包装体/主体为 `0x1800024b0/0x180002ca0`，`_save_manifest` 为 `0x180006aa0/0x180006d80`，`_export_reference_audio` 为 `0x180007880/0x180007b60`。原生调用链为：仅接收 WAV/MP3 → ffmpeg 标准化为 `normalized_input.wav` → `process_audio_batch` → 生成 `audio_path/text` 字典列表 → 选择文本最长项 → 写出 `slice_manifest.json`、`ref_audio.wav` 与 `ref_text.txt`。恢复版已按该字典协议修正清单序列化和最长项选择，并新增隔离 ffmpeg/ASR 的生命周期回归；全量门禁保持 `128/128 PASS`。

### Whisper ASR 运行时

`tools/asr/whisper_runtime.pyd` 已建立持久 Ghidra 工程 `rea-output/ghidra-whisper`，函数表和十个业务主体分别导出到 `whisper-functions.tsv`、`whisper-core-decompiled`。原生模型路径策略已确认：优先 `<asr_weight_path>/whisper/large-v3.pt`，兼容旧位置 `<asr_weight_path>/large-v3.pt`；两者都不存在时创建 `whisper` 目录并返回首选下载路径，而不是提前抛出文件不存在。转录调用固定传入 `task="transcribe"`、CUDA 可用性对应的 `fp16`、`verbose=False`、`word_timestamps` 和标点提示词。恢复源码和隔离回归已据此校正，全量门禁继续为 `128/128 PASS`。

`whisper_result_to_sentence_info` 主体 `0x1800090f0` 及 `flush` 闭包 `0x1800087d0` 也已逐分支恢复。原生逻辑按 word timestamp 累积文本，在命中句末标点、规范化长度达到 80 字或时间间隔达到 8.0 秒时 flush；没有 words 的 segment 走同样规则。输出毫秒使用 `int(max(start, 0) * 1000)` 与 `int(max(end, start) * 1000)` 截断，不做 `round()`，也不为最后一句自创标点。旧恢复版的毫秒四舍五入和末尾自动补句号已删除；负起点、非单调结束、80 字与 8 秒分界已加入回归，全量验证保持 `128/128 PASS`。

相邻文本链也已校正：`clean_whisper_text` 依次压缩全部空白、删除中英文标点前的空格、删除相邻汉字间的空白；`_segments_to_punctuated_text` 保留非连续 segment 的必要分隔；`whisper_result_to_text` 优先保留已有句末标点的顶层 `text`，仅在缺标点时借助 segments，最后才按中英文补默认结束符。二进制内嵌的双语 Whisper `initial_prompt` 也已逐字恢复，不再使用旧版自创文案。

Whisper 模型加载分支也已与主体 `0x180002920` 对齐：解析出的 `.pt` 存在时，直接将完整文件路径与 CPU/CUDA device 传给 `whisper.load_model`；仅文件不存在时才以 `large-v3 + download_root` 自动下载，并恢复两条原始中文诊断。`transcribe_with_whisper` 主体 `0x180004020` 没有预先检查本地文件是否存在，而是把 `audio_path` 原样交给 Whisper backend；恢复版已删除自创的 `Path.is_file()` 限制。本地模型、缺失模型自动下载参数和非存在输入转发均已加入回归，全量验证继续为 `128/128 PASS`。

### 在线音色生成

`tools/online_voice_generate/generate_voice.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-online-voice`，并导出函数表及 Minimax、DashScope/CosyVoice 全部主要业务主体到 `online-voice-core-decompiled`。本轮确认 `_minimax_headers` 只构造 `Authorization: Bearer <key>`，可选 content type 非空时才加入 `Content-Type`，不会在该底层帮助函数内自行拒绝空 key。阿里云运行时会保留输入配置，并同时写入 `base_http_api_url/base_websocket_api_url` 与 `http_url/websocket_url` 两组等价端点；这组契约已接入 `FaceHandLiveManager` 的 CosyVoice 运行时配置并加入大陆/国际区域回归。全量门禁保持 `128/128 PASS`。

模块初始化主体 `0x18001c410` 也已导出到 `online-voice-init-decompiled`，由其常量表恢复出完整语言矩阵。国际端点支持 `ar-sa、bahasa-malaysia、bahasa-melayu、de-de、en-us、es-es、fil-ph、fr-fr、id-id、it-it、ja-jp、ko-kr、ms-my、pt-br、ru-ru、th-th、tl-ph、vi-vn、zh-cn` 共 19 项；中国端点除 `de-de、fr-fr、pt-br、ru-ru` 外支持其余 15 项。`cosyvoice_language_hint` 现可将基础码、下划线 locale 和完整 locale 统一为原生小写 locale，并对未知值回退 `zh-cn`；区域差异和马来语、菲律宾语等路径均已加入回归。

### TTS 单任务限长链

`live/live_manager.pyd` 中的两个 Cython 函数已通过 Ghidra 12.1.4 定位并恢复：

```text
_limit_tts_synthesis_text(text)
  → strip
  → _tts_half_unit_length（ASCII/空白 1 个 half-unit，非 ASCII 2 个）
  → 未超过 _TTS_SYNTHESIS_MAX_HALF_UNITS：返回 (text, units, False)
  → 超限：逐字符累加并生成 candidate
  → _trim_tts_text_to_boundary(candidate, next_char)
  → 返回 (trimmed, actual_units, True)
```

边界回退搜索的下界为 `max(0, len(candidate)-80, int(len(candidate)*0.6))`；其中 `0.6` 已直接从 PE `.rdata` 的 `0x180120538` 读取确认。修整时强句界优先于软句界，并处理候选文本之后紧邻的标点，避免下一段以标点开头。`LocalLiveBrain._enqueue_tts` 已改为调用完整限长链，而不是此前的经验性单函数截断。

校验器同时新增模块级函数签名语义审计；当前类方法和模块函数均检查参数数量、名称、必填/可选状态与 `**kwargs` 契约。

### OmniVoice（voice_infer_v2）资源生命周期

本轮对 `bin/voice_infer_v2/infer_api.pyd` 建立了独立 Ghidra 工程，并反编译 `_is_model_ready`、`_check_and_download_model` 与 `clear`。恢复实现据此修正为：

- 优先识别交付包规范目录 `pretrained_models/OmniVoice`，兼容大小写目录及 `model.safetensors`、`pytorch_model.bin` 两种权重名。
- 使用原版属性名 `synthesizer` 管理 OmniVoice 实例，`model` 仅保留为兼容别名。

本轮为 `bin/voice_infer_v2/infer_api.pyd` 补建了持久化 Ghidra 工程 `rea-output/ghidra-voice-v2`，并定位 `VoiceSynthesizer.__init__` 包装体/主体 `0x180003870/0x180003f80`、`_get_voice_clone_prompt` `0x18000c620/0x18000c9c0`、`synthesize` `0x18000fb20/0x180010290`。合成主体确认整个请求运行在 `self._lock` 上下文内；调用参数的 `reference_audio/reference_text` 为空时才读取实例默认值，`reference_text` 会局部 `strip()`，但二者不会写回实例。缓存查询显式携带 `temp_dir、voice_id、text、speed、voice_infer_version、language、reference_audio、reference_text`，因此不同临时参考音必须生成不同缓存键。

旧恢复版没有实例锁，并会把单次调用的参考音和参考文本永久写回 `self`，后续请求会串用上一请求的音色，同时污染缓存查找和写入。现已在构造器补回 `_lock`，扩展共享 CacheMixin 让缓存读写接受调用级参考信息，并把 `synthesize()` 改为原生的局部覆盖语义；回归证明临时参考音参与缓存键但实例默认参考音保持不变。完整验证继续为 `128/128 PASS`。

同一 `synthesize` 主体还确认 `generate(...)` 返回的 `audio_list` 必须 truthy，否则显式抛出 `RuntimeError("OmniVoice 推理结果为空")`；该错误和其余合成异常统一由函数自身捕获，通过 `logging.error("OmniVoice 合成失败: %s", error)` 记录并返回 `None`，不会把模型异常抛给直播 worker。缓存命中记录“音频缓存命中，直接复用”，成功写音频后输出“语音合成完成，输出文件”。恢复版已补回空推理结果判断、异常边界和三类诊断，回归确认空生成列表按原生协议返回 `None`，全量验证保持 `128/128 PASS`。

构造主体 `0x180003f80` 进一步证实原程序并非延迟加载：创建锁后会规范化 CUDA/CPU 设备，CUDA 使用 `torch.float16`、CPU 使用 `torch.float32`，随后立即调用 `OmniVoice.from_pretrained(str(model_dir), device_map=self.device, dtype=self.dtype, load_asr=False)`。实例采样率读取 `synthesizer.sampling_rate`，假值回退 `24000` 并转为整数。恢复版已按此补回 eager 初始化、`dtype`、`model_dir`、`sampling_rate` 和三条初始化诊断。

`_build_prompt_cache_key` 包装体/主体位于 `0x18000ba70/0x18000be00`。原返回值不是哈希字符串：正常文件为 `(Path(reference_audio).resolve(), stat.st_mtime_ns, stat.st_size, reference_text)`，文件不存在时捕获 `FileNotFoundError` 并退化为 `(resolved_path, reference_text)`。恢复版此前自造的 SHA-256 键已删除，测试逐项比对路径、纳秒时间戳、大小和文本；相关反编译保存在 `rea-output/voice-v2-prompt-decompiled/`。
- `clear()` 删除 synthesizer、清空提示缓存、触发垃圾回收，并在 CUDA 可用时清空显存缓存。
- 新增无模型依赖的生命周期回归测试，验证规范模型目录发现和释放后的对象状态。

对应反编译证据保存在 `voice-v2-model-ready-body.c`、`voice-v2-download-body.c`、`voice-v2-clear-body.c` 及其 wrapper/ref 文件。

### IndexTTS（voice_infer_v3）生命周期与合成链

完成 `bin/voice_infer_v3/infer_api.pyd` 的独立 Ghidra 工程 `rea-output/ghidra-voice-v3`。构造包装体/主体为 `0x180001070/0x180001780`，模型目录包装体/主体为 `0x180004810/0x180004980`，合成包装体/主体为 `0x180007ac0/0x180008230`，清理包装体/主体为 `0x18000af80/0x18000b0f0`；完整函数表和核心反编译分别保存在 `voice-v3-functions.tsv` 与 `voice-v3-core-decompiled/`。

构造主体证明旧恢复版的延迟加载不正确。原程序创建 `_lock`，把不可用的 CUDA 请求回退到 CPU，以 `device.startswith("cuda")` 设置 `is_fp16`，解析 `models_base_path/model_dir`，清理参考文本两端空白，然后立即构造 `IndexTTS(cfg_path=str(model_dir/"config.yaml"), model_dir=str(model_dir), is_fp16=self.is_fp16, device=self.device)`；实例采样率固定为 24000。恢复源码现已补齐这条 eager 初始化链。

合成主体在实例锁内使用调用级 `reference_audio/reference_text`，并把二者显式传给音频缓存查询和记录，不会污染实例默认参考音。模型推理位于 `torch.inference_mode()` 中，调用 `infer_fast(reference_audio, text, raw_path, verbose=False)`；非 1.0 倍速再走 atempo 输出。异常由函数自身记录并返回 `None`。`clear()` 删除模型、执行 GC，并在 CUDA 可用时清理显存。新增无真实权重的生命周期回归，验证 CUDA 回退、四个 IndexTTS 构造参数、24000 采样率、推理参数、调用级参考音隔离和释放状态；全量门禁继续为 `128/128 PASS`。

### ZipVoice-Distill（voice_infer）生命周期

为 `bin/voice_infer/infer_api.pyd` 建立独立工程 `rea-output/ghidra-voice-v1`。构造包装体/主体为 `0x180001070/0x180001780`，模型检查包装体/主体为 `0x180007f10/0x180008080`，合成包装体/主体为 `0x18000c640/0x18000cdb0`，清理包装体/主体为 `0x1800130b0/0x180013220`。函数表、状态初始化和核心反编译分别保存在 `voice-v1-functions.tsv`、`voice-v1-init-decompiled/` 与 `voice-v1-core-decompiled/`。

状态槽与构造主体确认模型生命周期也是 eager：`_lock`、`device`、`models_base_path`、`model_dir`、参考音/文本和 voice 元数据建立后，构造器立即加载 `tokenizer`、`model`、`vocoder`、`feature_extractor`，并从配置写入 `sampling_rate`。旧恢复版把这整条链延迟到首次 `synthesize()`，同时会把调用级参考音永久写回实例。恢复版现改为构造阶段完整加载，CUDA 不可用时回退 CPU；合成在锁内使用局部参考音/文本，并让两者参与缓存查询和记录；异常在函数边界记录并返回 `None`。`clear()` 删除四个持有权重或张量的对象，执行 GC 和 CUDA 缓存清理。

新增 ZipVoice 生命周期回归，验证 eager load、设备回退、模型目录、调用级参考音隔离、`generate_sentence` 的文本/参考音/速度/采样率参数及完整资源释放。全量验证仍为 `128/128 PASS`。

### 淘宝讲解循环状态

`tools/taobao_live_control.pyd` 的 `_stop_explain_cycle` 与 `_arm_explain_watch` 已由 Ghidra 函数体恢复，不再是固定返回占位：

- `_stop_explain_cycle` 依次清除 `_active_goods_id`、`_popup_pending`、`_explain_watch_until`、`_explain_fail_streak` 和 `_control_recover_streak`，并在存在 reason 时输出停止原因。
- `_arm_explain_watch` 使用 `time.monotonic()`，计算 `now + max(1.0, sec)`；只有新截止时间更晚时才更新 `_explain_watch_until`。
- `_initialize` 已补齐弹窗 pending、讲解监视、失败计数、控制页恢复计数/时间和页面就绪时间等持久状态。
- 校验器新增讲解循环回归测试，覆盖最短监视窗口、截止时间单调递增和停止后的完整状态清理。

反编译证据保存在 `taobao-stop-explain-body.c`、`taobao-arm-explain-body.c`、`taobao-pump-popup-body.c` 以及对应 wrapper/ref 文件；后者将继续用于恢复完整的弹窗重试与控制页回收状态机。

`_pump_active_popup` 的核心调度分支现已恢复：停止事件或无活动商品时直接返回；pending 请求绕过常规冷却，普通 tick 必须满足 `_popup_interval_sec`；执行前清除 pending；成功和异常均更新 `_last_popup_at`，避免失败后的忙重试；Playwright closed-target 异常会清空活动商品和 pending，并调用 `_do_recycle_page`。该函数与原二进制一致只承担 worker tick 副作用，返回 `None`，不再把 `_do_popup` 的布尔结果错误地作为公开结果。

回归测试覆盖冷却抑制、pending 立即执行、pending 清除、closed-target 状态清理与页面回收调用。

### 淘宝控制页自愈

`_ensure_on_control_page`、`_recover_control_page` 和 `_do_recycle_page` 的二进制函数体已提取，恢复源码补入以下行为：

- 只有 Playwright、browser context 和 page 都存在且 worker 未停止时，才判定可继续；当前 URL 已是目标 `live/control?liveId=...` 时直接成功并清零恢复 streak。
- 偏离控制页时进入带冷却的恢复流程；普通失败采用短冷却，连续达到阈值后使用慢冷却，避免 Playwright/淘宝 SPA 故障时忙循环。
- 页面不存在或已关闭时从 context 创建新 page，再进入 `open_control_page`；成功后执行页面 settle、引导层清理、杂散页面关闭，并重置恢复计数、冷却和 `_page_ready_at`。
- closed-target 异常会丢弃失效 page，留待下次恢复重新创建。
- recycle 主动关闭当前 page、重新恢复控制页、清空讲解 watch；恢复成功且仍有活动商品时重新设置 popup pending。

校验器使用假 Playwright page/context 覆盖有效控制页快速路径、偏离页面恢复、新 page 创建、状态复位以及 recycle 后重新 pending。反编译证据见 `taobao-ensure-control-body.c`、`taobao-recover-control-body.c` 和 `taobao-recycle-page-body.c`。

淘宝 worker 的周期维护链也已补齐：

- `_settle_control_page` 等待商品 DOM（180 秒上限），关闭新手引导/讲解弹窗，并按 `comment_wait_ms` 等待评论区域；原先把任意等待截成 500ms 的近似实现已移除。
- `_pump_control_stay` 仅在 worker 未停止、Playwright/context 存在且 page 存活时调用 `_ensure_on_control_page(reason="control-stay")`。
- `_pump_page_recycle` 使用 `_page_ready_at` 与 `_PAGE_RECYCLE_INTERVAL_SEC` 做时间门控，再执行回收。
- `_worker_loop` 每个 tick 依次运行 control-stay、讲解确认、活动商品弹窗和 page-recycle；此前只运行弹窗，长期运行时页面自愈链实际上不会触发。

回归测试新增商品/评论 selector 等待参数和 recycle 时间门控。证据见 `taobao-settle-control-body.c`、`taobao-pump-stay-body.c` 与 `taobao-pump-recycle-body.c`。

动作分发与断开生命周期也已按 `_handle_action`/`disconnect` 函数体收紧：`set_active_goods` 将间隔钳制到二进制 `.rdata` 中确认的精确下限 `5.0` 秒，只设置 active/pending 并清零讲解失败和控制页恢复 streak，返回 `True`，不再同步触发浏览器弹窗。`disconnect` 会先以 `reason="disconnect"` 停止讲解循环，再安全关闭浏览器并清除初始化状态；worker 的 `disconnect` 动作返回 `True`。校验器覆盖间隔钳制、状态复位、关闭动作和未知 action 异常。证据见 `taobao-handle-action-body.c`、`taobao-disconnect-body.c`，常量位于 PE RVA `0xA0938`。

### Shopee 商品轮播状态

`tools/shopee_live_control.pyd` 的 `_handle_action` 与 `_pump_active_popup` 已单独建立 Ghidra 工程并提取函数体，不再沿用同步点击的兼容实现：

- `set_active_goods` 从 payload 读取商品 ID 和间隔，空间隔回退默认值，并按 PE `.rdata` RVA `0x82528` 的精确常量 `5.0` 秒钳制下限；随后设置 `_active_goods_id`、`_popup_pending=True` 并返回 `True`，浏览器点击留给 worker tick。
- popup pending 可绕过常规间隔；执行前清除 pending，成功或异常都用 `time.monotonic()` 更新 `_last_popup_at`，避免异常忙重试。
- closed-target 异常清空 active/pending，并执行安全浏览器关闭。
- `clear_active_goods` 只清 active/pending，不会错误断开浏览器；`disconnect` 才执行安全关闭、清除连接状态并返回 `True`。

回归测试覆盖最小间隔、pending 立即执行、冷却抑制、closed-target 清理，以及 clear/disconnect 的边界。反编译证据保存在 `shopee-handle_action-body.c`、`shopee-pump_active_popup-body.c`、`shopee-disconnect-body.c` 和 `shopee-shutdown-body.c`。

Shopee 的关闭生命周期进一步由 `_safe_close_browser` 函数体校准：内部关闭不再递归调用公开 `disconnect`，而是原子地清除 `_connected`、`_session_id`、`_initializing`，先保存 browser，再摘除 browser/context/page 引用，最后调用 `_disconnect_cdp`。`shutdown` 按二进制顺序先尝试 disconnect，即使失败也继续设置 stop event、向命令队列投入哨兵、等待 worker 并清空线程引用。回归测试验证 browser 只断开一次及全部状态引用被清理。证据见 `shopee-safe-close-body.c`、`shopee-disconnect-body.c` 和 `shopee-shutdown-body.c`。

`connect` 与 `_do_connect` 的函数体也已提取（`shopee-connect-body.c`、`shopee-do-connect-body.c`）。公开 `connect` 通过 worker `_call` 调度；内部连接开头先执行 `_safe_close_browser`，随后建立 CDP browser，并由 `_cdp_context_and_page(..., prefer_live=True)` 解包 context/page。对 2559 行主体的源行边界、helper 引用和字符串表继续分析后，连接后的页面状态机也已落到恢复源码：`_restore_connected_page` 保留登录页供交互登录；已登录 seller centre 会恢复店铺名，并按页面 URL/localStorage、持久化 storage 的顺序恢复 session；存在 session 时进入 `/pc/live?session=...` 并等待直播控制台，不存在 session 时进入 `/pc/sessionList`。最终 storage 同时保存 shop、session 与当前页面状态；任何连接/跳转异常仍统一 `_safe_close_browser` 回滚。回归覆盖登录页不跳转、无 session 的 seller centre、持久化 session、已处于直播控制页及 CDP 失败清理，全量验证为 `128/128 PASS`。

连接入口的第一阶段现已落到源码：worker 的 `connect` 直接进入 `_do_connect`；内部连接在锁内拒绝重复连接，清理旧 browser，设置 `_initializing`，复用或启动 Playwright，确保调试端口、连接 CDP、选择 live page，并从 URL/localStorage 或持久化状态恢复 session。成功写回 storage 并置 `_connected=True`；任何异常都会记录错误、执行 `_safe_close_browser` 并返回 `False`。回归测试覆盖 `headless` 参数传递、live page/context 绑定、session 写回以及 CDP 失败后的完整回滚。

Shopee 页面状态判定的六个缺失私有函数现已从各自函数体、嵌入 docstring、selector 与 JavaScript 常量恢复：`_page_is_login_surface`、`_page_has_seller_centre`、`_page_has_live_workspace`、`_page_looks_logged_in`、`_page_is_live_control`、`_page_looks_living`。登录 URL、账号/密码输入框以及滑块/验证页优先否决登录态；卖家中心账号 DOM、live workspace 或认证 cookie 可证明已登录；中控页必须包含 `live.shopee.../pc/live?session=`，并由评论框、`Shop Name`、`End Live` 或可见 `Products` 工具入口确认；正在直播则进一步要求评论框或 `End Live + Shop Name`。异常均按二进制返回 `False`。对应证据见 `shopee-page-*-body.c`，回归测试覆盖登录页、卖家中心、认证 cookie、直播中控、在播状态和验证码否决路径。

Shopee 登录与持久化链继续补回 `_maybe_hydrate_cookies_from_storage`、`_merge_storage_meta`、`_dismiss_modals`、`_wait_until_logged_in`、`_scrape_shop_name`、`_resolve_shop_name`。旧 storage JSON 只在 Chrome profile 缺少认证 cookie 时灌入；状态保存采用临时文件原子替换，合并 storage state、用户 ID、站点、页面 URL、session 和店铺名；店铺名依次从账号 DOM、`Shop Name:` 文本、`@shopee/account-basic-info` localStorage 和持久化状态解析。连接完成后已执行 cookie hydration，控制器保存路径统一走元数据合并。测试在临时目录验证 cookie 迁移和 JSON 写回，不触碰真实账号数据。

按 `.pyd` 限定函数名与恢复源码 AST 的严格差集，Shopee 模块的业务私有函数缺口已从 18 个缩小到 9 个：`_ensure_chrome_running`、`_stop_chrome_debug`、`_mid_control_busy`、`_read_products_from_local_storage`、`_wait_until_live_control`、`_collect_session_products`、`_wait_until_products`、`_products_panel_ready`、`_open_products_panel`。

上述 9 个缺口现已全部补回。商品链同时读取 `shopee-live-streaming-STORAGE_PRODUCTS_<sid>` 与商品表格 DOM，标准化后按 item ID 去重并重排 `goodsIndex`；`_open_products_panel` 优先点击 `contentText` 工具块，回退到可见的精确 `Products` 文本元素；面板就绪以表格中的 `Show/Showing` 操作为准。`fetch_shopee_session_products` 已改为等待 live control、打开商品面板并走统一商品等待链，而不是只盲扫当前 DOM。

Chrome 调试生命周期补入模块级锁和已启动进程句柄：`_ensure_chrome_running` 复用可用端口、清理已退出句柄、启动 Chrome 并等待 CDP；失败时回收本模块句柄后抛出明确错误。`_stop_chrome_debug` 只 terminate/kill 本模块实际保存的子进程，不按名称或端口误杀用户浏览器。测试覆盖启动、复用句柄和停止清理。

当前严格审计结果为 `SHOPEE_PRIVATE_FUNCTION_GAP []`：`.pyd` 中 54 个模块级限定函数名（排除 Cython 内部 scope/default 对象）均已在恢复源码中存在。该结论证明函数覆盖清零，不替代真实 Shopee 网站和 Windows Chrome 环境的端到端行为验证。

### 全包私有函数覆盖审计

严格审计已从 Shopee 扩展到全部 128 个第一方 `.pyd`：读取二进制中的模块限定名，排除 `__pyx_scope_struct_*`、`__defaults__` 等 Cython 运行时对象，再与实际导入后的恢复模块属性对比。首轮发现 21 个模块、75 个真实候选缺口；当前已全部清零，并将同一审计固化为 `verify_binary_qualified_module_names()`，不再依赖一次性脚本。

- `tools/llm/llm_reply` 的 8 个缺口已清零：语言解析、多语言/越南语判定、语言规则、翻译提示、persona 提取/拼接和多语言 fallback。接口采用二进制中提取的 Cython 类型签名。
- `live/live_manager` 的 3 个缺口已清零：16-bit 单声道 PCM 封装 WAV、越南语判定和中文数字；WAV 头、采样率及帧数均有回归断言。
- `live/face_hand_live_manager` 补回进场消息识别和互动消息类型归一化。
- 原始帧/v2 的四个 frame-player 包装模块补齐 KT overlay 与输出采样率私有接口；严格签名测试发现原二进制只接受两个参数，因此使用二参数适配层保留精确调用契约。
- realtime/RTMP face-reader 包装模块补齐 `_env_int`/`_env_float`；两代 image-infer 入口补齐 `_resolve_output_sample_rate`。
- `bin/video_player/infer_api` 补齐并接回 ffmpeg/ffprobe 定位、FPS 分数解析、stderr drain、进程 terminate/kill 回收和输出采样率协商。
- 淘宝控制模块补齐 Chrome 路径、storage context、Cookie 解码、登录等待、遮罩关闭、直播列表解析和最新未开播计划选择。
- 商品 KT 模块补齐白板检测、marker blob、NMS、中心/四角选择、缺角推断、四边形评分/扩展和 board-overlap，并接回 `detect_kt_board_quad`。
- `ip_agent/post_process` 的 FFmpeg、音乐、字体和封面私有函数完整转出；此前内联的颜色、模板、标题换行、画布裁切和原子下载接口也已恢复。
- 两个离线 frame-synthesizer CLI、快手直播 CLI、虚拟摄像头 creation flags 和 Windows EcoQoS 底层调用均已补齐。

全量校验仍通过：128/128 路径映射、模块导入、公开与私有限定函数清单、二进制类方法清单、类/模块函数签名、核心管理器行为和直播协议测试。`STRICT_QUALIFIED_FUNCTION_GAPS {}` 证明当前已知模块级函数名覆盖清零；它不证明每个函数与原二进制逐分支等价，后续仍需继续扩大行为测试和真实运行链验证。

`live/live_manager.pyd` 已建立独立 Ghidra 工程并导出函数表。`LiveManager._build_minimax_runtime_config`（主体 `0x1800b7380`）与 `_build_cosyvoice_runtime_config`（主体 `0x1800b7c20`）确认运行配置不是在全局配置和声音选择中二选一：原版复制对应的全局 provider 配置，再分别从 `voice_general_config["minimax"]`/`["cosyvoice"]` 读取 `minimax_voice_id`/`cosyvoice_voice_id`，执行 `str(...).strip()` 后覆盖。恢复版已按此修正，避免直播启动时丢失用户当前选择的云端音色，并增加配置隔离、去空白和空 ID 回归断言。

`LiveManager.prepare_multilingual_audio_cache` 的包装体为 `0x18007bd60`、主体为 `0x18007c310`。已确认它先规范化并校验主音色，用 `slice_content` 拆分主播/助播话术，再从 `shift_schedule` 和 `multi_product_configs` 收集 `voiceModelId` 及附加话术；候选文本经 `_expand_cache_text_candidates` 展开、`_limit_tts_synthesis_text` 限长后按“文本/音色/语言”去重。每项通过 `_ensure_voice_synthesizer(voice_id, voice_infer_version)` 取得合成器，并以 `speed`、`language`、`use_cache=True` 预热。恢复版现已覆盖主/助播、换班、多商品四类音色与五类候选文本，异常时保留 `last_error`、打印 traceback 并返回 `False`。

同一工程中 `LocalLiveBrain._drain_pending_script_tts` 的主体位于 `0x18002f3d0`。反编译确认它在锁内把 `_pending_script_tts` 原子替换为空列表，再逐个解包 `(text_snapshot, product_index)`，调用 `_enqueue_tts(text_snapshot, queue="normal", target_face_index=0, use_silent_features=False, product_index=product_index)`。此前恢复版错误地把该方法缩成 `_tick_rewrite_pool()`；现已恢复独立 pending 列表、锁、原子快照和精确发射参数，回归测试覆盖两项顺序与列表清空。

通过反编译字符串常量初始化体 `0x1800cc160`，现可把 Cython 模块状态槽精确映射回字符串名；例如 `0x1268 → _drain_pending_script_tts`、`0x2e68 → _tick_lock`。据此确认 `LocalLiveBrain.tick` 主体 `0x1800237a0` 先检查 `_stopped`，对 `_tick_lock` 执行 `acquire(blocking=False)`，随后严格按 `_drain_simulated_questions`、`_drain_manual_speaks`、`_drain_pending_script_tts`、`_tick_interactions`、`_tick_broadcast`、`_tick_rewrite_pool`、`_tick_shift_schedule` 的顺序执行，并在 `finally` 中释放锁。恢复版已补齐 `_lock`/`_tick_lock`、非阻塞防重入和精确调用顺序；测试覆盖正常顺序、锁占用跳过和停止后跳过。

广播水位的上游 `LiveManager.get_queue_lengths` 主体 `0x18008ff30` 也已恢复。原版返回固定四键：播放器当前 `normal`/`danmu` 长度，以及 `_pending_audio_snapshot()` 中独立的 `pending_normal`/`pending_danmu`；播放器不存在或查询抛出异常时前两项归零，但 pending 计数保留。此前恢复版继承父类，只返回播放器字典，导致 `_tick_broadcast` 无法看到正在合成但尚未入播放器的音频。现已补齐独立实现及正常/异常回归。

真正的模块顶层执行体为 `0x1800f6230`；其中 `BROADCAST_QUEUE_TARGET` 指向缓存整数槽 `0x3390 = 1000`，`TTS_PIPELINE_DEPTH` 与 `TTS_EMIT_BURST_MAX` 均指向 `0x32d0 = 4`。`LocalLiveBrain._tick_broadcast` 主体 `0x180024f30` 据此恢复为：改写任务或原始空闲视频模式下直接返回；每 tick 最多循环四次；每次重新读取 `normal` 与 `pending_normal`，pending 达到 4 或播放器 normal 达到 1000 时停止；其后分别进入音频索引、多商品和普通脚本路径。旧恢复版只要 normal 非零就停止且多商品路径递归调用自身，与原控制流不符。现已消除递归并加入普通脚本循环、两级背压、音频索引及当前商品脚本选择回归，完整验证继续通过 128/128。

多商品主体 `0x180027460` 与音频索引主体 `0x18002afe0` 已进一步逐分支恢复。顶层执行体确认 `PRODUCT_SWITCH_QUEUE_THRESHOLD = 0`；多商品路径以 `product_script_groups[current_product_index % len(...)]` 取组、读取组内 `items`，用独立 `product_item_cursor` 推进。索引小于 0、空组或多组播完时，只有 normal/pending 队列均为空才切换商品；单组播完则把游标归零继续循环。音频模式在 `script_audio_count <= 0` 时跳过，播放列表为空时重建 `list(range(count))`，随机模式调用 `random.shuffle`，随后 `pop(0)` 并发出 `play_audio_index`，载荷固定包含 `queue="normal"` 和 `target_face_index=0`。恢复版已替换此前简单递增索引及平铺商品脚本的近似实现；队列等待、商品轮换、顺序音频及完整任务载荷均有回归断言。

`LocalLiveBrain._emit_script_item` 主体 `0x180028b70` 的 item 协议也已恢复。完整状态槽解码确认类型字段为 `type`，支持 `host`、`assistant`、`pause`：host 读取 `content`，按 `rewrite_every_sentence`、`script_rewrite_interval`、`last_script_rewrite`、LLM 配置及 normal 队列低水位决定是否提交间隔改写，再执行 `process_special_variables` 并以普通主播参数合成；assistant 同样处理特殊变量，使用 `assistant_voice_id or voice_id`，双主播模式下目标脸为 1 且不使用静默特征，单主播模式相反；pause 仅接受正 duration 并发出 `pause` 任务。模块顶层常量还确认 `TTS_BACKLOG_LOW_WATERMARK = 250`。商品脚本规范化现生成原生 typed item，三种类型、助播音色/脸索引和零时长过滤均加入回归，128/128 全量验证通过。

间隔改写外层 `0x180032970` 与其 worker `0x180030480` 进一步确认：执行器优先取 `_interaction_llm_executor`，否则取 `_rewrite_executor`；没有执行器返回 false，提交前置 `_interval_rewrite_inflight = True`。worker 调用 `script_rewrite_content(text, special_instructions)`，再执行 `process_special_variables(...).strip()`，持有 `_lock` 时仅在未停止状态把 `(final_text, product_index)` 追加到 `_pending_script_tts`，最终无条件清除 inflight。异常日志分别为“话术重写失败”和“话术重写收尾失败，回退原稿”，失败路径保留原稿而不是静默丢句。恢复版已移除自创的文本集合去重状态，并把错误实现为 `Queue` 的 `rewrite_pool` 恢复为列表 FIFO；同步成功、LLM 异常回退和 inflight 清理均有确定性执行器回归。

互动口播入口 `_speak_interaction_reply` 主体 `0x180033610` 确认返回严格布尔值：先将 `reply or ""` 执行 `strip()`，空字符串返回 false；调用 `contains_blocked(text, self.reply_blocked_keywords)`，命中回复禁词同样返回 false；通过后打印最多 80 字的“[互动] 生成回复”诊断，并调用 `_enqueue_tts(text, queue="danmu", target_face_index=0)`，最后返回 true。此前恢复版没有禁词过滤，可能把被配置禁止的 LLM 回复直接播出。现已补齐配置字段、过滤和精确载荷，测试覆盖正常、禁词和纯空白三条路径。

淘宝场控回复规范化主体 `0x1800343a0` 也已逐分支恢复。该函数运行时导入 `tools.taobao_live_control.COMMENT_MAX_LEN` 并转为整数；淘宝控制扩展的 `PyModuleDef` 执行槽定位到 `0x180084d40`，其中名称槽 `+0xf0` 的值来自缓存整数槽 `+0x1910`，常量初始化体 `0x180084030` 明确以 `PyLong_FromLong(0x32)` 创建该值，因此长度上限为 50，而非经验猜测。昵称先 `strip()`，空值回退字符串槽 `+0xbb8`；对应 UTF-8 原始字节 `e794a8e688b7` 解码为“用户”。回复已以目标 `@昵称` 开头时保留；不以 `@` 开头时添加 `@昵称 `；以其他 mention 开头时按首个空格分割并替换 mention。随后执行 `" ".join(text.split())` 压缩全部空白、按 50 个 Python 字符截断，最后 `strip()`。恢复版已移除错误的 `{nickname}` 模板替换逻辑，并在数字人和手势直播管理器中统一该行为；回归覆盖正确 mention、错误 mention、空昵称、空白折叠和 50 字边界。

`LocalLiveBrain._send_taobao_control_reply` 主体 `0x180035850` 确认并不发内部 UI task。原版先对回复 `strip()` 并调用 `contains_blocked(..., reply_blocked_keywords)`；通过后调用模块级 `get_taobao_controller()`，检查 `controller.connected()`，再直接执行 `controller.send_comment(text)` 并返回其严格布尔值。未连接、发送成功和异常三条 PE Unicode 字符串分别为“`[local.live] AI场控发送跳过：中控台未连接`”、“`[local.live] AI场控发送: `”和“`[local.live] AI场控发送失败: `”，成功日志只展示前 50 字。恢复版已按该同步调用链替换此前自创的 `taobao_send_comment` 任务，测试覆盖断连、成功、禁词和异常。

场控 LLM worker `0x180036bb0` 与外层提交体 `0x180038010` 随后恢复。外层在 `_stopped` 时直接返回，否则快照 `_interaction_llm_executor`、`language`、`qa_info`、`special_instructions`，构造 worker 后优先 `executor.submit(worker)`，无执行器时同步运行。worker 调用公开 `generate_text_reply(nickname, content, product_info, qa_info, special)`；空返回时中文兜底为 `@昵称 收到，请稍等主播回复哦`，越南语槽对应 `@昵称 Mình đã收到您的提问。`。结果经 `_normalize_control_text_reply` 处理，仅在会话仍未停止时打印最多 80 字的“`[互动] 场控回复：`”并调用 `_send_taobao_control_reply`；异常使用“`[local.live] AI场控 LLM 异常: `”记录。此前恢复版错误调用私有配置型函数、复用普通互动去重器并把场控回复加入 TTS，现在已恢复为淘宝评论专用链。同期确认二进制 `_stopped` 是普通布尔字段，恢复版已由始终 truthy 的 `threading.Event` 改为布尔状态，避免场控提交被永久短路。全量验证继续为 128/128 PASS。

智能点品主体 `0x180038900` 进一步确认时间源为 `time.time()`，而不是单调时钟；只有 `last_dianpin_at > 0` 才检查冷却，实际阈值为 `max(dianpin_cooldown_seconds, 5.0)`，因此配置 0 也保留五秒防抖。冷却命中时以 `int(max(cooldown - elapsed, 0))` 输出“`[local.live] 智能点品冷却中，剩余N 秒`”。普通视频模式调用 `_jump_to_digital_dianpin(product_index, matched_keyword, content=content)`，仅成功后更新 `last_dianpin_at`。`origin_idle_video_mode` 则不切换脚本游标：从匹配目标读取 `start_ms`（缺省 0），生成点品转场文本，以 `queue="danmu"`、`target_face_index=0`、`seek_after_ms=start_ms` 入 TTS，更新时间并调用 `_sync_product_ui(product_index)`。恢复版已补齐两条模式、五秒下限、失败不更新时间及命中诊断；边界测试覆盖 4.9/5.0 秒和 2345ms seek，完整验证仍为 128/128 PASS。

`LocalLiveBrain._tick_interactions` 的包装器位于 `0x1800418b0`，真实主体位于 `0x180042ac0`。通过模块字符串槽表反查，已确认它使用 `comment_reply_interval`、`entrance_reply_interval`、`follow_reply_interval`、`gift_reply_interval` 四路开关，以及 `last_comment_reply`、`last_entrance_reply`、`last_follow_reply`、`welcomed_nicknames`、`exclude_nicknames`、`blocked_users` 等独立状态；消息来自 `interaction_messages` 上的 `_pick_comment` / `_pick_unprocessed`，而不是从自创 `_messages` 队列取一条后套 `interaction_replies` 固定模板。恢复版现按四类消息分别执行节流、用户过滤、问题禁词、智能点品和 `reply_danmu` / `reply_enter` / `reply_follow` / `reply_like` LLM 链，进场昵称写入去重集合，弹幕可并行提交淘宝 AI 场控；`100000` 关闭哨兵也与二进制保持一致。新增确定性回归逐项验证四个公开 LLM 函数的参数与四条 TTS 输出，全量验证继续通过 128/128。

同一主体尾部的 retention 随机触达链也已恢复。槽表确认开关与时间戳分别为 `mention_interval`、`last_mention`，LLM 函数为 `reply_retention`。原版在 `_lock` 内遍历 `interaction_messages`，提取并清理昵称，用集合去重并过滤 `exclude_nicknames` 与 `blocked_users`，候选达到 8 个即停止；非空时用 `random.choice` 选择昵称。有 LLM 配置时提交 `reply_retention(nickname, active_product_info, special_instructions)`，否则直接生成 `_fallback_reply_text(language, "retention", nickname, "")` 并口播，最后更新时间戳。恢复版已实现该链，回归覆盖重复昵称、黑名单、主播排除、8 人上限、LLM 参数、本地兜底与关闭哨兵；全量验证保持 128/128 PASS。

其上游 `LocalLiveBrain.submit_danmu` 包装器为 `0x18001f410`、主体为 `0x18001f6d0`。二进制明确构造模块级 `InteractionMessage(msg_type, nickname, content, timestamp)`，第五字段 `processed` 使用 dataclass 默认 `False`；`INTERACTION_MESSAGE_CAP` 指向整数缓存槽 `+0x3380 = 500`。输入昵称按 `nickname → user → ""`、正文按 `content → text → ""` 回退并直接 `strip()`，类型按 `msg_type → type → kind → "弹幕"` 交给 `_normalize_message_type(..., content=content)`，时间为 `float(message.get("timestamp") or time.time())`。空昵称及与 `live_streamer_name` 相同的主播本人消息不入队；进场消息 `insert(0, ...)` 后超限保留前 500 条，其他消息尾部追加后超限保留后 500 条，全部在 `_lock` 内完成。恢复版已删除自创 `received_at` 字典与 `_messages` 消费队列，统一使用 dataclass 和中文事件枚举；测试覆盖多键回退、空白清理、字符串时间戳、主播过滤、满队列进场优先、大小写敏感类型及 505 条裁剪，全量验证继续通过。

`LocalLiveBrain._enqueue_tts` 的包装器位于 `0x1800585a0`，真实主体为 `0x180058ae0`。该方法并不调用 `_limit_tts_synthesis_text`；此前恢复版在此截断文本属于错误近似。原链先执行 `strip_prohibited_words(text, self.prohibited_words).strip()`，再调用 `filter_han_for_language(text, self.language)`；过滤后仍有文本则使用过滤结果，若目标语言禁止汉字、过滤结果为空但原文含汉字，则保留原文并设置 `needs_language_translate=True`，其他空结果直接丢弃。它发出的 `tts_speak` 载荷固定包含 `text`、`voice_id`（显式参数否则实例默认）、`voice_infer_version`、`language`、`speed`、`queue`、`target_face_index`、`use_silent_features`、`use_cache`、`needs_language_translate`，并可选加入整数化的 `seek_after_ms` 与 `product_index`。音色通用配置优先取 `voice_general_config_map.get(str(voice_id or ""))`，无匹配时回退 `voice_general_config`，truthy 时写入载荷。恢复版已按此替换四字段简包；回归覆盖自定义违禁词、英文混合汉字过滤、纯汉字翻译标记、音色映射/回退、语速、缓存开关、seek 整数化和空文本丢弃，全量验证继续为 128/128 PASS。

商品位置查找的两个主体 `0x18003aa80`（`_find_product_group_index`）和 `0x18003b800`（`_find_product_script_cursor`）均不是“商品编号即列表下标”。二者分别遍历 `product_script_groups` 与 `script_list`，对元素的 `product_index` 和目标参数都调用 `int()`，相等时返回 `enumerate` 得到的真实列表位置；单项出现 `TypeError` 或 `ValueError` 时跳过，全部未命中返回 `None`。旧恢复版前者把商品号直接当下标，后者不转换元素值且遇坏项会中断。现已恢复稀疏编号、字符串编号和坏数据容错，并加入非连续 8/3 与 7/2 的回归用例。

商品信息解析主体 `0x18003c580` 也已恢复。原版从 `self.config.get("product_scripts") or []` 逐项遍历，分别对项内显式 `product_index` 与目标参数调用 `int()`；编号相等后读取同一项的 `content`，仅当内容 truthy 时执行 `str(content)` 并返回。单项的 `TypeError`/`ValueError` 被捕获后继续扫描；未命中、内容为空或列表为空时返回实例字段 `self.product_info`，并不会按列表下标读取，也不会自行尝试 `description`、`name`。恢复版已移除这些自创回退，初始化实例级 `product_info`，测试覆盖字符串编号、非字符串内容、空内容、坏项与全局回退。全量验证保持 128/128 PASS。

### 行为占位清理

`tools/auto_live_action/main.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-auto-live/auto_live`，导出完整函数表，并将 `VisualLiveAction` 与 `LiveControlAPI` 的包装器/主体逐一映射到 `auto-live-decompiled`。首个已确认的行为偏差位于 `_add_random_spaces`（`0x18001eee0/0x18001f110`）：原版对少于 6 字的文本原样返回；其余文本从内部位置固定抽取最多 5 项、排序后逐项插入 `random.choice([1,2,3])` 个空格，且不会因前一次插入修正后续索引。恢复版原先只插入 1–3 个单空格，现已按函数体修正并加入确定性随机回归；全量验证继续为 `128/128 PASS`。证据见 `rea-output/auto-live-action-notes.md`。

同模块 `stop_danmu`（`0x18001e8f0/0x18001ea60`）也已按主体恢复：清除运行标志后，对已有弹幕线程执行 `join(timeout=1)`，响应严格只有 `success/config` 两键，不清空线程引用。旧恢复版没有等待线程且自创了 `message` 字段；现已修正并加入假线程生命周期断言。

`get_config`（`0x18000dc80/0x18000ddf0`）进一步确认原版返回固定 12 键，而不是直接展开任意配置：七项允许配置、三个运行状态、`vietnam_pack` 和条件性的 `ui_labels`。PE 常量区内 29 项越南语标签及两段 HTML 操作说明已逐字恢复；越南客户包现在会正确本地化标题、按钮、状态、配置项和 OCR 定位说明，非越南包则返回 `ui_labels=None`。

`VisualLiveAction.send_danmu`（`0x1800012e0/0x180001530`）也已恢复为单坐标动作链：点击输入位置，三段各 0.2 秒等待之间依次执行剪贴板复制、`ctrl+v` 和 Enter；坐标或 GUI 依赖缺失时打印诊断并返回 `None`，成功同样隐式返回 `None`。旧版错误地维护 input/send 两套坐标、执行全选、在 Mac 使用 Command 并返回 `True`；`confirm_position` 现在把识别出的输入坐标对传入动作对象。

构造主体 `0x1800032b0` 还确认配置路径不是实例上的 `auto_live_action_config.yaml`，而是模块级 `tools/auto_live_action/config/config.yaml`。恢复树现补入同布局的默认配置资产，加载与保存统一走 `CONFIG_PATH`，保存前创建父目录；临时目录回归验证缺失配置回退、落盘内容和重新读取一致。

配置 API 也按主体收紧：`update_config`（`0x18000eb20/0x18000ed60`）只更新当前配置中已存在的键，因此能更新 YAML 自带的客户扩展字段但拒绝注入新键；`save_all_settings`（`0x18000a8c0/0x18000ab10`）改为 `_apply_settings(..., persist=True)`，成功文案精确为“配置已保存”，磁盘异常打印“保存失败”并返回 `success=False/message/config`，不再泄漏异常到前端。

`_apply_settings`（`0x18000b610/0x18000b910`）现已按原生主体完整恢复：弹幕列表逐项 `strip()` 并丢弃空项，`send_interval/work_minutes/rest_minutes` 经 `int()` 后下限钳制为 1，三个开关经 `bool()` 归一化；缺失键保留当前配置或原包默认值，客户扩展键不受影响。`persist=True` 时仅调用一次 `save_config()` 且方法返回 `None`。回归覆盖空白话术、字符串数字、负数与复选框值，全量验证保持 `128/128 PASS`。

`_danmu_thread`（`0x18001fa00/0x180020020`）的工作/休息双层循环也已落地。原版使用 `time.time()`，工作与休息分钟在入口乘 60；随机模式调用 `random.choice`，顺序模式用 `items[1:] + [items[0]]` 轮转本地列表。每次入队异常会单独打印“放入话术指令时出错”，外层异常打印“话术线程错误”，工作间隔和休息均为 `time.sleep`，不是旧恢复版的 `Event.wait`/单层单调时循环。

PE 文件偏移 242129 的 14,587 字节 `CONTROL_UI_HTML` 已原样取回，SHA-256 为 `e04ea27a1b22230879414a67fbfc1c36937bd06f3452c1704eed63f8081c4441`。恢复源码现使用完整设置、定位、多语标签、保存和启停 JavaScript 页面，不再是简化占位 HTML。构造主体还确认并恢复了 `Thread(target=self._run_http_server, daemon=True)` 的 `http_server_thread` 自启动；`main` 改用客户包标题、原页面和 WebView 关闭回调。全量验证仍为 `128/128 PASS`。

场控内部队列协议已从“纯文本队列”修正为命令队列。`_control_worker`（`0x180019020/0x180019190`）对 `"stop"` 结束标记特别处理，其他项按 `(method_name, *args)` 在 `VisualLiveAction` 上分派，并保留未知指令、单次执行异常、最终 `close` 和运行标志清理。弹幕线程与 `/send_danmu` HTTP 端点均改为入队 `("send_danmu", text)`；HTTP 服务器也恢复为原生 `HTTPServer`。`start_control/stop_control` 现支持幂等启动、无坐标时进入定位、停止定位队列、`stop` 入队、存活线程 `join(timeout=2)` 和异常响应；旧版自创的 `stop_event` 已删除。相关确定性回归已加入，全量门禁保持 `128/128 PASS`。

`confirm_position`（`0x180011c70/0x180013b00`）现已从直接调截图对象改回原生队列协议：向 `capture_cmd_queue` 发送 `"capture"`，对 `capture_res_queue.get(timeout=5)` 超时返回“获取截图超时”。OCR 匹配中/英/越输入提示和发送按钮关键词，将相对框坐标转为屏幕坐标；发送按钮未命中时，按所选矩形最右 15% 区域中心回退，即 `x = left + width * 0.925`、`y = top + height / 2`。输入提示坐标优先作为点击目标，否则使用发送/回退坐标。确认后停止红框、构造 `VisualLiveAction`并自动启动场控，成功响应严格为 `success/message/config`。回归已覆盖越南语 `Nói gì/Gửi`、坐标偏移、无 OCR 结果回退和响应键形，全量验证继续 `128/128 PASS`。

定位上游也已按主体恢复。`start_positioning`（`0x18000f480/0x18000f5f0`）在两个 `Queue.mutex` 内清除旧指令/结果，再启动 daemon `_capture_window_worker`；重入精确返回“正在定位中...”，成功文案为原生红框拖动说明。`_capture_window_worker`（`0x1800111c0/0x180011330`）才是 `CaptureWindow(capture_cmd_queue, capture_res_queue)` 的实际构造者，随后调用 `run()`，异常只打印“捕获窗口线程异常”；旧恢复版在入口提前构造窗口、在 worker `finally` 自创清空线程引用的行为已删除。队列清理、重入、线程参数与 worker 构造顺序回归通过，全量门禁仍为 `128/128 PASS`。

配置持久化的最后语义偏差同步清理：`load_config`（`0x180007720/0x180007890`）复制默认字典，对 UTF-8 YAML 的 falsey 结果使用空字典，再执行 `dict.update`，仅捕获 `FileNotFoundError`；非映射/损坏配置不再被静默忽略。`save_config`（`0x1800091a0/0x180009310`）使用 `yaml.dump(..., allow_unicode=True)` 写入文本流并隐式返回 `None`；旧版的 `safe_dump/sort_keys=False/True` 返回均非原生行为。场控定向回归已通过。

`start_danmu`（`0x18001cea0/0x18001d0f0`）随后恢复为原生两键响应，正常、空话术与可捕获异常都只返回 `success/config`。场控未运行时打印“请先启动场控。”；否则先执行 `_apply_settings(settings, persist=True)`，规范化后的 `danmu_list` 为空则不启线程。线程六个参数直接取自当前配置，不再进行旧版自创的列表复制和 `float/bool` 二次转换；异常打印“启动话术发送错误”并返回 false。未启动、空列表、持久化、线程 `target/args/daemon` 和列表同一性的定向回归通过。

相邻 `ocr_capture/capture_window.pyd` 已完成主体级恢复。独立 Ghidra 工程 `rea-output/ghidra-auto-live-capture/capture` 已导出 161 个函数并映射 `CaptureWindow` 全部 13 个方法；恢复版已对齐无边框置顶窗口、绝对边界坐标、四角缩放把手、20 像素下限、拖动、截图相似度基线以及每次最多消费一条指令的 100ms 队列调度。证据与定向回归见 `rea-output/auto-live-capture-notes.md` 和 `verify_capture_window_change_contract()`。

函数覆盖清零后又进行了一轮 `pass`、固定返回、`NotImplemented` 与“暂未恢复”文本审计：

- `origin_video_face_reader` 此前以 OpenCV 代替原二进制的 FFmpeg rawvideo 子进程，且 `_drain_stderr` 为空。现已恢复 `-stream_loop -1` 循环解码、BGR24 精确帧读取、stderr drain、seek 参数和 terminate/kill 回收；单元测试验证 raw frame 边界及告警管道。
- `Api.sync_taobao_products(source="plan")` 此前直接返回“暂未恢复”。现已恢复直播列表 API 响应解析、最新未开播计划选择、编辑页跳转、计划商品 DOM/API 提取，并与 `commodity` 分支统一返回结构。
- `BarrageCapture._clean_port` 此前为空。现会先回收自身旧子进程，再仅对 `pdd_ws_wrapper`、`tb_ws_wrapper`、`ocr_capture.py`、`ws_danmu_capture` 等已知捆绑 wrapper 清理端口占用，不误杀无关应用。
- `Api._start_live_locked` 的四个原始 live type 常量已核对：`digital_human`、`local_media`、`face_hand_live` 均有分支，`rtmp` 是视频源/推流相关值而非第四种 live type；未知值现在返回普通“不支持”错误，不再暴露恢复状态文案。

`origin_video_face_reader` 随后增加真实媒体集成验证：测试动态调用系统 FFmpeg 生成 64×48、25 FPS 的短视频，再实际执行 `start_capture`、读取 4 帧批次、`seek(120ms)`、再次读取和 `stop_capture`。帧尺寸、检测结果数量及最终子进程/线程清空均通过；这比仅用内存 pipe 验证更接近真实运行链。

### 可复现依赖环境

恢复源码新增 `requirements-core.txt`、`requirements-ai-cu118.txt`、`requirements-windows.txt` 和 `ENVIRONMENT.md`。版本全部从原交付包 `env/Lib/site-packages/*.dist-info/METADATA` 提取，并由 `verify_environment_manifests()` 在每次全量校验中逐项比对，避免手工版本漂移。标准环境为 CPython 3.10、Torch 2.6.0+cu118；RTX 50 系环境使用 Torch 2.8.0+cu128 与 onnxruntime-gpu 1.19.0。

当前 Mac 尝试安装原版 `av==14.1.0` 时被本机代理连接拒绝，因此 PyAV 播放链尚不能在此环境做真实解码验证；FFmpeg 子进程链已经完成真实文件验证。该网络限制不影响继续静态恢复，PyAV/CUDA 依赖将在具备包源的环境补测。

### IP Agent 与字幕真实媒体验证

IP Agent 后处理已经通过真实文件链：FFmpeg 生成 320×240、25 FPS、含 AAC 音频的输入视频；恢复源码成功提取首帧、生成 1080×1440 封面、合成 24 秒回退 BGM、混音并输出 H.264/AAC 视频，ffprobe 验证流类型与时长正确。该链已加入全量验证器。

字幕烧录测试发现当前 Homebrew FFmpeg 未编译 libass，原二进制使用的 `subtitles/ass` filter 在这台 Mac 不存在。恢复源码保留原 libass 高保真路径，并新增过滤器缺失时的 OpenCV/Pillow 回退：按 SRT 时间轴逐帧绘制、自动换行、描边、关键词高亮和 fade 动画，再用 FFmpeg 合并原音频。普通字幕与高亮+淡入淡出两条真实路径均已生成 H.264/AAC 文件，并纳入持续回归。

### 人脸人手与商品图像链

主 API 原先调用的 `face_hand_video_processor` 是早期简化实现，只做 FFmpeg `silencedetect`，没有执行二进制规定的输出规范。现已统一委托给按 `vad_split.pyd` 恢复的 energy-VAD 管线。真实测试将 1.2 秒含音频视频分别规划为两个人脸段和两个人手段，生成 manifest 后可被 `load_face_hand_video_group` 加载并通过校验；所有输出均由 ffprobe 确认为 1080×1920、25 FPS。

商品图像持续测试新增连通域去噪、box mask、NMS、主体框选择、BiRefNet mask 后处理、768×768 居中白底合成、640×640 绿幕适配和 1–10 级抖动边界。模型加载本身仍需 Torch、GroundingDINO 与 BiRefNet 权重，但模型前后的完整图像算法已在 Mac 上用合成图逐像素验证。

### 录播实拍报时链

真实测试使用 2 秒 H.264/AAC 视频和 0.6 秒旁白 WAV，依次执行原音轨抽取、指定区间静音、旁白 overlay、WAV 导出及视频重新封装；最终音频长度保持与原片一致，输出同时包含 H.264 与 AAC 流。

二进制字符串中的 `duration`、`waiting_seconds`、`is_running` 和循环状态揭示了此前遗漏的插播等待阶段。恢复源码现会把生成的插播视频登记进 session 临时文件，在 `insert_video()` 后轮询插播 worker，直至播放完成、会话取消或时长加安全余量超时，再统一删除文件。回归测试用异步假 player 验证 worker 等待、插入一次、文件删除和 session 复位，消除了原实现的临时视频泄漏。

### 离线形象克隆资源生命周期

`bin/image_clone/tools/frame_synthesizer/infer_api*.pyd` 的字符串表同时包含 `executor`、`ThreadPoolExecutor`、`ort_session`、`shutdown` 和 `VideoSynthesizer.__del__`，确认原实现会并行装载帧并在析构时回收线程池。恢复版现为每个 `VideoSynthesizer` 创建按 batch size 配置的帧加载线程池，`_load_batch_frames` 使用该线程池保持输入顺序并行读取；新增幂等 `close()` 和 context-manager 支持，关闭时取消未开始的任务并释放下层 ONNX session。析构只作非阻塞兜底，重复显式关闭或重复析构不会二次释放。

持续回归使用假的 executor、engine 和 native session 验证线程池、引擎和 session 均只关闭一次，引用最终清空；全量验证仍为 128/128 映射与导入通过。ONNX/CUDA provider 的真实显存释放效果仍需在 Windows/NVIDIA 环境用原模型观察。

模型资产解析也修正了一处会影响实际画质的偏差：交付包的 `input_mask.npy`、`input_mask_re.npy` 位于 `assets/pretrained_models/image_infer_v2`，与 `unet_v2.onnx` 同目录，而角色数据目录只包含 frames/positions。旧恢复版只从角色目录找 mask，实际会静默使用合成半幅 mask；现改为优先模型目录、再兼容角色目录。目录形式的模型参数优先采用配置清单明确指定且交付包真实存在的 `unet_v2.onnx`，仅在缺失时回退 `unet_v2_fix.onnx`。测试用不同内容的真实 NumPy mask 逐值确认加载来源和模型回退顺序。

交付的 373 MB `unet_v2.onnx` 图内字符串进一步确认其输入顺序与名称为 `source_img`、`ref_img`、`audio_feature`，输出为 `output`，和恢复运行时的 feed 映射一致；因此此处无需为适配测试环境改写模型契约。

保存帧变体的差异已进一步定位：`infer_api_save_frame.pyd` 的 `_process_batch` 比普通版多 `batch_start=0` 参数，并嵌有 `generated_face_with_landmarks_`、`generated_face_cropped_`、`landmarks_save_path` 等诊断输出。Ghidra 字符串交叉引用保存在 `save-frame-landmark-refs.tsv`、`save-frame-crop-refs.tsv`，相关模块初始化体保存在 `save-frame-process-batch.c`。当前生产输出的 `frames_dir/frame_*.jpg` 与两类写入当前工作目录的内部诊断图均已实现；精确绘制参数见下段。

独立 Ghidra 工程现已定位真正 `_process_batch` 为 `0x1800156f0`。文件名构造确认使用空保存根目录、固定前缀、`str(batch_start + batch offset)` 与 `.jpg`，即写入当前工作目录且索引不补零。进一步反编译 Cython 常量初始化函数 `0x18002b490`，确认诊断循环为 `range(2, 16)`：把局部 landmark 坐标取整后，以半径 2、绿色 `(0,255,0)`、实心 `-1` 绘圆，并在 `(x+3,y+3)` 处用 `FONT_HERSHEY_SIMPLEX`、字号 `0.4`、蓝色 `(255,0,0)`、线宽 1 标注索引。恢复运行时现按该参数输出 `generated_face_with_landmarks_<n>.jpg` 与 `generated_face_cropped_<n>.jpg`，并以调用级回归断言固定索引范围和 OpenCV 参数。

### ASR 与音频时长生命周期

`tools/asr/main.pyd` 的 `_temp.wav` 与 `remove` 证据对应识别转码文件清理。恢复版现在无论 Whisper 成功还是抛错，都会先释放模型、再删除临时 WAV，同时保留原异常；持续测试覆盖成功写出 TXT 与识别失败两条路径，确认不残留批量任务临时文件。

`tools/cloud_dh/audio_duration.pyd` 的字符串确认原实现使用 `librosa.get_duration` 作为 ffprobe 回退。恢复版现先查系统 ffprobe，再查可执行文件及源码祖先目录下的 `Library/bin`、`ffmpeg/bin`、`env/ffmpeg/bin`、`env_50/ffmpeg/bin`，与交付包实际布局一致；ffprobe 不可用时恢复 librosa 对 MP3/AAC 等格式的通用时长读取，WAV 标准库解析保留为最终回退。测试分别验证非 WAV librosa 路径和捆绑 ffprobe 定位。

### LLM 标题与话术泛化契约

`tools/llm/generate_title.pyd` 中的 `tags_match`、`tags_str`、DOTALL、逗号拆分和引号替换证明其 JSON 失败分支仍会单独提取标签。此前恢复版只提取 title 并丢弃 tags；现已恢复单引号/轻微破损 JSON 下的标签列表解析，同时保留标准 JSON 路径和 `#` 规范化，测试覆盖两类输出。

`tools/llm/generalize_sentences.pyd` 的 `deque`、`requests`、`window_size`、`popleft`、`wait_time` 表明原限流器使用一分钟滑动窗口，而非固定请求间隔；`\[(.*?)\]`、方括号内 `|` 模式、`all_variants`、`new_variants` 和 `generalized` 对应直播候选话术结构。恢复版现按滑动窗口限流，切句时把已有 `[候选一|候选二]` 视为不可拆的单元，输出 `[原句|新增变体…]`，可直接被 live manager 的候选展开器消费。测试覆盖标点切句、已有候选扩充、LLM 方括号返回去壳、去重和窗口淘汰。

### 短视频多语言语音路由

`tools/generate_short_video/audio_synthesis.pyd` 包含 `chinese/english/french/german/spanish/italian/portuguese/russian/japanese/korean` 及对应 `zh-*`、`en-*`、`fr-FR`、`de-DE`、`es-ES`、`it-IT`、`pt-PT`、`pt-BR`、`ru-RU`、`ja-JP`、`ko-KR` 常量。此前恢复版只规范化中英法，且日语、韩语短视频会错误落到 v2。现已补齐全部二进制可见别名：中文短视频使用 v2，多语言短视频与 IP Agent 使用 v3，其他旧场景保留 v1。参数化测试覆盖所有语言常量及场景路由。

相邻的 `bin/voice_infer_v2/infer_api.pyd` 还包含独立 `language_aliases` 以及 `zh-CN/zh-Hans/zh-SG/zh-TW/zh-Hant`、`en-US/en-GB/en-AU`、`ja-JP`、`ko-KR`、`my-MM`。OmniVoice 规范化现将这些区域代码映射到模型接受的 `Chinese/English/Japanese/Korean` 枚举（`my-MM` 保留规范小写代码）；此前 `zh-CN` 会未经转换直接传入模型。全部二进制可见别名已加入回归。

短视频口型渲染入口还补回 `enable_action_generalization`：生成请求中的值优先于全局配置并传入 `VideoStreamManager`，离线成片现在可按动作片段泛化而非始终顺序循环角色帧。假管理器回归验证构造参数、输出文件检查和 `stop_playing()` 清理。

`generate_lip_sync_video.pyd` 与 `main.pyd` 共同出现的 `video_info.yaml`、`create_time`、YAML `dump` 对应短视频持久化元数据。每次成功生成现在写入 ID、名称、模型 ID、模式、视频路径、音频路径和创建时间；`get_all_short_videos` 会回读这些字段，同时兼容旧版只有 `video.mp4` 的目录。持续测试实际生成元数据文件并通过主 API 列表回读。

### 形象克隆生成资源回收

`image_clone_api.generate_video()` 过去创建 `VideoSynthesizer` 后直接返回，新增的帧加载线程池和 ONNX session 只能等待 Python 垃圾回收。现已用 `try/finally` 显式调用幂等 `close()`；成功返回和推理异常都会立即关闭线程池并释放 session，原异常保持不变。回归测试用成功/失败两种假合成器确认关闭动作均执行。

`bin/image_clone/utils/video_preprocess.pyd` 的 docstring、`processed_frame`、`.npy`、NumPy `save` 和返回类型证明确认 `extract_frames()` 会先调用 `process_frame()` 统一为 720×1280 竖屏帧，逐帧保存 NumPy 数组，并返回整数帧数。旧恢复版错误地原尺寸写 JPG 并返回路径列表。现已改回 `<index>.npy` 与帧数契约；真实两帧视频回归验证中央 9:16 裁切、720×1280 输出、文件命名、帧数和像素顺序。

### PFLD-GhostOne 关键点骨干

`pfld_mobileone.pyd` 的 `AvgPool2d`、`avg_pool1..4`、`Linear`、`conv_out` 和五级 `multi_scale` 证据与公开上游 `AnthonyF333/PFLD_GhostOne` 的网络定义一致，交付版仅把默认参数改为 `width_factor=0.5`、`input_size=192`、`landmark_number=110` 并将最终线性层命名为 `conv_out`。旧恢复版误用了 AdaptiveAvgPool、人工 localization 特征、通道截断/补零和 Conv2d 输出层，无法匹配真实 checkpoint。

现已恢复四级固定 AvgPool2d、多尺度特征 `[x1,x2,x3,x4,x5]`、`512 * width_factor` 线性输入和 `landmark_number * 2` 输出。源码结构断言与全量模块验证通过；真正加载 PyTorch checkpoint 的数值验证仍留待具备 Torch/CUDA 的环境。

同一 `base_module.pyd` 的基础块也按上游和二进制符号校准：`Conv_Block` 始终使用无 bias 卷积；普通 GhostModule 对奇数通道采用 ceil 分支后裁切；GhostOneBottleneck 不包含额外 shortcut；普通和 GhostOne 两类 stride=2 深度卷积均保持 linear、不插入 ReLU。旧恢复版在这些点会产生额外参数键或改变数值图，现已增加结构断言防止回退。

### S3FD 人脸检测骨干

`s3fd/nets.pyd` 的字符串表包含 `softmax`、`detect`、`priorbox`、`priors` 和 `features_maps`，与 `joonson/syncnet_python` 的 S3FD 实现吻合：网络 `forward()` 内部生成先验框、执行 softmax、解码和 NMS，直接返回 `[batch, class, top_k, 5]` 检测张量。旧恢复版却返回 `(loc, conf)`，把后处理移到外层；它还多建了四个 extra 卷积、在 VGG 尾部多插入一次池化，并以 `strict=False` 静默忽略 checkpoint 键差异。

恢复版现已改回四个 extra 卷积、六级检测特征、网络内 PriorBox/Detect 以及严格权重加载。`box_utils` 同步恢复无 `+1` 的连续坐标面积公式和纯 Torch NMS，避免推理时把 CUDA tensor 往返复制到 CPU。结构与二进制契约断言已加入全量验证；真实 checkpoint 数值输出仍需 Torch/CUDA 环境验证。

### 快手弹幕协议

`kuaishou_v2/KsLive.pyd` 的字段表确认输出事件类型为 `chat`、`like`、`gift`、`stats`，用户字段为 `user_name`、`user_id`、`avatar`；统计事件包含 `status`、`like_count`。旧恢复版使用自创的 `comment/username` 字段，消费端也未读取 `user_name`，会导致真实快手聊天消息丢失昵称；它还完全没有解码 `SC_LIVE_WATCHING_LIST`。

恢复版现按随包 protobuf 描述符补齐 payload type 340、`SCWebLiveWatchingUsers`、观看人数与点赞数，恢复 feed 与观看列表的统计转发，并让快手消费端兼容原 `user_name`。礼物目录不再只保留名称，同时传递 `picUrl` 和 `unitPrice` 为 `gift_pic_url`、`price`。持续测试对消息执行 protobuf 序列化/反序列化，逐字段验证聊天、点赞、礼物、feed 统计及独立观看列表五条路径。

快手客户端的默认转发钩子也已由原生主体校准。`KuaishouLiveClient._forward_message` 的包装体/协程主体为 `0x18001e670`/`0x18001ea90`；主体没有发送、打印或抛出抽象异常，而是立即以 `StopIteration(None)` 完成。旧恢复版自创的 `NotImplementedError` 会让直接使用基础客户端时第一条消息即终止连接。现已恢复为异步空钩子，`ks.py` 中的队列子类仍按原设计覆盖它；测试同时验证基础类返回 `None` 与子类完整转发 chat/gift/like/stats。

`KuaishouLiveClient.__init__` 主体的状态槽进一步确认原版在构造期生成并保存 `page_id` 与 `sec_websocket_key`，创建 `ssl_context`，再用固定 page ID 生成一次 `encoded_data` 进房包；不是每次发送时重新生成 ID/key。`_prepare_enter_room_message` 包装体/主体为 `0x180007170`/`0x1800072e0`，明确读取 `live_stream_id`、`token`、`page_id` 三字段；`_get_headers` 包装体/主体为 `0x1800080c0`/`0x180008230`，明确读取缓存的 `sec_websocket_key`。

`_connect` 的包装体/主体为 `0x180009520`/`0x180009880`。Cython 关键字槽已解码为 `extra_headers=self._get_headers()`、`ssl=self.ssl_context`、`ping_interval=None`、`close_timeout=10`；其中禁用 websockets 内建 ping 是为了只保留快手协议自己的 heartbeat。恢复版此前只传 URL，并在每次连接/发送时重建 key 和 page ID。现已恢复构造期缓存、预编码包复用和四个连接关键字；protobuf 回归逐字段验证 stream、token、page ID、固定 WebSocket key 和实际发送字节，全量验证保持 `128/128 PASS`。

公开入口 `start` 的包装体/协程主体为 `0x180008f90`/`0x1800092d0`。主体只有一次 `await self._connect()`，成功后隐式返回 `None`，连接异常不捕获而是原样传播。旧恢复版在这里自创了重置计数、无限循环、指数退避和只捕获部分连接异常的第二套重连机制；这既与二进制不符，也会和 `_on_error`/`_on_close` 调用的 `_reconnect` 重叠。现已恢复为单次委托，并以回归验证恰好调用一次及异常传播。

消息接收协程也从主体 `0x1800129f0` 恢复。原版 `_on_message` 对 WebSocket 执行持续 `async for`，每帧调用并等待 `_handle_message`；单帧异常打印 `[解析错误] {error}` 后继续接收，不会结束整条连接。`_connect` 则分别创建 `heartbeat_task` 与 `message_task`，再通过 `asyncio.gather` 联合等待。此前恢复版把 `_on_message` 写成同步单次 `recv()`，且连接层完全绕过该公开方法。现已恢复双任务模型与逐帧异常隔离；回归以“坏帧 + 有效 feed”验证错误日志出现后 chat/gift/like/stats 仍全部转发，完整验证继续为 `128/128 PASS`。

断线生命周期随后由 `_on_error` 主体 `0x18001c1d0`、`_on_close` 主体 `0x18001c960` 和 `_reconnect` 主体 `0x18001d7d0` 完成闭环。前两者都是协程：错误回调打印 `[错误] {error}`，关闭回调打印 `[已关闭] WebSocket连接已关闭`，随后均执行 `await self._reconnect()`；旧恢复版只是保存错误或直接返回，完全不会恢复连接。

原生 `_reconnect` 在次数达到 10 时打印 `[重连] 达到最大重连尝试次数 (10)，放弃连接` 并隐式返回 `None`。未达上限时先计算指数退避延迟，再把次数加一，打印 `[重连] 第N次尝试，等待 X.XX 秒...`，依次等待 `asyncio.sleep(delay)` 与 `_connect()`；连接异常自然向上传播，成功同样隐式返回 `None`。恢复版已删除自创的 `True/False` 返回值并补回精确日志。回归验证第 3 次、1.25 秒的打印与 sleep→connect 顺序，以及第 10 次上限不再连接；全量验证保持 `128/128 PASS`。

连接建立入口 `_on_open` 的包装体/主体为 `0x18000ccf0`/`0x18000d120`，进房发送 `_send_initial_data` 的包装体/主体为 `0x18000e9e0`/`0x18000ee00`。原构造器保存的 `encoded_data` 不是 bytes，而是 `_prepare_enter_room_message()` 生成序列化包后的十六进制字符串；发送时严格执行 `bytes.fromhex(self.encoded_data)`，随后打印 `[数据][{room_id}] 初始数据已发送`。此前恢复版直接保存和发送 bytes，公开发送方法也只是返回 awaitable 而非协程。

原生 `_on_open` 先打印 `[已连接][{room_id}] WebSocket连接已建立`，等待初始数据发送，再分别创建心跳和消息任务并 `gather`；任务异常由入口捕获，输出 `[任务错误][{room_id}] 意外错误: ...`。`_connect` 已恢复为只负责建立带正确关键字的 WebSocket context，再委托 `_on_open`，不再复制第二套发送和任务逻辑。回归验证十六进制包可还原为精确 CS_ENTER_ROOM 字节、实际发送值、两条建立日志以及 heartbeat/message 两协程均被调度；全量验证继续为 `128/128 PASS`。

心跳协程 `_send_heartbeat` 的包装体/主体为 `0x18000f450`/`0x18000f880`。原版每轮用 `int(time.time() * 1000)` 生成毫秒时间戳并构造 `CS_HEARTBEAT` 帧；发送成功打印 `[心跳][{room_id}] 心跳包已发送，时间: {timestamp}`，然后等待固定模块常量 `HEARTBEAT_INTERVAL=20`。它不使用进入房间 ACK 写入的 `heartbeat_interval_ms` 作为 sleep 值。`websockets.exceptions.ConnectionClosed` 输出 `[心跳][{room_id}] 连接问题: ...` 后退出，其他异常输出 `[心跳][{room_id}] 意外错误: ...` 后退出。恢复版已由 `time_ns()` 与动态 ACK 间隔改回上述原生协议；回归将时间固定为 123.456 秒，解析实际发送字节并确认时间戳 123456、payload type、20 秒等待及精确日志，全量验证保持 `128/128 PASS`。

礼物目录协程 `fetch_gift_info_global` 的主体为 `0x1800011f0`，`get_gift_info` 的包装体/主体为 `0x180008860`/`0x180008a90`。原版通过 `aiohttp.ClientSession()` 和 `session.get("https://livev.m.chenzhongtech.com/rest/wd/live/gift/all")` 两层异步上下文请求目录：HTTP 非 200 打印 `[礼物] 全局获取失败: HTTP N`；成功时等待 `response.json()`，遍历 `result["data"]`，把每项的 `name`、`unitPrice`、`type` 以及首个 `picUrl[0]["url"]` 写入模块级 `gift_info_global[id]`，最后打印 `[礼物] 全局获取到 N 个礼物信息`。格式失败和异常只打印诊断，协程所有路径均隐式返回 `None`。

旧恢复版使用 `urllib.request` 在线程中访问、假定 `data["gifts"]` 嵌套结构、返回新字典，再把它保存在每个客户端的 `gift_names`，四处均与二进制调用约定不符。现已恢复共享目录和原生异步请求；`get_gift_info` 命中时返回共享项，未命中时精确回退为 `{"name": "未知礼物(ID)", "price": 0, "type": 0, "pic_url": ""}`。无网络回归用假的 aiohttp 会话验证 URL、字段映射、图片提取、日志、`None` 返回值及未知礼物回退，并同步修正 CLI、队列 worker 与 WebSocket server 三个调用方。

房间参数入口 `get_live_info_from_url` 的包装体/协程主体为 `0x18001eb10`/`0x18001ee60`。原版在异步函数中同步构造 `Tool(live_url)`，依次调用 `getLiveRoomId()` 和 `processLiveId(live_id)`；它不使用 `asyncio.to_thread`，也不自行用 `urlsplit` 提取 ID。只有 `room_info["data"].get("result") == 1` 时才继续：`liveStreamId` 为空则回退到 `live_id`，token 取 `token`，WebSocket 地址优先取非空 `websocketUrls[0]`，否则取 `webSocketUrl`。三项均有效才返回 `{"live_stream_id", "token", "ws_url"}`，否则返回 `None`；所有异常打印 `获取直播间信息出错: ...` 后返回 `None`。恢复版及无网络 Tool 双替身测试已按这条真实调用链校准。

继续下钻 `hq.cp310-win_amd64.pyd` 后，新建 Ghidra 工程 `rea-output/ghidra-kuaishou-hq/hq`。`Tool.getLiveRoomId` 的包装体/主体为 `0x18000bd50`/`0x18000bec0`。方法名具有误导性：它不是本地 URL 解析器。原版先执行 `self.liveUrl.strip("/").split("/")[-1]` 得到候选 principalId，再以 `requests.get("https://live.kuaishou.com/live_api/liveroom/livedetail", params={"principalId": ...}, headers=...)` 请求房间详情，等待 `response.json()` 后读取 `resp_json["data"]["liveStream"]`，优先返回 `liveStreamId`，为空则返回 `id`。

原请求头的 14 个键值也已由状态槽恢复，包括 `Accept: application/json, text/plain, */*`、`Referer: self.liveUrl`、Cookie、Chrome 137 User-Agent、三项 `Sec-Fetch-*` 及三项 `sec-ch-ua*`。旧恢复版只截取链接尾段，导致后续 `processLiveId` 收到用户短号而非真实直播流 ID。现已改回 livedetail 数据流，并用假的 `requests.get` 验证 URL、`principalId`、Cookie、浏览器头与最终流 ID，全程不访问网络。

`Tool.__init__` 主体为 `0x18000a3e0`，`generate_cookie` 包装体/主体为 `0x18000b8e0`/`0x18000ba40`。构造器保存原生字段 `liveUrl`、`cookie`，创建 `ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)` 到 `det`，设置 `verification_token=None`；cookie 为空时调用 `generate_cookie()`。随后以 `dirname(abspath(__file__))` 为 `base_dir`，形成 `js/node.exe`、`js/sign_url.js`、`js/encrypt.js` 三条路径。恢复版此前既没有 OCR/token/脚本字段，又把原生 `liveUrl` 改成了 `live_url`，已全部校准；未安装可选 ddddocr 时恢复版保留 `det=None`，以维持源码在当前 Mac 环境可导入。

原生 `generate_cookie()` 只返回 `"did=" + str(generate_did())`，不会拼接 didv、kpf、webDid 或指纹 token。`generate_did` 主体为 `0x1800010f0`，其生成器主体为 `0x1800013c0`：严格执行 32 次 `random.choice("0123456789abcdef")`，再加前缀 `web_`。旧恢复版以 UUID 构造 DID 并生成一整套臆测 Cookie，现已改回原生算法；确定性测试覆盖 OCR 参数、自动 Cookie、三条资源路径及 32 位十六进制选择过程。

`Tool.processLiveId` 的包装体/主体为 `0x18000d390`/`0x18000d5e0`。输入流 ID 为假值时，原版打印“未获取到直播间ID，无法生成签名URL。”并返回 `None`。有效输入先构造 `{"liveStreamId": live_id}`，再执行 `subprocess.check_output([self.node_exe, self.sign_url_js, "/live_api/liveroom/websocketinfo", "/rest/k/live/websocket/info", json.dumps(params)], encoding="utf-8").strip()`；签名结果拼成 `https://live.kuaishou.com{signed_url}&liveStreamId={live_id}`。这证明该方法不会再次调用 livedetail，也不会把 `live_id` 误当用户短号重新解析。

websocket-info 请求头已按常量槽完整恢复：Chrome 138 User-Agent、`kww` 加密常量、Cookie、Referer、Accept/语言/压缩、三项 `sec-ch-ua*`、三项 `Sec-Fetch-*` 和 Host。若实例已有 `verification_token`，首请求即加入 `identity-verification-token` 与类型 `1`。响应执行 `json_data.get("data", {})`；当 `result == 400002` 时把 data 交给 `handle_captcha`，其返回真且生成了 token 后，用同一 URL 和更新后的验证头重试一次。最终始终返回完整 `json_data`，不做旧恢复版自创的字段扁平化或合并。无网络回归逐项验证 Node 参数、签名 URL、关键请求头、400002 分支、token 重试、原始 JSON 返回和空 ID 提示；全量验证保持 `128/128 PASS`。

`Tool.handle_captcha` 的包装体/主体为 `0x18000f1f0`/`0x18000f440`，主体反编译共 4070 行。旧恢复版只从传入字典猜测 target/background 并执行一次本地模板匹配，遗漏了实际验证码协议。恢复版现按原主体恢复三次尝试：从 `resp_data["data"]["captchaUrl"]` 用 `captchaSession=([^&]+)` 提取会话，调用 `/rest/zt/captcha/sliding/config`，读取 `captchaSn`、`bgPicUrl`、`cutPicUrl`、`disY`，再携带 captchaSn 下载两张图片并调用 `self.det.slide_match(cut, background)`。

主体对 OCR 的 `target[0]` 与 `disY` 均乘精确常量 `0.469` 后取整，并将横向距离再乘 `3.42` 交给轨迹生成器；明文验证参数由十项组成：captchaSn、固定展示尺寸 `316×184`/`56×56`、relativeX、relativeY、trajectory、gpuInfo 和序列化 browser fingerprint。字典逐项执行 quote，并额外把 `/` 替换为 `%2F`；之后严格调用 `subprocess.check_output([self.node_exe, self.encrypt_js, data_crack], encoding="utf-8").strip()`。密文以 `{"verifyParam": ...}` JSON 提交到 `/rest/zt/captcha/sliding/kSecretApiVerify`。`result == 1` 时打印成功诊断、把可选 `captchaToken` 写入 `self.verification_token` 并返回 `True`；失败会打印尝试次数、等待后重试，第三次失败返回 `False`。无网络测试覆盖配置、图片、OCR、缩放、十项明文、JS 参数、验证请求和 token 写回，全量验证保持 `128/128 PASS`。

`Generate_trajectory.get_slide_track` 已按 `0x180007d30` 完成常量级还原：输入必须是非负整数；初始坐标分别取 `[10,30]`，总段数取 `[20,30]`；进度 `<0.3` 使用三次曲线、`>0.7` 使用二次减速、中段系数为 `1`，每段带 `0.9–1.1` 随机扰动。纵向抖动范围为 `[-3,3]`，时间增量为 `[10,50]` 且按段累计，输出严格采用 `x|y|time` 逗号串联，并在未到目标时补齐终点。离线测试锁定了随机调用顺序、累计时间戳、异常文本及静态方法签名；当前全量门禁为 `128/128 PASS`。

`generate_gpu_info` 已按 `0x180004800` 替换早期平台探测占位代码。原函数并不读取本机 GPU，而是随机生成 Windows ANGLE/WebGL 指纹并返回 `json.dumps` 字符串。厂商池为 Intel/NVIDIA/AMD；Intel 型号池为 HD/UHD/Iris 并附加 `[500,999]` 编号，NVIDIA 使用 GTX/RTX 与 1060、1650、1660、2060、3060、3070、4060，AMD 使用 Radeon/Radeon RX 与 580、590、5500、5700、6600、6700。Direct3D 版本从 11/12 中选取，驱动号由 `[20,31].[0,21].[10000,15000].[1000,9000]` 组成。返回字段严格为 `glRenderer`、`glVendor`、`unmaskRenderer`、`unmaskVendor`；测试已锁定 Intel 分支的全部随机池、调用顺序和最终 ANGLE 字符串，全量门禁仍为 `128/128 PASS`。

`generate_fingerprint` 的 `0x1800017b0` 主体也已完成还原。原实现不是浏览器指纹 JSON 的 SHA-256；实际明文严格为 `str(random.random()) + str(time.time()) + str(random.randint(10000, 99999))`，随后执行 `hashlib.md5(value.encode()).hexdigest()`。恢复代码与确定性测试均已按此调用顺序更新。

`generate_browser_fingerprint` 已按 `0x180002440` 完成 19 字段还原。Chrome 主版本在 `[95,138]` 内随机生成；宽度池为 1920/1680/1440/2560，高度池为 1080/1050/900/1440；时区池为 UTC+8、UTC+7、UTC+9、UTC-5、UTC-4，语言池为 zh-CN、en-US、zh-TW、ja-JP。CPU 核数字符串来自 `[4,16]`，平台固定为 `Win64`，pixelDepth 与 colorDepth 分别独立选择 24/32。Canvas 与 WebGL 的普通值和 FingerPrint 值各调用一次 `generate_fingerprint`。兼容字段 `key1/key2/key3/key5/key7/key8` 分别复用 DID、毫秒时间戳、UA、语言、宽度、高度。确定性测试已锁定全部随机调用顺序、字段类型、UA 拼接、四次 fingerprint 调用与字段复用关系；全量门禁继续为 `128/128 PASS`。

`Tool.slide_match` 已从包装器 `0x180015630` 和主体 `0x180015940` 精确恢复。它并不自行通过 OpenCV 解码或模板匹配，而是严格转发为 `self.det.slide_match(target_bytes, background_bytes, simple_target=True)` 并原样返回 ddddocr 结果。早期近似实现已删除，测试锁定两个位置参数及 `simple_target=True` 关键字。

### 直播话术时间变量

`text_processing.pyd` 包含 `{time}`、`{min_left}`、`{next_h}` 三种变量，但旧恢复版只实现了 `{time}`。Ghidra 对 `process_special_variables` 主体的反编译确认：`{time}` 替换为中文小时加“点”，仅在分钟非零时追加中文分钟和“分”；`{min_left}` 使用 `(60 - minute) % 60` 并只输出中文数字；`{next_h}` 使用 `(hour + 1) % 24` 并追加“点”。

三条路径现已按该运算和格式恢复，持续测试覆盖 13:05 与 23:00 两个边界，验证分钟省略、下一日零点和整点剩余分钟归零。Ghidra 项目、函数清单和七个主要函数反编译结果保存在 `rea-output/ghidra-text-processing`、`text-processing-functions.tsv` 与 `text-processing-decompiled/`，供后续继续校准同模块其他行为。

同一模块的 `strip_prohibited_words` 反编译体还显示：函数先创建固定长度为 5 的列表，再与传入的违禁词列表相加；对应 Unicode 常量为“哎呀、嘿、哎哟、哦、喔”。旧恢复版遗漏了这组内置口语填充词。现已恢复内置词与自定义词的合并删除，并覆盖空配置、空词项及完整五词清理测试。

`parse_qa_info` 的反编译数据流确认其读取问答项后只访问 `question` 与 `answer`，分别执行 `(value or "").strip().split()`，再把每个关键词映射到同一个候选回答列表对象；重复关键词由后项覆盖。旧恢复版把整句问题和整段答案各视为单项，后续又保留了二进制不存在的 `keywords/answers` 兼容分支并为每个关键词复制答案列表，现已删除。测试覆盖双关键词共享列表、双候选、随机命中、重复键覆盖、兼容键拒绝和非字典项的原生 `AttributeError`。

同模块的过滤函数也完成主体级校准。`contains_blocked` 与 `is_user_blocked` 都先要求候选项 truthy，再执行候选子串包含判断；后者不是旧恢复版的 `nickname in blocked_users` 集合精确成员判断。因此黑名单项“用户12”会阻止昵称“黑名单用户123”。`match_keywords` 则不额外过滤空关键词：空字符串键可命中任意内容，候选列表为空时返回 `None`，非空时调用 `random.choice`。上述边界均已加入回归，全量验证保持 `128/128 PASS`。

`parse_qa_info_from_text` 主体 `0x1800079f0` 使用 `re.split(r"\n\n", qa_info)` 分块，再以起始锚定语义的 `re.match(r"问：(.*?)\n答：(.*)", block, re.DOTALL)` 解析；旧恢复版在调用前擅自统一 CRLF、全局 `strip()`，并用可跳过任意前缀的 `re.search`。现已恢复原生调用，验证标准双块、前缀拒绝和 CRLF 捕获后 `strip()` 的结果。`_num_to_chinese` 的 0–9、10–99 与范围外回退，`process_script_options` 的花括号竖线随机选项，以及三种时间变量也均加入确定性断言。结合九个公开/私有主体、原始正则和五个固定口语过滤词，`tools/text_processing.pyd` 现可在 Mac 静态证据范围内标记为完成；全量门禁继续为 `128/128 PASS`。

### FunASR 句子合并

`funasr_sentences.pyd` 的模块初始化体明确创建整数 `0x32` 与 `0x50`，分别对应 `TARGET_SENTENCE_CHARS=50` 和 `HARD_MAX_SENTENCE_CHARS=80`；Unicode 常量确认硬终止标点为 `。！？!?`，软标点为 `，,；;、`。旧恢复版使用无二进制依据的 28/48，并把分号误列为硬终止、冒号误列为软标点，导致字幕和口型时间段过度碎裂。

恢复版现按约 50 字目标、80 字硬上限累加短句，达到目标后可在硬标点或软标点处 flush。持续测试验证分号不触发单段拆分、55 字软标点段落在下一片到来前结束，以及时间戳边界保持。Ghidra 项目、函数清单和主要反编译体已保存至 `rea-output/ghidra-funasr-sentences` 与 `funasr-sentences-decompiled/`。

该模块的 `_normalize_text` 也从 Ghidra 调用序列确认有三层正则：先把全部空白折叠为单空格并去除首尾空白，再删除两个汉字之间的空格，最后删除标点前空格。旧恢复版直接删除全部空白，会把英文 `hello world` 合并成 `helloworld`。现已恢复中英文分流规则，测试覆盖换行折叠、英文词间空格、汉字间空格和中英文标点前空格。

`recognize_media_sentences` 的二进制后缀常量确认 `.wav/.mp3/.flac/.m4a/.ogg` 直接进入 FunASR，其他音视频才提取临时 WAV。旧恢复版无条件转码，而且 FFmpeg 提取发生在模型清理的 `try/finally` 之外，提取失败会泄漏刚加载的模型。现已恢复音频直通和非音频临时 WAV 分支，并把整个媒介处理包入模型清理范围。测试覆盖 MP3 零转码、MP4 提取、临时 WAV 输入以及提取异常后清理。

### Whisper SRT 临时音频

`get_srt.pyd` 的 `gettempdir`、`temp_audio_path`、`remove`、`-map`、`0:a:0` 和 `-acodec pcm_s16le` 证明字幕识别音频应写入系统临时目录、显式选择第一条音轨，并在结束后删除。旧恢复版把 `_subtitle_asr.wav` 写在源视频旁且永不清理。现已恢复临时目录和音轨映射，并将提取、模型、识别和输出全部纳入清理范围；成功与识别异常测试均确认临时 WAV 删除且模型释放。

同一模块的三层规范化正则还补回“ASCII 标点后到汉字前”的空格删除，与原有汉字间、汉字到标点前规则共同覆盖中英混排字幕。

### 字符时间戳字幕分块

Ghidra 定位到 `_build_subtitles_from_timestamps`（`18000ad10`）及其 `flush` 闭包（`180009bb0`）。原逻辑把顶层 `timestamp(s)` 时间对依次映射到规范化文本中的非空白、非标点字符；标点不消耗时间对。累计字符达到 `MAX_SUBTITLE_CHARS`、跨度达到 `MAX_SUBTITLE_MS`，或句末标点且已达到 `MIN_SUBTITLE_MS` 时输出字幕块，最后统一校正时间轴。恢复版已替换此前错误的“每个 Whisper word 输出一条字幕”实现。

模块初始化函数进一步确认这三个阈值分别为 24 字、4500 ms 和 500 ms（另有 1000 ms 时间轴重叠常量），替换了早期恢复版未经二进制证实的 28 字与 8000 ms。

`_normalize_subtitle_timeline` 的反编译比较链及 PE `.rdata` 浮点值确认重叠阈值为字幕自身时长的 0.5：重叠达到一半的字幕直接丢弃，不足一半才将开始时间裁到上一条结束。恢复版已补回轻微重叠保留、严重重叠过滤，并确认三路构建顺序为 `sentence_info → timestamps → plain_text`。

`_build_subtitles_from_sentence_info` 还确认直接读取顶层 `sentence_info`，将各项 `start/end` 以 `int(float(...))` 解释为毫秒，规范化 `text` 后逐项 clamp，非法类型或数值跳过。恢复版已移除此前错误的 Whisper `segments` 间接转换依赖，并覆盖缺省结束时间与坏数据过滤。

`_build_subtitles_from_plain_text` 则逐字符累计，遇 `PUNCTUATION` 或 24 字上限即成块；时长按块字符数占全部块字符数的比例，从 `cursor_ms` 连续分配，最后一块强制结束于媒体总时长。恢复版已替换此前按字幕块数量简单等分的近似实现。

### 数字人智能点品跳转

Ghidra 已完整定位 `_jump_to_digital_dianpin` 主体 `0x18003d6f0`。普通话术模式先确认 `script_list` 非空，并用 `_find_product_script_cursor(product_index)` 找到真实话术游标；成功后更新 `broadcast_cursor`、`current_product_index` 和 `_resolve_product_info()` 的结果。多商品模式则用 `_find_product_group_index()` 找组，从组内 `config.imageModelId/voiceModelId` 切换数字人与音色，重置 `product_item_cursor`，并把新模型、音色及 `voice_infer_version` 合入清队列任务载荷。

两条成功路径都会清空 `_pending_script_tts`，发出 `clear_normal_queues`（载荷含 `clear_queues=True` 与目标 `product_index`），把点品转场句加入 `normal` 队列、指定 `target_face_index=0` 和商品编号，最后调用 `_sync_product_ui(product_index)`。二进制中的三条失败诊断也已解码并恢复：“数字人点品失败：话术列表为空”“数字人点品未找到话术起点”“数字人点品未找到多品分组”。恢复版已移除此前错误的 `switch_product + danmu TTS` 近似实现；普通、多商品、空列表、稀疏编号和缺失分组测试均通过，全量验证保持 `128/128 PASS`。

### 互动 LLM 提交与回退

`_submit_interaction_llm` 主体 `0x180040940` 与其 worker `0x18003fc70` 已恢复。原程序先快照 `language`，worker 调用传入的 `llm_call()`；结果为空时才调用 `_fallback_reply_text(language, kind, nickname, content)`，随后把原始回复交给 `_speak_interaction_reply()`。异常日志为 `[local.live] {kind} LLM 异常: {exc}`。存在 `_interaction_llm_executor` 时提交后台 worker；线程池为 `None` 时执行完全相同的同步路径。

旧恢复版额外加入了二进制中不存在的 `(kind, nickname, content)` 去重集合，并错误地用淘宝场控的 `@昵称` 规范化普通语音互动回复；同时没有同步回退路径。上述差异现已删除，测试覆盖直接回复、空回复中文回退、异常吞吐以及即时线程池提交，全量验证继续保持 `128/128 PASS`。

FaceHand 的淘宝场控链也已从独立扩展 `face_hand_live_manager.cp310-win_amd64.pyd` 精确恢复。外层 `_submit_ai_control_reply` 主体为 `0x180036bb0`，worker 为 `0x180035ad0`；外层快照 `_interaction_llm_executor`、`qa_info` 与 `special_instructions`，执行器为空时同步运行，否则调用 `submit(worker)`。worker 调用公开 `generate_text_reply(nickname, content, product_info, qa_info, special)`；空结果使用原始常量 `@{nickname} 收到，稍等主播回复哦`，随后调用 `_normalize_control_text_reply`。模块状态槽进一步解码为 `0xcd0 → _interaction_llm_executor`、`0xcf0 → is_broadcasting`、`0xfc8 → _normalize_control_text_reply`、`0x1328 → _send_taobao_control_reply`：因此生成完成后只有仍在直播时才打印最多 80 字的“`[face_hand.live] 场控回复：`”并直发淘宝评论。异常前缀的原始 UTF-8 数据为“`[face_hand.live] AI场控 LLM 异常: `”。此前恢复版错误调用私有 `_generate_text_reply`、把回复送入普通互动 TTS，且遗漏同步执行路径；现已修正，并加入五参数传递、空回复兜底、异常吞吐、直播停止后不发送及即时执行器回归。反编译证据保存于 `rea-output/face-hand-manager-decompiled/submit_ai_control_outer.c` 和 `submit_ai_control_worker.c`，全量验证仍为 `128/128 PASS`。

FaceHand 音频合成链的低保真分支也已继续校正。`_build_minimax_runtime_config` 包装体/主体为 `0x18004e1d0/0x18004e490`：原版复制 `self.minimax_voice_config`，再从 `voice_general_config["minimax"]` 取 `minimax_voice_id`、转字符串并去空白后覆盖。`_build_cosyvoice_runtime_config` 为 `0x18004eaf0/0x18004edb0`，会先调用 `tools.online_voice_generate.generate_voice.resolve_aliyun_voice_runtime(self.cosyvoice_voice_config)` 解析地域端点，再覆盖 `cosyvoice_voice_id`。`_handle_tts_speak` 包装体/主体为 `0x180047400/0x180048360`，已确认 payload 可覆盖 queue、voice_id、voice_infer_version、voice_speed、language 和 use_audio_cache；`minimax`/`cosyvoice` 走 90 秒云端超时链，其余版本走 120 秒本地合成链。恢复版现已实现两个云 provider、按 `(voice_id, voice_infer_version)` 缓存多个本地合成器，并在停播时统一释放；配置隔离、国际阿里云端点、音色覆盖及云合成入队均已加入回归。

`_handle_tts_speak` 的合成后半段也已恢复：音频返回后重新检查 `is_broadcasting` 和 `host_streamer`；对 `normal` 队列比较任务 `epoch` 与 `_normal_audio_epoch`，切品/清队列期间完成的旧合成结果直接丢弃。有效普通音频在入队后以 `str(audio_path) -> int(product_index)` 写入 `_audio_product_map`，超过 `AUDIO_PRODUCT_MAP_LIMIT` 时按插入顺序删除最旧映射。`_clear_normal_queues` 现会先递增 epoch，`_enqueue_tts` 将当前 epoch 快照进 payload。`_audio_worker_loop` 包装体/主体为 `0x180042990/0x180042b00`，原生异常前缀已从 UTF-8 数据确认为“`[face_hand.live] 音频任务异常: `”；恢复版现会捕获单个任务异常、打印 traceback、在 `finally` 中减少 pending 计数并继续处理后续任务。回归已证明失败任务不会杀死 worker，且过期音频不会入队或污染商品映射。

FaceHand 商品图链的三个原生主体已导出：`_build_product_image_items` 为 `0x180012960`、`_prepare_product_images` 为 `0x180013e40`、`_sync_product_image` 为 `0x18001bbd0`。构建函数只接受字典项，按 `itemPic/item_pic`、`itemName/item_name`、`itemId/item_id` 的顺序取值并转字符串、`strip()`，图片地址以 `//` 开头时补 `https:`，输出固定三键 `itemPic/itemName/itemId`。预加载函数将结果保存到原生字段 `product_image_items`，规范化 `product_image_jitter_level`，按配置加载抠图模型，再将 `enable_cutout/enable_jitter/jitter_level` 传入 popup 预加载。切品同步现从 `product_image_items` 而非丢失图片字段的话术分组取值，以 `_synced_image_goods_id` 避免重复显示；停播时关闭全局 popup、卸载抠图模型并清空同步状态。回归覆盖双命名风格、协议相对 URL、非字典过滤、商品 ID 转换及重复切品去重。

播放中的商品追踪入口 `_sync_playing_product` 包装体/主体为 `0x18001cdd0/0x18001cf40`。原逻辑只在 `phase == "hand"` 且 `enable_taobao_product_sync`、`enable_product_image_sync` 至少一个开启时运行；从 `host_streamer.get_current_playing_audio_path()` 取得当前 TTS 路径，空路径和以 `<` 开头的内部占位路径直接忽略，再以 `self._audio_product_map.get(str(path))` 找到商品索引并转为整数传给 `_sync_product_ui`。播放器查询异常由原函数吞掉。恢复版已删除此前按 `_group_index` 猜测切品的实现，接通“合成写映射—播放器报告当前路径—商品 UI 同步”的真实闭环；回归覆盖阶段门控、有效映射、占位路径和未映射路径，完整验证保持 `128/128 PASS`。

下游 `_sync_product_ui` 的包装体/主体确认为 `0x18001a860/0x18001ab20`。商品索引先执行 `max(int(product_index), 0)`；淘宝同步开启且索引不同于 `_synced_goods_id` 时，函数调用模块级 `get_taobao_controller()`。控制器已连接则执行 `set_active_goods(index)`，未连接仍把该索引记为已同步以避免每个 tick 重试；异常只打印原始前缀“`[face_hand.live] 中控弹窗失败: `”。三条 PE 文本已直接解码为“中控未连接，跳过弹窗商品”“中控弹窗商品”和上述失败前缀。无论淘宝分支是否启用或成功，最后都会调用 `_sync_product_image(index)`，因此淘宝中控和本地商品图是并列输出。恢复版现已补回 `_synced_goods_id`、去重、非负钳制、精确日志和双路同步，停播时同时清空淘宝与图片同步状态；回归覆盖负索引、重复索引和商品切换，全量验证继续为 `128/128 PASS`。

过品清理入口 `_pause_product_ui` 包装体/主体为 `0x180019710/0x180019880`。淘宝同步开启时通过模块级 `get_taobao_controller()` 调用 `clear_active_goods()`，无论成功或异常均清空 `_synced_goods_id`；商品图同步开启时同样通过模块级 `get_product_image_popup()` 调用 `show_greenscreen()`，随后清空 `_synced_image_goods_id`。两条异常前缀已从 PE 数据解码为“`[face_hand.live] 过品停中控弹窗失败: `”和“`[face_hand.live] 过品绿幕失败: `”。恢复版此前只对可能存在的缓存 popup 显示绿幕，遗漏淘宝清理、全局 popup 获取与状态复位，现已完整补齐并通过双路回归。

FaceHand 调度 `_tick` 包装体/主体为 `0x18001f160/0x18001f2d0`。原函数使用 `_tick_lock.acquire(blocking=False)` 防止重入，并确保所有出口释放锁；首次 tick 在 `_started_cycle == false` 时只置位并调用 `_enter_face_phase(0)`，后续 tick 才依次执行 `_drain_manual_and_simulated()`、`_tick_interactions()`、`_tick_broadcast()`。`_sync_playing_product()` 位于 `_session_loop` 而非 tick 本体。恢复版现已增加 `_tick_lock`、`_started_cycle` 和独立 `_session_stop` 事件，恢复首次启动、非阻塞重入保护及真实调用顺序；启动与停止会同步管理这些状态。首次/后续 tick 和锁占用回归均通过，全量验证仍为 `128/128 PASS`。

`_session_loop` 的主体 `0x18001dae0` 进一步确认每轮先要求 session 未停止且仍在直播；当 `phase == "face"`、streamer 存在并且 `consume_face_clip_done()` 返回真时调用 `_on_face_done()`，随后依次调用 `_tick()` 与 `_sync_playing_product()`，最后以 `_session_stop.wait(TICK_INTERVAL_SECONDS)` 进行可中断等待。单轮异常不会终止 session，原始日志前缀已解码为“`[face_hand.live] tick 异常: `”。恢复版已从仅按固定 sleep 调用 tick 的近似循环，改为独立停止事件、直播状态门控、face 完成消费、播放商品同步和精确异常诊断。

下游 `_send_taobao_control_reply` 主体 `0x180034770` 随后完成闭环。原版先对 `reply or ""` 执行 `strip()`，再调用模块级 `contains_blocked(text, self.reply_blocked_keywords)`；空文本或命中禁词均返回 false。通过后不是使用实例缓存的 `_taobao_controller`，而是每次调用模块级 `get_taobao_controller()`，检查 `controller.connected()`，连接存在时执行 `send_comment(text)` 并返回其布尔值。三条原始日志分别为“`[face_hand.live] AI场控发送跳过：中控台未连接`”、“`[face_hand.live] AI场控已发送: `”和“`[face_hand.live] AI场控发送失败: `”，成功日志截取回复前 50 字；异常被捕获并返回 false。恢复版已补齐禁词过滤、控制器获取、连接判断、精确日志与异常语义，反编译证据保存于 `rea-output/face-hand-manager-decompiled/send_taobao_control_reply.c`，断连、成功、禁词与异常四条回归均通过。

FaceHand 手动口播与模拟提问队列也由三个原生主体完成校正：`request_manual_speak` 为 `0x180029d20`，`request_simulated_question` 为 `0x18002a800`，统一消费函数 `_drain_manual_and_simulated` 为 `0x18002b190`。两个提交入口都先执行 `(value or "").strip()`，空值或 `is_broadcasting == false` 时返回 false；成功路径持有实例 `_lock`，分别向列表 `_manual_speaks` 与 `_simulated_questions` 执行 `append()` 并返回 true。消费函数在同一把锁内复制两个列表并原地 `clear()`，解锁后处理完整快照；所有手动文本均调用 `_enqueue_tts(text, queue="danmu")`，模拟提问则逐项调用 `submit_danmu({"msg_type": "弹幕", "nickname": "模拟用户", "content": content})`。原始常量“弹幕”和“模拟用户”已从 PE UTF-8 数据槽 `+0x440`、`+0x498` 解码。此前恢复版错误使用两个 `Queue`、每 tick 只消费一个项目、手动内容进入 `manual` 音频队列，且模拟昵称/字段分别写成“模拟观众”与 `type`；现已恢复为原生列表快照协议，多项顺序、清空及精确载荷均有回归，完整验证保持 `128/128 PASS`。证据保存在 `request_manual_speak.c`、`request_simulated_question.c` 与 `drain_manual_and_simulated.c`。

传给互动 LLM 的商品上下文入口 `_active_product_info` 主体 `0x180031f20` 也已恢复。原版依次检查 `current_product_index` 与 `_pending_group` 是否处于 `product_script_groups` 的合法下标范围；对命中的组只读取 `group.get("product_info")`，truthy 时执行 `str(...).strip()`，非空才返回。两个候选均无有效资料时返回实例级 `self.product_info`。旧恢复版使用自创 `_group_index` 从商品名和全部脚本文本动态拼接，既忽略待切换商品，也可能把播报脚本错误泄入问答上下文。现已补齐原生状态字段及当前商品、待切商品、全局回退三层回归；证据保存于 `face-hand-manager-decompiled/active_product_info.c`，全量验证继续为 `128/128 PASS`。

商品分组入口 `_build_product_groups` 主体 `0x180010d80` 已完成结构级恢复。原版遍历 `products or []`，跳过非字典项；将 `product.get("scripts") or ""` 转为字符串并 `strip()`，非空后调用模块级 `tools.slice_content.slice_content`，把话术切成 host、assistant、pause 项。`product_index` 优先取商品显式字段并执行 `int()`，任何转换异常均回退到 `enumerate` 下标；每个切片复制为新字典并写入该索引。只有切片列表非空时才生成组，固定结构为 `{"product_index": index, "product_info": str(product.get("content") or product.get("itemName") or ""), "items": items}`。旧恢复版把 `scripts` 当作字符串/字典列表原样保留，输出字段仍叫 `scripts`，没有执行原生切片，也未给每个 item 标注商品索引。现已同步修改人脸完成回调和广播消费端使用 `items`，回归覆盖显式/非法索引、三种切片类型、商品资料优先级、空话术与坏项；全量验证仍为 `128/128 PASS`，反编译证据保存于 `face-hand-manager-decompiled/build_product_groups.c`。

FaceHand 的 face/hand 商品播报状态机已由 `_enter_face_phase`（`0x180020270`）、`_on_face_done`（`0x1800224d0`）和 `_tick_broadcast`（`0x180024190`）三个主体联合恢复。进入 face 阶段会清理 normal 队列、播放 face 片段，并设置 `phase="face"`、`_pending_group=目标组`、`current_product_index=-1`、`product_item_cursor=0`；face 完成回调仅在当前阶段确为 face 且商品组存在时提交 `_pending_group % len(groups)`，切换 `phase="hand"`、设置当前商品并清零 item 游标，再播放 hand 片段。hand 阶段的广播 tick 每次最多发射 `TTS_EMIT_BURST_MAX` 个 item，持续读取 `normal`/`pending_normal` 水位，分别受 `BROADCAST_QUEUE_TARGET` 与 `TTS_PIPELINE_DEPTH` 限制；常量初始化体 `0x180062ea0` 确认 burst 与 pipeline 共用缓存整数槽 `+0x17c0 = 4`，FaceHand 自己的广播水位槽 `+0x1810 = 800`（此前误用了 `live_manager.pyd` 的 1000），切品阈值直接使用缓存零槽 `+0x17a8`。item 耗尽且两级队列降到阈值后，计算下一商品、输出原始“话术耗尽触发过品”诊断并重新进入 face 阶段。旧恢复版提前把商品标为当前、另起线程一次性排队，且每个 tick 永远重复首个 item；现已恢复为游标推进、四项 burst、两级背压和循环切品，三种 item 的完整发射及 0→1 切品回归通过。证据保存于 `enter_face_phase.c`、`on_face_done.c` 与 `tick_broadcast.c`，全量验证保持 `128/128 PASS`。

单项发射入口 `_emit_script_item` 主体 `0x180026430` 随后恢复。该函数严格读取 `item["type"]`：仅 `host` 进入播报路径，其他类型（包括 `assistant` 与 `pause`）直接返回 None。host 内容读取 `item.get("content")`，依次调用模块级 `process_special_variables`、`process_script_options` 和字符串 `strip()`；结果非空时调用 `_enqueue_tts(text, queue="normal", product_index=item.get("product_index"))`。这一数据流同时证明 `tools.slice_content` 输出的 host/assistant 文本键是 `content`，旧恢复版自创的 `text` 键与两个消费模块均不兼容，现已在切片器中统一修正。回归覆盖 host 的精确 TTS 载荷和 assistant/pause 不入队，反编译证据保存于 `face-hand-manager-decompiled/emit_script_item.c`，完整验证继续为 `128/128 PASS`。

互动空回复生成器 `_fallback_reply_text` 的完整主体随后定位到 `0x180008c90`（1112 行反编译）。语言先规范化为小写；`vi/vi-vn/vietnamese` 使用越南语，`zh/yue/ja` 前缀共用中文，其余使用英文。五种事件分别是 `danmu/enter/follow/like/retention`，未知事件走各语言固定默认句。`danmu` 中文分支在有问题内容时精确拼为“`内容，昵称，这个问题我给你简单说一下。`”，无内容时为“`昵称，我看到你的问题啦。`”；英文、越南语的全部前后缀也已从 PE 原始 UTF-8 数据解码。

FaceHand 的互动开关 `_interaction_enabled` 主体 `0x180026ef0` 只执行一次严格比较：`int(interval) < INTERACTION_OFF_SECONDS`。继续反编译常量初始化体 `0x180062ea0` 后确认槽 `+0x1818` 由 `PyLong_FromLong(100000)` 创建，因此 `100000` 是关闭互动的哨兵值，`99999` 仍启用；旧恢复版错误地以 `int(interval or 0) >= 0` 判断，使关闭哨兵永远无法生效，并且吞掉了 `None` 的原始转换异常。现已恢复精确转换、严格边界，并加入整数、字符串整数和临界值回归。

互动队列的数据协议也已从模块顶层类型构造和 `_tick_interactions` 主体联合确认。原模块用 `@dataclass InteractionMessage`，注解字段依次为 `msg_type: str`、`nickname: str`、`content: str`、`timestamp: float`、`processed: bool = False`；模块常量 `INTERACTION_MESSAGE_CAP` 映射到整数缓存槽 `+0x1808 = 500`。`_tick_interactions` 首先要求 `self.llm_config` truthy，然后调用 `time.time()`，在 `_lock` 内筛选全部 `processed == False` 的对象并只保留前 20 条，之后逐条设为已处理。恢复版已用 dataclass 替换自创字典/`received_at` 协议，`submit_danmu` 统一规范化类型并在锁内维持 500 条上限，tick 由单条消费修正为最多 20 条批量消费；类型、容量及 25 条消息只处理前 20 条的回归已补齐。事件级 LLM 分支仍在继续逐段核对。

`_tick_interactions` 创建的 LLM 闭包也已逐个定位。弹幕 lambda6 主体 `0x18002e600` 调用 `reply_danmu(nickname, content, product_info, self.qa_info, self.special_instructions)`；进场 lambda2、关注 lambda3、点赞/礼物 lambda4 分别调用 `reply_enter`、`reply_follow`、`reply_like`，后三者统一传入 `(nickname, self._active_product_info(), self.special_instructions)`。四条分支均先用 `_interaction_enabled(interval)` 检查 100000 关闭哨兵，再比较 `now - last_reply < interval`，通过后更新对应时间戳并调用 `_submit_interaction_llm`；进场另以 `welcomed_nicknames` 去重。弹幕还先检查 `question_blocked_keywords`，并在启用 `enable_ai_control_reply` 时并行提交淘宝文字场控链。恢复版已删除二进制中不存在的 `interaction_replies` 固定模板替换，恢复四类公开 LLM 调用、独立节流、黑名单/禁词、进场去重和场控并行路径，精确参数及三类事件回归已加入。

上游 `_normalize_interaction_msg_type` 主体 `0x180002a60` 已完整还原。它对 `msg_type or "弹幕"` 只执行 `str(...).strip()`，不会转小写；`分享/comment/chat → 弹幕`，`enter/进入/进直播间/member/join/进入直播间 → 进入直播间`，`follow/关注主播 → 关注`，`gift/礼物/点赞/like → 礼物`，未知非空类型原样保留。仅当规范类型为“弹幕”时，再调用 `_is_entrance_message_content(content)`，命中则改为“进入直播间”。这证明模块内部事件枚举始终使用中文，而旧恢复版自创了 `comment/enter/follow/gift` 英文枚举并无条件 `.lower()`。`submit_danmu` 现已同步恢复无昵称丢弃、truthy 时间戳否则 `time.time()`、`float()` 转换、进场消息 `insert(0, ...)` 优先和其他消息尾部追加；tick 分支也改为消费原生中文枚举。

此前恢复版只做“中文/非中文”二分，文案和标点均为猜测，还自创了 gift 专用句。现在三套语言、五种事件、空/非空问题以及未知类型共 20 条断言逐字验证；`_submit_interaction_llm` 的同步和异步 fallback 也随精确文案更新，全量验证保持 `128/128 PASS`。反编译证据保存在 `rea-output/live-manager-decompiled/fallback_reply_text.c`。

### LiveManager 音频任务优先级

`_audio_task_queue_name` 的包装体为 `0x180081000`、主体为 `0x1800812c0`。原逻辑读取 `task.get("payload") or {}`，再把 `payload.get("queue") or "normal"` 转为字符串、去除空白；队列名不在 `_pending_audio_tasks` 时统一回落到 `normal`。这也确认普通 LiveManager 只维护 `normal` 与 `danmu` 两类待处理计数，旧恢复版额外加入的 `manual` 不是该模块的原生队列。

`_take_next_audio_task` 的包装体为 `0x180088110`、主体为 `0x180088280`：先对 `self._audio_task_queues["danmu"]` 执行 `get_nowait()`，为空时才对 `normal` 队列执行 `get(timeout=0.2)`，两者均空时返回 `(None, None)`。恢复版已由单一 FIFO 改回双队列，因此即使 normal 任务先入队，后到的弹幕仍会优先合成；未知/手动队列会落入 normal。清空全部任务现在逐队列扣减计数，清 normal 时不会取出再塞回 danmu 任务。

相邻 `_audio_worker_loop` 的包装体为 `0x180089380`、主体为 `0x1800894f0`。每个任务的执行异常会输出“`[live.local] 音频任务执行异常: {exc}`”并打印 traceback，但不会终止 worker；无论成功或失败，`finally` 都会把相应 pending 计数减一。回归覆盖 danmu 抢占 normal、未知队列回落、计数归零，以及首个合成任务抛异常后继续执行第二个任务；完整验证保持 `128/128 PASS`。

### TTS 执行入口与清队列竞态

`_handle_tts_speak` 包装体 `0x180097020`、主体 `0x180098660` 的入口数据流已经分段恢复。函数先对 `payload["text"]` 做空值回退和 `strip()`，并要求 `host_streamer` 存在；音色优先使用 payload 的 `voice_id`，否则使用 `_primary_voice_id`。推理版本、语言、语速、队列、目标脸索引、静默特征和音频缓存开关也分别按“payload 覆盖实例默认值”解析。文本会先替换时间变量；显式 `needs_language_translate` 为真，或目标语言禁止汉字且文本仍包含汉字时，经带超时的 `translate_text_llm` 翻译。之后才调用 `_limit_tts_synthesis_text`，其三元组结果中的截断文本进入实际合成。

恢复版现已把上述链路接到已有 near-clone 与通用 provider 合成入口，最终以 `queue_name`、`use_silent_features` 和 `target_face_index` 参数送入 streamer。函数开头还快照 `_normal_audio_epoch`；普通音频合成结束后若 epoch 已变化则直接丢弃，防止耗时合成跨越“清普通队列”操作后又把旧话术塞回来。回归覆盖 payload/default 合并、200+200 汉字长文本截断、播放器参数和过期普通音频抑制。Minimax、CosyVoice、本地合成和 near-clone 的各自异常/超时细节仍在继续按主体分支校准。

provider 分支现已进一步校准。模块常量初始化函数 `0x1800f5530` 把 `.rdata` 的 `0x180120578`、`0x180120580` 分别构造成 `TTS_CLOUD_TIMEOUT_SECONDS` 与 `TTS_LOCAL_TIMEOUT_SECONDS`；原始 IEEE-754 值为 `90.0` 和 `120.0`。`_handle_tts_speak` 主体比较的是 `voice_infer_version == "minimax"/"cosyvoice"`，两类云服务均经 `_run_with_timeout(..., 90, ...)`；其他版本先拒绝 provider 与版本不匹配的云音色，再由 `_ensure_voice_synthesizer(voice_id, voice_infer_version)` 获取可复用本地合成器，并以 120 秒超时调用 `synthesize(text, speed, language, use_cache)`。旧恢复版仅检查 `voice_general_config.provider`，且每次本地合成都重新创建/销毁模型，现已修正。

near-clone 分支也确认只在 `use_near_audio_clone`、队列为 `danmu` 且 streamer 暴露 `get_near_audio_clip` 时启用，并使用本地 120 秒超时；normal 话术仍走选定音色的常规合成。这避免旧实现错误地让整场普通话术持续截取近场音频。合成成功后，normal 任务若带 `product_index` 会把音频路径记入当前 session 的 `audio_product_map`；`seek_after_ms` 非空且播放器支持 `schedule_seek_after_interaction` 时转为整数提交。Minimax、CosyVoice、本地与近场四路分派、90/120 秒常量、商品映射和 2345 ms 延迟跳转均已加入回归，全量验证保持 `128/128 PASS`。

超时执行器 `_run_with_timeout` 的包装体为 `0x18008aad0`、主体为 `0x18008ba20`。原实现创建结果字典与 `threading.Event`，后台线程名为 `tts-timeout-` 加描述前 24 个字符，且设置 `daemon=True`；worker 把返回值写入 `value`，把任意 `BaseException` 写入 `error`，并在 `finally` 中触发 event。调用端以 `event.wait(timeout)` 判断超时：等待失败抛 `TimeoutError`，成功后若存在 `error` 则原样重新抛出，否则返回 `value`。它不会强杀超时线程。恢复版已由匿名线程加 `join()` 的近似实现改为该原生协议，回归覆盖正常返回、`ValueError` 身份/文案保持和 0.01 秒超时；全量验证继续为 `128/128 PASS`。

与之配套的 `_handle_clear_normal_queues` 已定位为包装体 `0x180085360`、主体 `0x180085620`。主体首先执行 `_normal_audio_epoch += 1`，随后调用 `_drain_normal_audio_task_queue()`，再对 `host_streamer.clear_audio_queues()` 执行播放器全清；播放器异常被捕获，函数仍继续处理 payload 的后续控制标志。恢复版已补齐 epoch 推进、仅清待合成 normal 任务但清空播放器现存音频的区别。payload 中 `new_image_model_id` 或 `new_voice_id` 为真时，原函数还会复制 payload、强制 `clear_queues=False`，构造 `{"id": 0, "session_id": None, "seq": 0, "type": "switch_model", "payload": ...}` 并作为 normal 任务入队，避免清队列和模型切换互相递归。精确任务结构、danmu 待合成任务保留和播放器全清均已有回归。

后续 `_handle_switch_model` 包装体为 `0x1800a0aa0`、主体为 `0x1800a0d60`。它读取 `new_image_model_id`、`new_voice_id` 和 payload/实例回退的 `voice_infer_version`。新形象通过配置 `image_base_dir` 与模型 ID 组成目录，在 streamer 支持 `switch_image_model` 时切换；新音色写回 `_primary_voice_id` 与 `voice_infer_version`，随后调用 `_ensure_voice_synthesizer(..., force_refresh=True)` 立即刷新缓存模型。`clear_queues` 为真时最后调用 `host_streamer.clear_audio_queues()`。三类操作均有独立异常保护。恢复版已替换此前只读取不存在的 `model_id` 并传给 `_runtime.switch_image_model()` 的近似实现；临时真实目录、形象路径、v2 音色强制刷新、状态写回和清队列回归通过，完整验证保持 `128/128 PASS`。

任务处理器中的停顿和预录音频路径也已校准。`_handle_pause` 包装体 `0x18009fca0`、主体 `0x18009ff60` 并不调用播放器的 `pause()/resume()`；它把 `payload["duration"]` 转为浮点数，非正值或无 streamer 时返回，调用 `_create_silent_audio(duration)` 生成静音 WAV，再以 payload/default 的队列名调用 `add_audio_to_queue(path, queue, use_silent_features=True)`。旧恢复版把停顿任务误解释成全局暂停开关，现已恢复为可排队的定长静音片段。

`_handle_play_audio_index` 包装体 `0x18009eb50`、主体 `0x18009ee10` 会严格执行 `int(payload["index"])`，拒绝负数及超出 `_script_audio_files` 长度的索引；合法项读取 payload/default 的 queue 和整数 `target_face_index`，随后调用 `host_streamer.add_audio_to_queue(audio_path, queue, target_face_index=...)`。恢复版此前默认缺省索引为零、忽略队列/目标脸并直接依赖 `_runtime`。1.5 秒 danmu 停顿、第二个预录音频、目标脸 3 和负索引拒绝均已加入回归，全量验证仍为 `128/128 PASS`。

### 本地直播启动状态闭环

`start_live` 的包装体为 `0x1800622b0`、主体为 `0x180062730`。REA/Ghidra 对 2387 行 Cython 主体的控制流与间接属性引用分析确认它是覆盖层而非图像播放器的底层入口：先在 `_local_session_lock` 保护下停止旧 session，复制 Minimax/CosyVoice provider 配置，再调用底层直播启动；底层返回假值时直接返回 `False`。成功后才绑定 `host_streamer`，创建 `LocalLiveBrain`，启动音频 worker、平台控制准备和 `_local_session_thread`。因此 session 不会早于图像运行时出现。后半段异常路径会停止已经启动的底层运行时并返回 `False`，避免留下半启动资源。

恢复版现已把这套事务顺序落到真正的 `LiveManager.start_live()`，并增加原生字段 `_local_session_lock` 与 `_local_session_stop_event`；`start_local_runtime()` 只负责规范化参数并委托该入口，不再自行重复创建 session。启动成功会同步 `_primary_voice_id`、`voice_infer_version`、`language`、`voice_speed`、`use_audio_cache` 与 `use_near_audio_clone`，同时把 LocalLiveBrain 的 TTS payload 配置保持一致。`DigitalLiveManager.start_live()` 加载出的预录音频列表保存为 `_script_audio_files`，使 `_handle_play_audio_index` 可用；停止成功清空 `host_streamer`，避免停播后任务继续写入已关闭播放器。模拟底层成功的回归真实经过覆盖层，验证 v3 音色、en-US、1.4 倍速、禁用缓存、near-clone、两个 provider 配置的隔离复制、session 创建与 runtime 绑定；全量验证为 `128/128 PASS`。

启动/停止回归同时暴露并修复 `_local_session_loop` 的竞态：旧循环在条件中检查 `self._session` 后又重新读取并调用 `tick()`，停止线程可在两次读取之间将其置空，产生 `None.tick()`。现改为每轮持有同一 session 快照，再检查 stopped 和等待事件。模拟成功启动验证 v3 音色、en-US、1.4 倍速、禁用缓存、启用 near-clone 以及配置传递；完整验证无后台 session 线程异常并保持 `128/128 PASS`。

### 商品 KT 板覆盖层

`tools/product_kt_overlay.pyd` 已建立独立 Ghidra 工程 `rea-output/ghidra-product-kt-overlay` 并导出函数表。`ProductKtOverlay.apply` 的包装体/主体为 `0x180045300`/`0x180045670`；主体首先对 `None` 或非 `numpy.ndarray` 输入原样返回。预计算路径并非按帧文件名查询字典，而是对 `physical_index` 做 `int` 转换后以 `% len(_boxes)` 循环索引，与播放器物理帧循环保持一致；空框才回退实时检测。贴图异常由原函数捕获，打印 `[product.kt] apply failed: ...` 后返回原帧，不能终止播放线程。

`load_from_model_dir` 的包装体/主体为 `0x18003f990`/`0x18003fc50`。缓存严格解包为 `(boxes, frame_size, hit)`，并在锁内写回 `_boxes`、`_frame_size`、`_frames_dir` 后重置 tracker；其中 boxes 保留每一物理帧的位置，未检测到的帧以 `None` 占位。此前恢复版只保存命中框的 `{文件编号: (box, size)}` 字典，导致缺帧、非零编号和循环播放时错位。恢复源码已改为原生全帧列表及缓存三元组；构造器主体 `0x18003d7c0` 也确认 `_product_key` 与上述三个缓存字段。回归覆盖三帧/两个命中框的 NPZ 往返、120→240 分辨率缩放、索引 3 循环到第 0 帧、空框、贴图异常、`None` 和非数组输入；全量验证保持 `128/128 PASS`。

### 商品自动抠图模型生命周期

`tools/product_cutout.pyd` 已建立独立 Ghidra 工程 `rea-output/ghidra-product-cutout`。`ProductCutoutEngine.load` 的包装体/主体为 `0x180014680`/`0x180014930`；原流程在缺少本地权重时打印下载仓库，按当前 CUDA 可用性选择 device，依次加载 BiRefNet 与 GroundingDINO，最后才设置 ready。成功与失败路径分别输出 `[product.cutout] models ready` 和 `[product.cutout] load failed: ...`，失败前会释放所有已部分加载的模型，不能静默隐藏下载、权重或 CUDA 错误。

`_release_unlocked` 的包装体/主体为 `0x180018620`/`0x180018790`。反编译确认它严格写回五个字段：`_ready=False`，并将 `_biref`、`_biref_transform`、`_dino`、`_dino_processor` 置空，再尝试清理 CUDA cache；它不会清空 `_model_root`。公开 `unload` 还输出 `[product.cutout] models unloaded`。`cutout_bgr` 的包装体/主体为 `0x180018e50`/`0x1800197f0`，推理异常打印 `[product.cutout] infer failed: ...` 后返回 `None`。恢复源码已补回完整可观察诊断并保持模型根目录状态语义；回归覆盖五字段释放、根目录保留、卸载日志和非法输入，全量验证继续为 `128/128 PASS`。

### 快手 WebSocket 错误与重连链

`kuaishou_v2/KsLive.pyd` 的 `_on_error` 主体 `0x18001c1d0` 已完成校准。原函数先输出“`[错误] {error}`”，然后等待 `self._on_close(ws)`；`_on_close` 再输出“`[已关闭] WebSocket连接已关闭`”并等待 `self._reconnect()`。恢复版先前从 `_on_error` 直接跳到 `_reconnect`，遗漏了关闭回调及其可观察日志；现已恢复为 `_on_error → _on_close → _reconnect` 的原生异步调用链。回归同时覆盖单次错误触发的一次关闭/重连，以及错误后再显式关闭的两次重连语义；全量验证为 `128/128 PASS`。

### 录播实拍报时资源所有权

`live/record_live_manager.pyd` 已建立独立 Ghidra 工程 `rea-output/ghidra-record/record_live`，并导出 `start_live`/`stop_live`、报时准备、实拍后台任务、本地合成、取消与清理的包装体和真实主体。`_process_real_shot_task` 主体 `0x180009ff0` 证实：生成 MP4 会先放入会话 `temp_files`；播放器 `insert_video(output)` 调用成功后，立即将该路径从 `temp_files` 移除，再执行会话清理。这是一次明确的所有权转移：播放器接管成功后，报时 worker 不能删除该文件；插入失败时路径仍留在会话清单中，由 `_cleanup_session` 删除。旧恢复版等待私有 `_insert_worker` 后无条件删除输出，可能让播放器持有失效路径，现已按二进制语义修正。

同一主体还确认混音链的原生中间量为 `start_ms`/`end_ms`/`silence_duration`/`part1`/`part_middle_silence`/`part3`/`final_audio`：用等长静音替换原音区间，再从 `start_ms` 叠加新语音。恢复源码已同步原始 RealShot 诊断文案，并删除二进制中不存在的播放线程轮询。真实 FFmpeg 生成、音轨替换、AAC 封装、插播后输出文件保留及会话状态回归全部通过，全量验证保持 `128/128 PASS`。反编译证据位于 `rea-output/record-live-decompiled/`。

`start_live` 真实主体 `0x1800027a0` 也已逐分支同步。本地源会输出开播请求、使用 `os.path.exists` 拒绝缺失文件，并把 `os.path.abspath(video_path)` 作为播放源；抖音源要求非空直播间链接，再由 `LiveStreamIngestProcess` 转换为本地播放源。去重处理器只在顶层 `deduplication_config["enabled"]` 为真时创建。`Player` 用 `width`/`height`/`output_mode`/`frame_processor` 构造后先写入 `self.video_player`，再精确调用 `start(playback_source, loop=True)`；这保证启动中途异常时也能在异常分支停止已创建的播放器。恢复版先前缺失文件校验、`loop=True`、`enabled` 门控和启动失败的播放器回收，现已全部补齐。新回归覆盖缺失路径、参数精确传递、去重开关和解码器启动异常清理，全量验证仍为 `128/128 PASS`。

### 输出分辨率五档协议

`tools/output_resolution.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-output-resolution/output_resolution`，六个公开函数的包装体、五个独立主体、GPU 检测主体以及模块初始化函数均已导出。模块创建体 `0x180006610` 和执行体 `0x180006e60` 给出了精确常量：`PORTRAIT_RESOLUTION_MAP = {"480p": (480, 854), "720p": (720, 1280), "1080p": (1080, 1920), "2k": (1440, 2560), "4k": (2160, 3840)}`，`RESOLUTION_RANK` 按相同顺序映射为 `0..4`。旧恢复版只有前三档，会把真实 `2k`/`4k` 配置静默降为默认 `720p`，现已补齐全部尺寸和公开 `RESOLUTION_RANK` 常量。

`detect_primary_gpu_name` 主体 `0x180002ca0` 使用 `nvidia-smi --query-gpu=gpu_name --format=csv,noheader`，过滤空行后返回第一个去空白的 GPU 名；原实现捕获任意 `Exception`，不只是子进程异常。恢复源码已同步这一边界。回归覆盖五档规范化、竖/横屏目标高度、素材限制降档、精确提示文案、GPU 命令参数及广义异常回退；全量验证保持 `128/128 PASS`。证据位于 `rea-output/output-resolution-decompiled/`。

### 客户包身份路径恢复

`tools/customer_pack.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-customer-pack/customer_pack`，并导出 `_client_base_dir`、`_asset_base_dirs`、`read_admin_id` 与 `is_vietnam_customer_pack` 四个完整主体。`_client_base_dir` 主体 `0x180001080` 精确执行 `dirname(dirname(abspath(__file__)))`，返回字符串；原恢复版把实现放在包根并返回 `Path`，虽能在当前目录偶然命中，但已破坏原包层级和公开返回类型。现已将真实实现迁回 `recovered/tools/customer_pack.py`，根级模块只作兼容转发。

`_asset_base_dirs` 主体 `0x180001950` 在普通 Python 模式返回客户根目录；冻结运行时计算可执行目录和 `_internal`，仅在目录存在且未重复时加入候选。`read_admin_id` 主体 `0x180002ac0` 按候选顺序读取 `assets/web/id.txt`，以 UTF-8 去空白后只接受纯数字，单个候选异常不阻断后续回退；`0x1800041c0` 只判断管理员 ID 是否为 `21`。恢复包已补入原交付包的 `assets/web/id.txt`（ID `62`）。回归覆盖未冻结/冻结路径顺序、去重、非法 ID 回退、62 普通包和 21 越南包判定；全量验证保持 `128/128 PASS`。证据位于 `rea-output/customer-pack-decompiled/`。

### 违禁词替换模块静态调用链

`tools/replace_illegal_words/replace_forbidden_words.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-replace-forbidden/replace_forbidden`。模块不是简单的字符串表替换：六个原生函数 `_protect_phrases`、`_restore_phrases`、`_remove_superlative_patterns`、`_pick_replacement`、`replace_forbidden_words`、`test_replacement` 均已定位，包装体/主体分别为 `0x180001070/0x1800012b0`、`0x180001c10/0x1800019d0`、`0x180002310/0x180002480`、`0x180002970/0x180002ae0`、`0x180006363/0x180003610`、`0x180006b51/0x180006490`。完整反编译体、注册字符串引用和模块初始化体保存在 `rea-output/replace-forbidden-decompiled/`。

模块初始化证据确认原包导入 `jieba` 与 `random`，并使用 `jieba.initialize()`、`jieba.add_word`、`random.choice`、`sorted(..., reverse=...)`、`enumerate`、安全短语槽位和最高级模式清理。原始 UTF-8 常量进一步确认 `_SAFE_FROM_ZUI_REGEX` 对应的安全项只有“最近、最终”，旧恢复版自创的“绝对值、最后、文本”已删除。`_remove_superlative_patterns` 主体精确执行两次固定替换：先 `re.sub(r"最[\u4e00-\u9fff]{1,3}", "", text)`，再 `re.sub(r"全网最[\u4e00-\u9fff]*", "", text)`；旧版的 `{0,3}` 限长、lambda 保留捕获组和函数内部二次安全短语保护均不存在。

主入口现已恢复每次调用先初始化 jieba、把额外违禁词登记为星号等长替换与 `medium` 等级、再把完整词库逐项加入 jieba。控制流进一步确认：先把长度至少为 2 的 `multi_words` 按长度倒序直接补扫；随后清理最高级模式；字典单字阶段只特殊处理“最”，其他单字原样保留；最后执行 `list(jieba.cut(processed))`，逐 token 重组并恢复安全槽位。旧恢复版把全部单字与多字词统一直接替换，现已按上述三阶段拆开。

`_protect_phrases` 主体还确认 `slots` 是按实际命中顺序追加的列表，而不是旧恢复版的字典；未命中的前置安全短语不会造成后续槽位编号空洞。最终结果直接恢复安全槽位，不执行旧版额外添加的空白压缩和 `strip()`。新增回归验证“最近/最终”完整及单独命中、槽位列表形状、两条正则顺序、单字“禁”保留、单字“最”替换、多字“词组”补扫、jieba 初始化/加词与 cut 重组副作用；全量验证保持 `128/128 PASS`。本阶段不需要 Windows，Windows 仅用于最终加载 CPython 3.10 `.pyd` 做差分验证。

相邻 `forbidden_words.pyd` 已新建 Ghidra 工程 `rea-output/ghidra-forbidden-words/forbidden_words`，模块执行体 `0x1800037f0` 共约 3.3 万字节、反编译为 6836 行，证据保存在 `rea-output/forbidden-words-decompiled/`。Cython 字符串初始化体 `0x180001020` 给出了模块状态偏移到 UTF-8 常量的完整映射；执行体以 `_PyDict_NewPresized(0x93)` 创建 147 项词典。把 147 个 `word` 偏移、对应 `PyList_New(n)` 和列表元素偏移逐项关联后，确认原表有 147 条、146 个唯一词，其中只有 8 条带非空替换：`今天→今儿`、`原价→日常价`、`优秀→棒`、`块钱→块`、`囤→豚`、`周末→双休`、`扣个1→扣个一`、`扣1→扣一`；其余列表均为空，命中时由 `_pick_replacement` 回退为空字符串。

旧恢复版只有 111 项，并为大量条目自创“优惠价、知名品牌、日常养护”等替换文案，已整体替换为按二进制构造顺序恢复的精确 147 项表，包括空字符串首项、重复的“周年庆”以及此前缺失的“装13、评论区、有惊喜”等词。回归锁定总数、唯一数、首尾顺序和全部八组非空映射；完整验证保持 `128/128 PASS`。至此 `forbidden_words.pyd` 数据模块可在 Mac 静态证据范围内标记为完成。

`tools.audio_devices.pyd` 已完成模块级静态闭环。Ghidra 工程位于 `rea-output/ghidra-audio-devices/audio_devices`，包装器/主体为 `0x180002fd0/0x180001030`。原版只枚举 PortAudio host API `0`，按 `deviceCount` 用循环索引读取设备；返回项的 `index` 也是循环索引，不使用设备字典里的 `index`，也没有多 host 枚举、去重或额外类型转换。异常会打印“`枚举音频设备失败: `”并保留部分结果，`terminate()` 位于清理路径。恢复版此前遍历所有 host、改变索引和异常语义，现已逐项修正；正常双工设备与中途异常回归均通过，全量门禁保持 `128/128 PASS`。详细证据见 `rea-output/audio-devices-notes.md`。

`tools.audio_player.pyd` 新建了 Ghidra 12.1.4 持久化工程并完成两个入口的主体级校正。`scan_audio_files`（`0x18000bf80/0x18000c0f0`）只接受 MP3/WAV，保留 `os.listdir` 顺序并传播目录异常；旧恢复版错误地排序、吞掉缺失目录并扩大到六种格式。`insert_audio`（`0x180002d90/0x180003090`）只按 `queue_type.lower() == "danmu"` 选队列，原样入队且返回 `None`；旧版额外解析路径、检查存在性并返回路径。两项已修正并加入回归，详细证据见 `rea-output/audio-player-notes.md`。

同一 `audio_player.pyd` 的构造、启动、停止主体 `0x180001190/0x180001c60/0x180002470` 也已完成联合核对。原版构造时立即创建 PyAudio，停止标志为普通 bool；`start()` 首次返回 `True`、重复启动返回 `False`，线程只传 target 后单独设置 daemon；`stop()` join 线程并关闭 stream，但不会 terminate PyAudio，后端释放属于析构器。旧版采用 Event、延迟创建后端、没有原生布尔返回值且 stop 提前终止后端，影响停止后重启。现已恢复原生命周期、字段常量和精确启动/停止日志，模拟线程回归确认 join 超时为 2 秒且 stop 不释放后端。

`AudioPlayer._play_audio_thread` 主体 `0x180003680` 已继续恢复。原循环依次以 `empty()`/无参数 `get()` 检查弹幕和普通队列，弹幕分支每次播放后立即回到循环头；全部为空才 `time.sleep(0.1)`。它不使用阻塞超时 get、不在此层切换 `is_playing`，也不捕获 `_play_audio_file` 异常。旧恢复版的三处差异均已修正，弹幕优先、精确等待和异常传播回归通过。

`AudioPlayer._play_audio_file` 包装器/主体 `0x1800046b0/0x180004900` 已完成主体级恢复。原版不是直接用 `wave.readframes`：它把 FFmpeg 结果交给 `AudioSegment.from_wav`，强制声道数和 44100 Hz，再以 `make_chunks(..., 1024)` 分块，通过共享 `self.player` 创建流并写入每块 `_data`。循环同时响应 `stop_flag` 和可选的 `stream.is_stopped()`；异常、流停止/关闭以及转换临时文件删除均有独立路径。恢复源码已改为该调用链，新增模拟 pydub/PyAudio 回归，且全量验证仍为 128/128 通过。

`AudioPlayer._convert_audio_with_ffmpeg` 包装器/主体 `0x180008b00/0x180008dc0` 也已按 Cython 控制流收口。恢复了应用相对临时目录、UUID WAV 文件名、14 项 FFmpeg 参数顺序、Windows 隐藏窗口 `STARTUPINFO`、一次性命令缺失告警、转换失败与未知异常分支。旧版自行跳过标准 WAV、搜索 `ffmpeg.exe`、使用系统临时目录及 `capture_output/timeout`，这些兼容性扩展与原程序不符，现均已移除；定向和全量回归通过。

`tools/edit_audio/edit_audio.pyd` 已建立 Ghidra 工程并完成模块执行主体 `0x180001560` 恢复。这个 23 KB 扩展只是启动包装器：从 sibling `main` 导入 `main`，在 `__name__ == "__main__"` 时零参数调用；真正编辑器属于相邻 217 KB 的 `main.pyd`。恢复树此前错误地从包装器重导出整套编辑器 API，现已按真实模块边界缩回单一 `main` 入口，全量验证继续通过。证据见 `rea-output/edit-audio-notes.md`。

相邻 `tools/edit_audio/main.pyd` 现已建立独立 Ghidra 工程，并完成全部 `AudioEditorAPI` 包装器—主体地址映射。二进制中 12,028 字节的原始 WebView HTML 已逐字取回，替换此前约 2 KB 的简化页面并以固定 SHA-256 回归。目录加载现恢复“必须存在 WAV、且每个 WAV 必须有同名 TXT”的原约束；配置损坏回退、取消选择、空关键词、按修改条目计数和删除完成文案也已按主体修正。自然排序、大小写 WAV、缺 TXT 错误、TXT 持久化和页面哈希回归通过，全量门禁保持 `128/128 PASS`。

`edit_audio/main.pyd` 的转换链也已完成结构校正。原生 `items` 是 basename 键控字典，`_convert_basename` 才负责调用 synthesizer，而 `convert_item` 只做输入同步和状态包装；旧恢复版把二者职责颠倒且使用列表。现已恢复固定 `speed=1.0`、逐项 `reference_audio/reference_text`、`shutil.move` 覆盖 WAV、TXT/内存同步、未修改短路，以及 `convert_all` 只处理修改条目的策略。单条、批量、缺失条目和输出移动回归通过，完整门禁仍为 `128/128 PASS`。

该工具的 WebView 生命周期也已按 `main` 主体 `0x1800191b0` 与 `on_closed` 闭包 `0x180018df0` 恢复：窗口为 1400×860、最小 1100×720，允许调整尺寸和文本选择；启动参数固定关闭 debug/private mode。关闭时先调用 API shutdown，再 `os._exit(0)`。恢复版原有尺寸、标题、事件绑定和退出行为均已校正，模拟 WebView 回归及全量验证通过。

### 云端数字人提示词精确恢复

`tools/cloud_dh/prompts.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-cloud-dh-prompts/prompts`。`build_avatar_prompt` 的包装体/主体为 `0x180001020/0x180001230`；固定中文提示词从二进制原始偏移 `0x66c0` 逐字恢复，补充前缀“人物外观补充要求：”与句号分别位于 `0x6510`、`0x69c4`。旧恢复版使用了自创英文提示词，现已替换为原包的年轻中国女性、职业装、中景半身、纯绿幕和竖屏 9:16 等完整约束。

控制流确认参数先按真值分支，再执行 `strip()`；空结果返回固定提示词，非空结果直接拼接固定提示词、补充前缀、去除首尾空白后的描述和句号。原函数不会压缩描述内部空白，也不会额外插入换行。精确字符串、空值、首尾空白与内部换行回归均通过，全量门禁保持 `128/128 PASS`。详细证据见 `rea-output/cloud-dh-prompts-notes.md`。

### 直播贴片标题生成路由校正

`tools/live_sticker/titles.pyd` 已建立独立 Ghidra 工程 `rea-output/ghidra-live-sticker-titles/titles`。`_chat_ark` 与 `generate_room_titles` 的主体分别为 `0x180001510`、`0x180003570`，模块初始化主体为 `0x180004b20` 和 `0x180006240`。二进制内嵌函数说明明确写明“生成 3 条候选标题，优先客户端 LLM 配置；失败则用火山生图同套 API Key 调 Ark 文本模型”，旧恢复版在存在 Ark Key 时反而直接跳过客户端 LLM，现已恢复原优先级。

静态常量还确认 Ark 标题模型为 `doubao-seed-1-6-flash-250828`，而不是旧恢复版自填的 `doubao-1-5-pro-32k-250115`。模块状态表进一步确认 Ark JSON 为 `model/messages/temperature/thinking`，温度为 `0.7`、thinking 为 `{"type":"disabled"}`，超时为原生常量 120 秒；HTTP 状态显式与 200 比较，并保留缺少 Key、非 200 与空内容的原始中文异常。`generate_room_titles` 的原生返回键是 `room_titles`、`room_title`、`title_model`，上层调用已同步；错误按 `llm_config: …` 和 `ark: …` 聚合。定向与完整验证全部通过，本模块现已达到 Mac 静态证据闭环；证据见 `rea-output/live-sticker-titles-notes.md`。

### 云端数字人音频时长探测闭环

`tools/cloud_dh/audio_duration.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-cloud-dh-audio-duration/audio_duration`。`_find_ffprobe` 与 `get_audio_duration` 主体分别为 `0x1800017f0`、`0x180003600`，字符串状态初始化体为 `0x180004880`。原生定位器从模块路径计算客户包根目录，按 `_internal/env/ffmpeg/bin`、`_internal/env/Library/bin`、构建树 `packed/_internal/env/Library/bin` 和命令名 `ffprobe` 四个候选逐一执行 `-version` 验证；旧恢复版扩展到 `shutil.which`、系统解释器目录与 `env_50`，均非该模块行为，现已删除。

时长主体使用固定八项 ffprobe 参数，严格传入 `capture_output=True, text=True, check=True` 并把 stdout 去空白后转为 float；找不到 probe 才调用 `librosa.get_duration(path=path)`。空路径或非文件使用原始“音频不存在”异常，探测失败统一包装为“无法读取音频时长”。旧版的 `check=False`、负时长过滤、错误吞并和 WAV `wave` 兜底均已移除。命令形状、候选验证、librosa 回退和缺失文件回归通过，全量门禁保持 `128/128 PASS`。详细证据见 `rea-output/cloud-dh-audio-duration-notes.md`。

### 直播贴片提示词原始模板恢复

`tools/live_sticker/prompts.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-live-sticker-prompts/prompts`，十二个业务主体已批量导出。二进制内含完整的背景、前景绿幕贴片、淘宝封面和直播间标题系统提示词；旧恢复版使用自创英文模板并要求生成 8 个标题，和交付包不符。现已逐字恢复三套中文生图模板，标题系统要求也恢复为“只输出 JSON 数组、恰好 3 条、每条 8～16 个汉字”等五项约束。

商品字段协议确认使用 `product_name/product_selling_points/product_price/product_content`；摘要标签依次为“商品名称/卖点/价格/补充信息”，空值回退“未提供商品信息”，用户提示以“商品信息：\n”起始。标题解析为空时恢复原始 `ValueError("标题解析结果为空")`。模板、字段、空摘要和异常回归均已加入。

`build_product_vibe` 与 `_strip_spam` 也已闭环：按原生顺序逐项删除 18 个促销词，再删除感叹/问号/波浪号与中英文括号。商品名使用 `product_name/itemName` 并截断至 28 字，卖点切分后取前两条，补充内容使用 `product_content/content` 并截断至 18 字，最后以中文逗号组合。`_clip` 的尾部标点裁剪与空输入返回空串均已恢复。精确清洗、顺序、截断、回退与三类生图提示词已加入回归，全量验证保持 `128/128 PASS`；证据见 `rea-output/live-sticker-prompts-notes.md`。

### OCR 捕获变化检测协议

`tools/auto_live_action/ocr_capture/capture_window.pyd` 已建立独立 Ghidra 工程并导出 161 个函数和全部 `CaptureWindow` 业务主体。`capture_screen` 的主体 `0x18000acf0` 确认返回值固定为 `image/changed` 字典，而不是旧恢复版的裸数组或 `None`；停止、无效矩形和异常路径均返回空图与未变化。

截图调用固定使用 `ImageGrab.grab(bbox=rect)` 和 `numpy.array`。首次截图、尺寸变化或未提供阈值时更新基准并报告变化；有阈值时以 `numpy.mean(current_image == last_image)` 计算逐元素相等率，只在 `similarity < similarity_threshold` 时更新基准。恢复源码和首次/相同/变化帧专项回归已同步，详细证据见 `rea-output/auto-live-capture-notes.md`。

同一扩展的窗口状态、几何与队列链也已校正：原生使用 `root` 和绝对右下边界，而非旧版 `window/positions`；初始框为屏幕宽度 80%、高度 40% 并居中，透明度 0.3。拖动按当前坐标叠加增量，四角缩放最小边长为 20。队列每个定时周期最多取一个命令，截图结果以 `image/pos` 投递。专项回归覆盖绝对矩形、队列形状、100ms 调度、拖动与缩放下限。

相邻 `ocr_capture/ocr.pyd` 也已建立独立 Ghidra 工程并完成两个公开主体。恢复版现在同时支持带 `boxes/txts/scores` 属性的新 RapidOCR 结果和旧序列结果，`None` 输入不调用引擎，旧结果缺少置信度时使用 `None`。此前强制 `str/float` 转换会改变原始值，现已按主体移除；现代对象、旧二元组和缺少 score 的专项回归通过。证据见 `rea-output/auto-live-ocr-notes.md`。

`bin/image_infer_v2/tools/position_compat.pyd` 已完成独立 Ghidra 主体恢复。原生 `bounding_box` 顺序为 `[Ymin,Ymax,Xmin,Xmax]`，目标边长公式由常量初始化体确认是 `img_size + int(img_size / 256) * 10`，默认 266；中间坐标为 float64，输出为 int32。当前字段优先 `landmarks`，旧包只回退 `crop_lm + bounding_box`。旧恢复版自行加入的 `frame_landmarks/positions/lmk/bbox` 别名和 float32 输出均已移除，坐标轴、缩放、字段、dtype 与错误文案专项回归通过。证据见 `rea-output/position-compat-notes.md`。

`bin/image_clone/utils/lip_detector/tools/detect_face.pyd` 的三个公开方法也已完成主体恢复。原类包装 sibling `FaceDetect(cpu=False, model_path=...)`，逐帧调用 `get_bboxes`，把五字段 xyxy 框转为 float32 xywh，并返回 `(boxes, indices)`；首个空帧返回空数组/空索引，后续空帧复用上一帧元组。旧恢复版直接构造 SCRFD、返回 boxes/keypoints 字典且没有时序回退，现已替换；依赖它的唇部裁剪也同步改为批量 xywh 协议。专项回归覆盖构造后的核心行为、空帧复用与 release。证据见 `rea-output/image-clone-detect-face-notes.md`。

`bin/image_clone/utils/hubert_extractor.pyd` 已建立 Ghidra 工程 `rea-output/ghidra-hubert-extractor/hubert`，构造与提取主体分别为 `0x180001320` 和 `0x180001c40`。原生实现用 `Wav2Vec2Processor` 和 `HubertModel` 以 `local_files_only=True` 加载同一模型目录，设备字符串原样传入 `.to(device)`，不做 CUDA 降级，也不调用 `.eval()`。提取链为 `processor(..., sampling_rate=16000, return_tensors="pt").input_values.to(device) → model(...) → last_hidden_state[0]`；特征帧数为奇数时裁掉最后一帧，最后执行 `detach().cpu().numpy()`。旧恢复版额外的 reshape、dtype 强制、`no_grad`、squeeze 和 CUDA 回退均已移除；专项契约回归已加入。详细证据见 `rea-output/hubert-extractor-notes.md`。

`bin/image_clone/utils/lip_detector/tools/get_landmark.pyd` 已完成三个业务主体的恢复：`face_det` (`0x1800012c0`)、`Landmark.__init__` (`0x180005160`) 和 `Landmark.detect` (`0x1800074b0`)。人脸裁剪使用 xywh 框的最大边乘 `1.05`形成正方形，越界位置补黑并保留负起点，只处理第一张选中人脸。关键点链已恢复为 192×192 归一化、HWC→CHW、CUDA PFLD 推理、均值脸偏移、裁剪尺寸回映及 int32 输出，返回 `(pre_landmark, x1, y1)`。旧版只把图片路径交给批量检测器，整条 PFLD 逻辑缺失，现已补全。证据见 `rea-output/image-clone-get-landmark-notes.md`。

`bin/image_clone/utils/lip_detector/lip_detector.pyd` 也已恢复三个主体：构造、批量人脸裁剪和批量关键点推理。原生 `_face_det` 用 `1.05` 而非旧恢复版的 `1.2` 扩展比例，返回原尺寸裁剪与 `(offset_x, offset_y)`；192×192 缩放、批量堆叠、CUDA PFLD、均值脸修正和绝对坐标回映均已回归 `detect_landmarks`。模型加载恢复为 `checkpoint["pfld_backbone"]`、`.cuda()` 和 `.eval()`。证据见 `rea-output/image-clone-lip-detector-notes.md`。

`lip_detector/tools/base_module.pyd` 已建立 Ghidra 工程并完成模型对象布局校正。MobileOne 的分支数字段、GhostOne 的推理/分支字段和 stride 约束已恢复；ReLU 恢复为非 inplace 实例，SE 降维数直接使用 `int(in_channels * rd_ratio)`。尤其是 `InvertedResidual` 的子模块名已从旧恢复版自创的 `conv` 改回原生 `inv_res`，避免 PyTorch checkpoint state-dict 键名不兼容。证据见 `rea-output/image-clone-base-module-notes.md`。

`lip_detector/tools/pfld_mobileone.pyd` 的构造与 forward 主体已与随包 checkpoint 联合校验。checkpoint 中 `conv_out.weight` 形状为 `(220,256,1,1)`，证明原层是 `Conv2d`，而非旧恢复版的 `Linear`；同时 `localization.0/3` 权重证明旧版漏掉了完整 localization 子网络。现在四个池化特征与 `conv8` 保持四维并按通道拼接，经 1×1 `conv_out` 后才执行 `view(batch,-1)`，已恢复与原权重完全兼容的网络布局。证据见 `rea-output/image-clone-pfld-notes.md`。

`image_clone/utils/video_preprocess.pyd` 的三个入口已完成主体级恢复。竖屏裁剪尺寸使用 `int()` 截断，不是旧版的 `round()`；宽高比差小于 `0.01` 时 `process_frame` 直接缩放，且不强制 `INTER_AREA`。`extract_frames` 按 `CAP_PROP_FRAME_COUNT` 遍历，返回每个 `.npy` 输出路径的列表，而非旧恢复版的整数计数；原生边界内也不自建目录或包装打开异常。证据见 `rea-output/image-clone-video-preprocess-notes.md`。

`image_clone/tools/step0_video_normalize.pyd` 已从临时兼容代码中拆回独立模块。`get_video_info` 使用 ffprobe JSON 恢复视频旋转后的有效宽高、帧率和音频规格；`normalize_video` 通过 `normalize_target_height` 选择目标高度，等比计算宽度并向下修正为偶数。输出名恢复为 `normalized_<原文件名>`，FFmpeg 使用 libx264/medium/CRF18 和 AAC 128k，保留探测到的采样率与声道数，不再强制裁剪、25 FPS、48 kHz 单声道。证据见 `rea-output/image-clone-video-normalize-notes.md`。

`image_clone/tools/generate_infer_data/face_detect.pyd` 的 PFPLD 和 98→68 关键点链已完成主体恢复。原生输入只执行 112×112 缩放、除 255、float32 和 HWC→CHW，不进行旧恢复版自创的 BGR→RGB 及 `[-1,1]` 归一化。ONNX 取输出索引 1；98→68 不是简单下标抽取，而包含左右眼轮廓的多个两点均值插值，现已完整恢复。模型路径、CPU/CUDA provider 和 SCRFD 500m/10g 选择也已按主体校正。证据见 `rea-output/image-clone-generate-face-detect-notes.md`。

`FaceDetect.get_bboxes` 的主体进一步确认它只是 SCRFD 转发层：ndarray 原样传入，路径输入经 `cv2.imread` 后从 BGR 转 RGB，最终调用 `detect(image, thresh=..., max_num=..., metric="default")` 并原样返回 `(boxes, keypoints)`。旧恢复版在这里又裁脸调 PFLD，并对已是 68 点的结果再次执行 98→68，现已删除。转发参数和返回形状已加入回归，全量门禁保持 `128/128 PASS`。

`image_clone/tools/generate_infer_data/scrfd.pyd` 已建立独立 Ghidra 工程，11 个业务主体全部导出。模块来自 InsightFace SCRFD 分支，但增加了 `cpu` 构造参数和 `detect(..., thresh=0.6, ...)` 阈值参数。恢复版已校正为按行 softmax、单一显式 CPU/CUDA provider、batched ONNX 输出分支、100 项锚点缓存上限、固定输入尺寸不覆盖及 `prepare()` 返回 `None`。原实现的 `get_scrfd` 在不下载时直接断言传入路径存在，不会像旧恢复版那样自行拼接 `root/name/scrfd_10g...`；`2p5gkps` 工厂则强制走下载分支。证据见 `rea-output/image-clone-generate-scrfd-notes.md`。

`image_clone/tools/generate_infer_data/infer_api.pyd` 已完成静态业务逻辑闭环。`read_video_frames` 按六位数 JPG 保存并只返回 `fps/width/height/total_frames`；`save_frame_data` 按原始顺序写入位置文本并返回 `None`。`process_face_frames` 现已恢复两遍帧扫描：第一遍求关键点外接矩形的平均 `width/height`，第二遍以该均值生成横向各 `0.75h`、纵向上 `0.15h`/下 `1.35h` 的非对称裁剪框，然后按图像边界裁剪并以 `[Ymin,Ymax,Xmin,Xmax]` 保存。GPU 回退、最高 score 选择、逐帧异常降级、100 帧进度输出和 `None` 返回均已对齐。证据见 `rea-output/image-clone-generate-infer-api-notes.md`。

`bin/image_infer_v2/infer_api.pyd` 现已建立独立 Ghidra 工程 `rea-output/ghidra-image-infer-v2/image_infer_v2`，导出函数表、全字符串引用和首批核心主体。`clear_audio_queues` 已从只清两个音频容器修正为原生的逐项排空、播放器画面队列清空以及七项语音/淡入淡出状态复位。`switch_image_model` 主体 `0x18002a110` 也已对齐：非 file 模式只警告并返回 `None`；file 模式停止旧预加载线程、清空但复用帧队列、重新计数 JPG、复位帧游标，并以新 Event 和 daemon Thread 启动 `self._preload_frames_worker`。旧恢复版自创的异常、队列重建、`data_dir` 改写和 `True` 返回已移除。证据见 `rea-output/image-infer-v2-notes.md`。

`drive_with_special_video` 主体 `0x18002c790` 的阻塞式注入生命周期也已接回：要求 player 存在且运行，同时读取输出采样率音频与 WeNet 特征，整个任务持有 `processing_lock`，懒构造并复用专用 `VideoFaceReader`，按 synthesizer batch size 取帧、合成和上传，短驱动视频会 rewind 循环至音频结束。`force_is_no_face` 在保留视音频注入的同时强制跳过口型合成。旧实现会篡改常规 reader/input mode、只塞一条 danmu 音频并立即返回，与原二进制明确的阻塞契约相反；现已删除。无模型回归已验证锁内完成、帧编号、物理帧编号、音频切片和 no-face 元数据。

`process_single_file` 包装器/主体 `0x180053620/0x1800539b0` 也已完成主体级校正。未传 `output_path` 时原函数返回内存视频帧列表，而非自动生成文件名；输出文件时以首帧尺寸、`self.fps`、`mp4v` 写入 `*_temp.mp4`，再用 FFmpeg 按 `0:v:0/1:a:0` 映射、视频 `copy`、音频 `aac` 合并。旧恢复版自创的 file-mode 限制、音频文件校验、预加载线程停启、25 FPS 常量和 libx264 重编码已移除。内存/文件两条分支的专项回归及全量 `128/128 PASS` 均通过；详细证据见 `rea-output/image-infer-v2-notes.md`。

`main.pyd` 的 IP-agent 家族开始进入主体级替换。首组五个基础方法已从持久 Ghidra 工程导出包装器和真实主体：项目根目录原生位于模块旁的 `assets/ip_agent_projects`，不是 `runtime_dir/ip_agent_projects`；默认项目主体 `0x1800ce8e0` 创建完整 47 字段协议，时间键为 `create_time/update_time`，并包含脚本分析、字幕、BGM、封面、发布平台/账号和一键生成状态。恢复版此前缺少近半字段，且自创了 `status`、`created_at` 和预设输出文件路径，现已纠正。

项目摘要主体 `0x1800cfac0` 也已恢复为原生六键结构：`id/name/create_time/update_time/preview_url/path`。空名称回退 `IP项目-<id>`，封面缺失时回退 `result/sample.jpg`，路径使用 `os.path.abspath`。目录、47 字段顺序与关键默认值、封面回退和摘要结构均有专项回归，全量验证继续 `128/128 PASS`。相邻 load/save/create/list 和媒体流水线主体已批量导出，仍需继续逐项对齐；证据见 `rea-output/main-ip-agent-notes.md`。

IP 智能体项目持久化主体 `_load_ip_agent_project`（`0x1800d0d90`）与 `_save_ip_agent_project`（`0x1800d3200`）已进一步校正。读取缺失目录或空 YAML 返回 `None`，成功读取会补入请求 ID、绝对目录、封面 data URL，并分别解析 result/subtitled/final 三种浏览器预览路径。保存不负责创建目录；目录缺失时抛出“IP项目不存在”，否则按“47 字段默认值 → 旧 YAML → 调用方数据”合并，强制 ID 与 `%Y-%m-%d %H:%M:%S` 格式的更新时间、补齐空创建时间、删除 `subtitle_debug_json_path`，写入后重新走加载富化链。公开 get/update/delete 的精确响应与错误前缀也已同步。缺失项目、合并优先级、默认字段补齐、瞬态键清理与预览路由专项测试通过，全量门禁保持 `128/128 PASS`；详细证据见 `rea-output/main-ip-agent-notes.md`。

IP 项目创建、列表与内联媒体链也已按主体恢复。`create_ip_agent_project`（`0x1800e0650`）去空白校验名称、生成 `uuid4().hex`、先以 `exist_ok=True` 建目录，再走默认记录和保存；`get_all_ip_agent_projects`（`0x1800e1d20`）创建根目录、忽略普通文件和空项目，并按 `update_time` 倒序。`get_ip_agent_media_data`（`0x1800e56a0`）删除旧恢复版自创的 runtime-root 路径限制，恢复 `file_path/data_url` 返回协议和三种原生错误。私有 `_encode_media_data` 主体 `0x1800ca3a0` 会检查存在性和 64 MiB 上限，再执行 MIME 推断与 Base64 Data URL 编码，异常返回空串；64 MiB 数值由常量初始化 `0x1801a28b6` 与 Api 类赋值 `0x1801a8b54` 联合确认。创建事务、排序、响应形状、MIME 回退和大小限制专项回归通过，全量验证继续为 `128/128 PASS`。

同组的 `get_ip_agent_creation_assets` 主体 `0x1800e42c0` 已恢复字幕样式枚举、`Microsoft YaHei` 字体回退、音乐列表 `limit=80`、原生 `fonts` 返回键及单一 `error` 失败结构。旧恢复版漏掉整个 `subtitle_styles`，键名和异常结构也不一致；成功/异常专项回归和全量门禁均已通过。

## 5. Mac 已完成与 Windows 边界

Mac 当前可以继续完成静态反编译、接口恢复、纯 Python 行为测试和协议测试。以下项目必须留到 Windows/NVIDIA 环境做最终验证：

1. `launcher_temp` 的 Win32 电源节流 API 与 `env/env_50` 实际切换。
2. CPython 3.10 Windows `.pyd` 的原生加载与 DLL 搜索顺序。
3. CUDA、TensorRT/ONNX、WeNet 和真实模型权重的端到端推理。
4. PyAudio/虚拟声卡、摄像头、窗口播放器、SRS/RTMP 推流。
5. pywebview 的 Windows WebView2 前端交互和安装/升级流程。

因此目前不需要立即换 Windows；当进入“真实模型启动并跑一条完整直播链”的阶段时，需要 Windows 10/11、NVIDIA 驱动以及与交付包匹配的 CUDA 运行环境。
