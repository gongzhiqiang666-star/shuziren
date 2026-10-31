# 本地媒体适配

本包只负责真实 HTTP 媒体调用。场次锁、任务审批、版本检查、epoch 与数据库状态由业务层负责；`SendAudio` 成功只表示上游接收，不能写成“已播完”。

## 已核验的上游合同

核验日期：2026-10-31。LiveTalking 源码版本固定为 `c7269433a2b6ecebcd9342445d2ecc882c98b0da`。以下接口已经按官方文档和源码核对；尚未在客户 GPU 上运行该版本。

| 调用 | 请求 | 验证成功的条件 |
| --- | --- | --- |
| TTS `/synthesize` | JSON `{text}`，仅向 TTS 发送 Bearer token | HTTP 200，WAV Content-Type，有界且结构有效的单声道 PCM16 WAV |
| LiveTalking `/offer` | JSON `{sdp,type:"offer"}` | HTTP 200，JSON 中 `type:"answer"`、有效 SDP、非空字符串 `sessionid` |
| LiveTalking `/humanaudio` | multipart：文本字段 `sessionid`，音频字段 `file`，文件名 `speech.wav` | HTTP 200，JSON 中明确存在整数 `code:0` |
| LiveTalking `/interrupt_talk` | JSON `{sessionid}`，字符串会话 ID | HTTP 200，JSON 中明确存在整数 `code:0` |

当前官方 `session_manager` 用 UUID 字符串创建会话。数值 JSON 会话 ID 会被拒绝；本版本不声称兼容旧的数字会话协议。业务层应保存 `/offer` 返回的原始字符串，上传和接管时使用相同值。

官方来源：

- [API 文档](https://github.com/lipku/LiveTalking/blob/c7269433a2b6ecebcd9342445d2ecc882c98b0da/docs/api.md)
- [routes.py：humanaudio、interrupt_talk、json_ok](https://github.com/lipku/LiveTalking/blob/c7269433a2b6ecebcd9342445d2ecc882c98b0da/server/routes.py)
- [rtc_manager.py：handle_offer](https://github.com/lipku/LiveTalking/blob/c7269433a2b6ecebcd9342445d2ecc882c98b0da/server/rtc_manager.py)
- [session_manager.py：字符串会话](https://github.com/lipku/LiveTalking/blob/c7269433a2b6ecebcd9342445d2ecc882c98b0da/server/session_manager.py)

源码中的音频上传将文件字节交给 `put_audio_file`；打断调用 `flush_talk`。本包不调用 `/human`，因此不会让 LiveTalking 用其他 TTS 再合成一次。口型与播放使用工作台已审核的同一份 WAV；上游如需重采样，由这一份音频派生。

## 配置与错误

`Config{}` 合法，表示两个媒体服务均未配置。单独配置 LiveTalking 也合法。TTS URL 和 API key 必须一起提供；key 使用 24–512 位 ASCII Bearer 字符，推荐随机生成至少 32 字节。URL 仅允许 HTTP/HTTPS；禁止内嵌账号密码、查询串、fragment 和路径穿越。可设置固定的反向代理路径前缀。

所有请求拒绝重定向，不自动使用进程级 HTTP 代理，不把 TTS token 发给 LiveTalking。上游错误正文和网络错误原文不返回给业务层，避免泄露文本、密钥或内部 URL。LiveTalking 官方接口没有本项目的 Bearer 保护，部署时只让它在受控本机或内部网络访问。

可用 `errors.Is` 识别：`ErrNotConfigured`、`ErrInvalidConfig`、`ErrInvalidInput`、`ErrUpstream`、`ErrInvalidResponse`、`ErrSessionNotFound`。最后一种仅用于打断接口：HTTP 200 且合法 JSON 精确包含整数 `code:-1` 和 `msg:"session not found"` 时，表示官方源码明确报告该上游会话不存在，业务层可允许重建预览。HTTP 404、超时、未知非零码、相似错误文本均不能按不存在处理；上传接口仍将非零码视为发送失败。它不代表平台已缓存的声音停止。调用方的 `context.Canceled` 和 `context.DeadlineExceeded` 保持可识别。配置状态仅代表已提供配置，不代表模型已加载或上游在线。

单次文本最多 2,000 Unicode 字符；WAV 限 32 MiB、300 秒、单声道 PCM16、8–48 kHz。校验 RIFF 长度、fmt/data 块、帧大小、采样率和字节率，拒绝截断、溢出及重复音频块。合成 180 秒、协商 90 秒、上传 30 秒、打断 10 秒的上限均可被调用方更短的 context deadline 覆盖。

对已出站的上传，取消、超时、无效响应或错误响应都可能无法证明音频完全未入队。业务层应保守标记 `delivery_unknown` 并禁止自动重播。`Interrupt` 成功只证明上游执行了停止请求，不能撤回 WebRTC、OBS 或平台已有的缓冲。

## 验证

在 `server` 目录运行 `go test -race ./internal/media`。测试使用 `httptest` 本机服务器核对 multipart 文件与原 WAV 字节一致、UUID 协商/JSON 打断、缺配置、错误/畸形响应、大小限制、请求取消和超时，以及重定向不泄露任何请求。测试不代替真实 LiveTalking、MuseTalk、GPU 或淘宝端验证。
