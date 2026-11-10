# RTX 3060 实时生成性能验证

本页记录 2026-11-10 在 Windows、i5-12490F（6核12线程）、RTX 3060 12GB、驱动621.14上的实测。使用授权 v122 运行包原生模块、原人物资源、原WAV及原UNet模型，不提交运行包、模型或人物素材。

## 已验证的优化

- UNet CUDA 使用 HEURISTIC 卷积算法选择及4GB arena限制，避免默认算法搜索占满显存及过长冷启动。
- 可选 TensorRT FP16、2GB workspace和本机引擎缓存；加载失败明确报错，不把CUDA/CPU回退记为TensorRT通过。
- 复用常驻模型和预处理人物；实时入口采用原 `FrameSynthesizer`，4帧一批。
- 通过有界队列解耦合成和25fps逐帧输出；8帧预填充代表320ms画面缓冲，非全部互动延迟。
- Windows输出线程请求1ms计时精度，退出时释放。
- 本次进程补齐随包FFmpeg、CUDA11.8、TensorRT8.6 DLL路径；不修改安装的第三方库或原`.pyd`。
- TTS使用原 `VoiceSynthesizer` 常驻实例，逐句禁用缓存，结束后调用原`clear()`释放。

## 第一组实测

| 测试 | 实测 | 解释 |
|---|---|---|
| 原CUDA短片基线，50帧 | 57.67秒，其中ORT54.00秒、读帧0.19秒 | 当时另有v179程序占用CUDA，不能作独占速度对照 |
| CUDA HEURISTIC，50帧 | 首轮7.35秒，后两轮5.67/5.64秒 | 约8.8fps，仍未达到实时 |
| TensorRT FP16，50帧 | 引擎构建后两轮1.79/1.83秒 | 约27.4–27.9fps；首轮含引擎构建不能当热态速度 |
| 实时合成+NVENC，60秒 | 1500帧；总输出59.96秒；容量约37.53fps | 25fps定时输出，批次超时0，完整解码通过 |
| 实时合成+NVENC并行独立TTS，120秒 | 3000帧；输出119.97秒；容量约37.95fps | 无缓冲时4批次超时，最大78.46ms；未将新TTS音频切入输出流 |
| 独立常驻TTS，3段不同话术 | 3.09/2.93/2.82秒生成7.04/7.89/7.68秒 | RTF约0.44/0.37/0.37，三份WAV哈希不同 |
| 8帧缓冲+1ms计时+并行常驻TTS，120秒 | 3000帧，输出119.96秒，合成/读帧容量38.25fps | 队列饿帧0、编码单帧预算超时0；6帧调度迟到超过5ms，最大24.43ms，P95为1.15ms；完整解码通过 |
| 同时工作的常驻TTS，3段新话术 | 6.12/5.32/4.85秒生成8.58/8.70/8.15秒 | RTF0.71/0.61/0.60，独立进程并行，未将这些新语音动态切入画面流 |
| 完整173帧离线MP4加速入口 | 缓存就绪后总耗时22.26秒，其中初始化13.48秒、文件生成8.75秒 | 与实时入口不同；一次性进程仍有初始化成本，不能宣称离线文件生成恒为38fps |

最后一轮缓冲并行测试采样显存最高5327MiB，非连续峰值。首批合成约107ms，真实8帧预填充约212ms；这些数字不含新话术TTS、在线分块Wenet及网络延迟。TTS并行冷启动约8.56秒，开播前必须预热。原始证据：`buffered-persistent-120s/result.json`、`buffered-persistent-120s/tts/result.json`、`buffered-persistent-120s/mixed-control.json`及`optimized-full-cached.result.json`。

**判断：这台机器具备单路720×1280/25fps实时人物合成、NVENC编码并行语音合成的算力条件。完整直播仍待队列接入、虚拟摄像头/OBS/平台和长时间验收。** 当前网页的一键离线流程没有被改成生产直播流程。

FP16与CUDA同段输出SSIM：全画面0.999747；固定面部区域0.997055。它们是编码后两秒短片对照，不能替代人物、音色、口型和闪烁的人工验收。原TensorRT日志提示小权重的FP16下溢，保留该兼容风险。

## 复测命令

使用随包CPython3.10，不要使用系统Python。先在原程序中暂停其他GPU生成任务，不要广泛结束python进程。`$cache`应仅用于相同GPU、模型和ORT/TRT版本；更换这些条件时选择新缓存目录。首次构建以及遇到新batch形状时会额外构建引擎，必须在开播前完成预热。

```powershell
$bundle = 'D:\TEMP\v122-minimum-proof-ready'
$runtime = "$bundle\runtime\yunchuang_v122"
$python = "$runtime\_internal\env\python.exe"
$cache = "$bundle\reports\speed\trt-cache"
& $python D:\TEMP\shuziren\scripts\benchmark_v122_realtime.py --runtime-root $runtime --person-id minimum-proof-20261110b --audio "$bundle\recordings\minimum-selected\generated.wav" --output "$bundle\reports\speed\repeat-buffered" --cache $cache --seconds 120 --buffer-frames 8
```

工具输出真实合成+NVENC MP4、完整ffprobe、完整解码检查和`result.json`。`capacity_scope`说明容量数字的计时范围，`buffered_playback`记录实际播放端迟到和队列饥饿，`initialization_including_features_seconds`单列启动及音频特征准备。

并行复测时，可在画面测试开始输出帧后，在另一个控制台执行下面的常驻TTS命令。本机记录使用控制器在第204帧附近启动该命令，并保存两个进程的日志、退出码及时间线。两个进程必须共用同一张GPU，不能将独立测得的RTF标为并行结果。

```powershell
& $python D:\TEMP\shuziren\scripts\benchmark_v122_tts.py --runtime-root $runtime --voice-id minimum-proof-20261110 --output "$bundle\reports\speed\repeat-tts"
& $python D:\TEMP\shuziren\scripts\generate_v122_fast.py --runtime-root $runtime --person-id minimum-proof-20261110b --audio "$bundle\recordings\minimum-selected\generated.wav" --output "$bundle\reports\speed\new-fast-output.mp4" --cache $cache
```

`generate_v122_fast.py`要求新输出路径。现有网页默认编排未被悄悄改动，加速需要显式使用新入口；FP32可用`--backend cuda`复查。

## 证据与边界

原始证据只在本机`D:\TEMP\v122-minimum-proof-ready\reports\speed`：`baseline-profile.json`、`heuristic-profile.json`、`tensorrt-profile.json`、`live-60s/result.json`、`mixed-120s/result.json`、各测试的`mixed-control.json`、`persistent-tts/result.json`、SSIM日志及录像。

测试中的音频和Wenet特征在计时前准备；使用授权真实素材重复构成压力音频，不是麦克风实时输入测试。并行TTS测试测算力争用，未验证新语音切换时的队列、打断与音画衔接。单次短时通过不等于长时间生产稳定性。

尚未验收：新TTS持续补队列并驱动人物、在线分块Wenet输入延迟、虚拟摄像头/OBS实际取流、平台推流及多小时稳定性。这些项目保留，不能凭MP4或平均FPS标记整个实时直播端到端通过。
