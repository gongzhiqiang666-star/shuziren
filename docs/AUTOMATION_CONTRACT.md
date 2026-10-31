# 本地调度、生成限额与语音缓存契约

本页补充 v0.2 接口。全部接口在 `/api/v1`，仅管理 APP_TOKEN 可访问。它们提供本地可测试的控制，不代表 GPU、OBS、淘宝或供应商账单已经完成实测。

## DeepSeek 限额和用量

```ts
type GenerationLimits = {
  shop_id:string; requests_per_minute:number; daily_request_limit:number;
  daily_token_limit:number; version:number; updated_at:string;
  global_max_concurrent:1; request_reservation_tokens:100000
}
type GenerationUsage = {
  limits:GenerationLimits; date_utc:string; requests_today:number;
  charged_tokens_today:number; unknown_requests_today:number;
  pending_requests_today:number; enforcement:string
}
```

| 方法与路径 | 输入 | data |
| --- | --- | --- |
| GET /generation/limits | query shop_id | GenerationLimits |
| PUT /generation/limits | `{shop_id,requests_per_minute,daily_request_limit,daily_token_limit,version}` | GenerationLimits |
| GET /generation/usage | query shop_id | GenerationUsage |

默认每店每分钟10次，日请求和日token限制为0（不设该项上限）；全局最多一个生成流程在途，不排队积压旧问题。requests_per_minute为1..60，日请求0..100000，日token 0..1000000000。首次配置 version=0，之后带当前版本。额度按UTC自然日计算。

生成先完成本地检索和上下文校验，再记账和请求DeepSeek。请求内容限定64KiB以内，max_tokens=4096，每次调用前保守预留100000 token；余额不足则拒绝，不发送请求。这是本地限额规则，不能当作精确分词数量或人民币账单上限。

收到可信 prompt_tokens/completion_tokens 后按实际用量结算，包括模型返回无效回答或草稿因版本改变无法保存的情况。无usage、取消、响应不明、重启中的请求保留全部预留，不能当免费请求自动释放。限额冲突返回429 `generation_rate_limited` / `generation_budget_exceeded`，全局并发冲突返回409 `generation_busy`。BGE或本地检索先失败的情况不会创建远程用量记录。

## 任务优先级和截止时间

Job 增加 `priority:number`（0..100，默认50）与 `expires_at:string|null`。截止时间与商品有效期、商品/人格/知识/活动/素材版本以及epoch一起校验。更高priority先领取本地TTS，当前正在合成的任务不被低成本假设下强行抢占。

`PUT /jobs/:id/dispatch-policy` 输入 `{shop_id,priority,expires_at}`，返回 Job。仅未发送且未取消的有效任务可设置；截止时间应在未来。已经过期的任务不能通过延后截止时间复活，应重新生成与审批。改变优先级不会绕过人工审核。

## 单次定时派发

```ts
type SpeechSchedule = {
  id:string; shop_id:string; session_id:string; job_id:string;
  run_at:string; expires_at:string;
  status:'scheduled'|'dispatching'|'sent'|'failed'|'cancelled'|'delivery_unknown';
  reason:string; error_code:string; created_at:string; updated_at:string
}
```

| 方法与路径 | 输入 | data |
| --- | --- | --- |
| POST /jobs/:id/schedule | `{shop_id,run_at,expires_at}` | SpeechSchedule |
| GET /schedules | query shop_id，可选session_id | SpeechSchedule[]，最近100条 |
| POST /schedules/:id/cancel | `{shop_id}` | SpeechSchedule |

run_at需在未来、最多7天；expires_at需晚于run_at、最多晚1小时，前端建议run_at后60秒。只接受已审核的 approved/queued/synthesizing/ready 任务；批准后尚未合成的任务会进入持久TTS队列，同一任务只能有一个未结束的定时任务。

任务尚未ready且本地TTS未配置时，创建计划返回503 `tts_not_configured`，不保存计划；不能把无法合成的任务伪装成已安排。

到期后只向在线、音视频就绪且租约有效的**独立输出页面**派发。资料和epoch重新检查；音频未就绪时等待到expires_at，之后失败。接收页离线、资料过时或发送失败不自动重试；需要操作者检查后重新安排。`sent`仍仅表示上游接受。

接管/结束/撤销取消尚未派发的计划，派发中的结果保守记录为不明。取消单条尚未派发计划不删除已审核草稿或音频；已经dispatching/sent/delivery_unknown的计划必须用场次接管处理。

重启后：未来的scheduled保留；已经错过run_at的scheduled标为failed，不突然补播；dispatching标为delivery_unknown，不重发。与业务版本、epoch或任务截止时间冲突的计划不得继续派发。

## 语音缓存

同一job的持久WAV直接用于预听和发送。Job另外返回`audio_engine_id`（未核验时为空）。生产媒体客户端必须从TTS健康接口获得真实engine_id；健康检查失败时停止合成/派发，不静默降级。跨job缓存key包含实际engine_id、精确文本、店铺、商品/人格/知识版本与业务指纹。缓存有SHA256完整性校验、条目/磁盘上限；读取前和合成后复核真实身份，身份改变或无法确认时丢弃结果，不能成为ready。

成功合成把实际engine_id持久化到job，派发前再次核对。已经ready的音频若遇到当前引擎不同或未核验，拒绝派发，需恢复原引擎或重新创建并审核任务。只有明确未实现身份接口的测试adapter允许未核验路径，且始终禁止跨job缓存；主程序的真实media.Client不走此路径。

缓存不复用派发状态、不免除审批和版本/租约校验，也不宣称“素材台账已切换实际模型”。缓存坏掉或不可用时回到真实本地合成，不制造音频或调用其他付费厂商。
