# V04-01 前置接口核对与恢复版离线基线

V03人工听感、浏览器实录尚未验收，本记录是独立后续准备，不放行V03或V04整关。

## 缺陷与修复

恢复版`VideoSynthesizer.extract_audio_features`向本机WeNet `get_weget`传入权重路径字符串，但真实函数要求已经加载的PPG模型。新生成音频实测报`TypeError: 'str' object is not callable`，见本机`logs/validation/v04-contract/before.json`。

改为按配置/权重/设备首次加载PPG模型、后续请求复用；关闭时清理模型引用；明确拒绝关闭后提取和不符合20×256窗口要求的特征；ffprobe失败显式报错并限制30秒。保留公开参数和25fps离线窗口计算。未宣称此修改已经完成与原`.pyd`的完整差分。

真实CUDA特征提取：同一新音频两次得到84×20×256有限数值，复用同一个模型对象、特征一致，关闭后对象持有的模型引用清空。证据`logs/validation/v04-contract/after.json`；不把清空Python引用当作峰值显存/全部释放验收。

## 新音频到完整视频

新增可重复运行入口`python -m scripts.validate_recovered_avatar`，实际调用`recovered.image_clone_video_synthesizer.VideoSynthesizer`，不调用原生VideoSynthesizer。参数指定runtime-root、avatar-directory、audio、report-directory及backend；输出只写新UUID实验目录；原人物素材只读，输入音频SHA前后不变。

本机CUDA基线报告：`logs/validation/v04-restored/run-c7ace432be584890be31030f95e1f162/result.json`。

| 检查 | 实际结果 |
| --- | --- |
| 音频 | 来自V03本次新文本真实TTS，非既有演示配音 |
| 引擎 | 恢复版帧合成；session provider含CUDAExecutionProvider，21批/84帧实际推理 |
| 视频 | 720×1280，84帧，文件编码帧率25fps，时长3.36秒 |
| 音轨 | 3.328秒，与视频相差32ms；完整FFmpeg解码成功 |
| 耗时 | 初始化4.20秒，总计17.69秒，**不满足实时速度，不能宣称实时25fps** |
| 回归 | 配置随包FFmpeg路径后，恢复基线128/128 PASS，退出0 |

验证器的backend=tensorrt入口已提供但本次只运行CUDA。尚需人物制作/管理接入、FP32与FP16对照、至少50条验收语料、实际正常观看与嘴周/身份检查、模型预热/失败取消及25fps预算；V05连续音频驱动、输出接收端与同步另验。当前仍依赖授权原包中的WeNet代码和模型，独立打包/许可边界在V09处理，不是独立产品交付。
