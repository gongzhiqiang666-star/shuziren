# V03-01 常驻TTS与音色契约

2026-11-10核对：已有benchmark_v122_tts使用原bin.voice_infer_v3.infer_api.VoiceSynthesizer，from_voice_dir后复用实例，synthesize每句禁缓存，最终clear。该路径证明原生参照，不证明重建源码实际合成。现有runtime_bridge的speech-generate走短视频audio_synthesis且配置v2，不能直接当成常驻v3接入。

恢复版voice_infer_v3调用包内IndexTTS源码、infer_fast、锁、FP16、缓存及clear。模型源码当前来自外部授权运行目录；其依赖/使用条件/独立打包尚待确认，最终自有源码交付不能直接依赖原商业.pyd。

## 已修复的真实差分

from_voice_dir(模型目录,声音根目录,voice_id)恢复版此前直接resolve_reference(声音根目录)，忽略voice_id。用临时根目录诱饵和speaker-a/speaker-b子目录，对原生类和恢复类派生Probe，只覆盖构造函数捕获参考路径/文字，不加载模型。原生使用声音根目录/voice_id/ref_audio.wav及同目录文字，恢复版误读根目录。已改为Path(voice_base_dir)/voice_id。

修复后两音色路径/文字与原生一致，命令退出0；2项路径针对测试通过，含所选音色缺失时不回退根目录。探针仅验证classmethod的真实原生路径计算，构造和推理由捕获构造器替代，不证明音色质量/GPU。完整基线5组通过，128恢复模块及23工具测试保持通过，日志logs/validation/v03-reference-baseline。

本机资源只记录数量：声音目录1个，含ref_audio.wav及ref_text.txt；IndexTTS模型config、原生API及引擎Python源码存在。不打印声音名称、文本或原始音频，不提交模型/素材。第二音色真实切换仍需新增可授权参考音，不能用本次两个路径探针充当音色听感通过。

## 后续任务

| 编号 | 工作 | 必需验证 |
| --- | --- | --- |
| V03-01 | 现有路径核对与差分修复 | 本记录、两个原生路径对照、针对测试及恢复回归；通过 |
| V03-02 | 独立音色目录、导入/制作与选择 | 不改原包；真实音频规范化与文字配对，路径边界、无效媒体/缺参考、重开和选用不串音色 |
| V03-03 | 自有常驻TTS worker | 复用实例、按声音/引擎身份切换，生成用当前已选话术版本，取消/退出/迟到隔离；原生参照与重建路径分开 |
| V03-04 | 缓存、速度、失败及资源 | 缓存键含文本、声音/参考内容、语言、速度、引擎；禁缓存新文本、参考替换失效、异常恢复/取消释放 |
| V03-05 | 页面及真实放行 | 两参考音真实新文本，完整解码、播放听感、音色正确，修改后新请求不污染，重开/退出；缺项不放行V04 |

MED-007退回开发中，完整矩阵保持58项；局部路径修复不能作为整个IndexTTS能力完成。

## V03-05 双参考切换与录音卡点（2026-11-10）

已增加 `scripts/validate_tts_voice_switch.py`：独立导入两份本机参考音，以相同新文本进行 A/B/A 三次禁缓存真实 GPU 推理；单次实验180秒超时，关闭仅回收自己启动的 worker。修复切换参考音重复加载整套模型的问题，利用 IndexTTS 按参考路径更新条件缓存。验证模型加载次数始终1、切换计数0/1/2、推理次数1/2/3、各输出所绑定音色ID正确，三份WAV全部FFmpeg完整解码，worker退出0。

本机报告：`logs/validation/v03-voice-switch/run-1e80bb50365d49c4a63d9dcedb00a7a7/result.json`。这证明参考切换和模型复用链路；两份原文件不同不等于两位说话人，不宣称音色相似度或听感通过。音频/模型不提交。

录音诊断已收敛：Realtek物理输入的PortAudio callback采集2秒成功，但样本全零（RMS=0）；此前16k不支持及WDM-KS阻塞API不支持已分别定位，不继续重复相同尝试。证据 `logs/validation/v03-quality/physical-callback-probe.json`。这不能把静音当作可用音色；物理麦克风真人实录、音色听感/身份核验仍是明确未通过项。浏览器交互链后来已由文末受控虚拟麦克风补验，两种证据范围不得混淆。

执行约束：同一失败路径没有新证据时停止重复，及时报告“任务编号、具体错误、影响范围、替代路径”；不让单个设备问题阻止独立开发，也不跳过阶段验收发布。

## V03-05 内容与参考匹配自动核验

新增 `scripts/validate_tts_quality.py`，使用已有本地Paraformer和CAMPPlus权重，不下载、不传送录音。测试前固定内容CER不超过0.15、目标参考余弦相似度比另一参考至少高0.05；参考互相余弦大于等于0.8时不作可区分双音色放行。这些指标仅为自动回归，不替代人工听感/身份检查。

- 原两包参考的CAMPPlus余弦0.999947，不能作为不同人声验证。原三段生成ASR转写均准确，但参考匹配整体不通过；保留失败报告 `logs/validation/v03-voice-switch/run-1e80bb50365d49c4a63d9dcedb00a7a7/quality-result.json`。
- 改用本机CAMPPlus模型自带speaker2人声样例作为第二参考，仅限本机实验；配对文本为本地ASR结果，未经人工校订，媒体不提交。两参考余弦0.08279；A/B/A三次禁缓存推理、完整解码、单次模型加载通过。三段识别CER均0，目标参考余弦0.633/0.636/0.647，相对另一参考优势0.541/0.656/0.605。
- 通过报告：`logs/validation/v03-distinct-reference/run-c5eb1753014b4a20a22afad284dc6d1f/result.json`及`quality-result.json`。未声称真实身份认证、所有语料质量或人工听感通过。
- 本地FunASR 1.2.3在当前权重的句级时间戳路径因缺失timestamp报错；本次仅需内容转写，显式关闭sentence_timestamp后成功。未来字幕/对齐接入仍需单独处理这一缺口，不能认为带时间戳ASR已经通过。
## 浏览器录音制作补验（2026-11-14）

`scripts/validate_microphone_ui.py` 使用 Chrome 受控虚拟麦克风真实执行页面的 `getUserMedia`、`MediaRecorder`、停止、试听状态和“保存录音为音色”，随后由随包 FFmpeg 走正式导入接口。`logs/validation/v03-microphone-ui-04/result.json` 记录通过：保存后自动选中，授权类型为 `self_recorded`，受管 WAV 为单声道 PCM16/24 kHz、1.8 秒，页面截图为同目录 `microphone-saved.png`。

该证据关闭浏览器录音交互、权限、Blob 上传和规范化链路缺口。输入是可重复的虚拟音频夹具，不代表物理麦克风、真人语音清晰度或克隆听感；本机当前无物理麦克风，真人录音和第二人声主观听审继续保留。
