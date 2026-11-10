# V03-03a 重建入口的真实常驻TTS

日期：2026-11-10。新增scripts/tts_worker.py：JSON行协议，输入通过stdin，模型诊断写stderr，自有输出目录写WAV。使用recovered.voice_infer_v3.VoiceSynthesizer派生OwnedSynthesizer，将缓存/临时音频置于本地数据目录，声音从VoiceStore校验指纹后读取；没有调用原voice_infer_v3.infer_api.pyd合成入口。

底层IndexTTS模型Python模块及权重目前仍由外部授权运行目录提供。此处证明自有包装/常驻协议实际驱动模型，不声称独立安装或全部引擎依赖已纳入仓库；依赖来源、使用条件及独立交付在后续打包关继续验证，不提交原商业包或模型。

## 真实执行

```powershell
python -X utf8 -m scripts.validate_recovered_tts --runtime-root D:/TEMP/v122-minimum-proof-ready/runtime/yunchuang_v122 --data-directory logs/validation/v03-voices --report-directory logs/validation/v03-recovered-tts
```

使用当前已导入且选中的14.19秒人声参考，生成两段带本次随机编号的新中文文本，use_cache=false。真实CUDA输出：

| 项目 | 第一句 | 第二句 |
| --- | --- | --- |
| 模型新加载 | 是 | 否 |
| 累计加载次数 | 1 | 1 |
| 初始化耗时 | 24.16秒 | 近0 |
| 合成及复制耗时 | 5.277秒 | 1.919秒 |
| 音频时长 | 4.821秒 | 5.376秒 |
| 采样率 | 24000Hz | 24000Hz |

两WAV哈希不同，真实FFmpeg完整解码均退出0；worker退出0。GPU总使用量运行前2383MiB，退出后2387MiB（同时有其他程序，非独占测量，不能以4MiB差值证明无泄漏）。未测峰值；单次短句不作为30分钟实时或容量证明。

报告result.json及worker.log位于本机logs/validation/v03-recovered-tts，音频位于自有data/tts目录；不提交音频/声音文本/运行包。1项真实子进程协议测试通过，3种无效请求均返回ok=false且无WAV，随后正常close退出；未用桩代码冒充推理。

## 边界与下一项

03a真实合成/实例复用/解码范围通过，音色听感与发音未验证，listening_verified=false。麦克风实录仍待用户在本机浏览器完成，已有参考音不替代该项。当前worker尚未接入产品话术快照、任务队列、取消和页面，不能直接作为直播服务；也未完成双人声切换、缓存失效、变速及异常后的资源验证。

下一项V03-03b：父进程任务管理、商品/选用稿/音色版本绑定与取消隔离，接入前保留原生参照和重建结果分开的证据链。
