# v0.2 独立输出契约

本页冻结独立 OBS 浏览器源与后端的接口。它延用 MVP_CONTRACT 的 data/error envelope、UUID、UTC 时间和管理口令。独立输出仅报告浏览器接收状态，不证明 OBS 已采集、淘宝已接收或观众已听到。

## 权限与页面

- 管理 API 仍为 `/api/v1`，仅接受 `APP_TOKEN`。
- 独立页面 `/output#token=<output_token>`。仅随机 256 bit 的场次专用令牌进入 fragment，绝不把 APP_TOKEN 放入 URL。
- 输出页面从 fragment 读取令牌并在内存中使用；输出 API 仅接受 `Authorization: Bearer <output_token>`，不接受 query 令牌、APP_TOKEN 或 cookie。
- 服务端仅保存输出令牌 SHA256，原文只在 issue 成功响应中返回一次。issue 再次调用会轮换令牌，使旧链接失效；管理页刷新后若未保留链接，需要重新签发。
- 输出令牌仅能访问 `/output-api/v1/status`、`offer`、`heartbeat`、`release`，不能读取店铺、商品、任务、音频文件，也不能派发音频。
- 令牌不设固定时长，到撤销、再次签发或本地场次结束时失效。每个页面初始化时生成新的 UUID `receiver_id`，不得复用别的页面实例 ID。

## JSON 对象

```ts
type OutputConfig = {
  width:number; height:number; fit:'contain'|'cover'; background:string
}
// 默认1280×720、contain、#000000。宽高160..3840，background仅#RRGGBB。
// 这些值只控制浏览器输出画布，不改变模型的原生生成细节或帧率。
type OutputStatus = {
  session_id:string; enabled:boolean; generation:number;
  session_status:'active'|'paused'|'ended'; epoch:number;
  config:OutputConfig;
  state:'disabled'|'offline'|'negotiating'|'connected'|'paused'|'ended';
  online:boolean; peer_state:string; video_ready:boolean; audio_ready:boolean;
  last_heartbeat_at:string|null; lease_expires_at:string|null;
  lease_owned:boolean; lease_id:string|null;
  heartbeat_interval_ms:number; lease_ttl_ms:number
}
type OutputControlResult = {
  output:OutputStatus;
  media_stop_status:'sent'|'not_connected'|'failed'
}
type OutputIssueResult = OutputControlResult & {token:string; output_path:string}
```

`lease_id` 只有携带匹配本页 receiver_id 的输出端 status/offer/heartbeat 响应可见；管理页和其他页面实例只看到租约是否占用，不看到拥有者 ID。`online` 仅在有效租约、当前 epoch、最近 connected 心跳且视频/音频播放条件均满足时为 true。

## 管理 API（APP_TOKEN）

| 方法与路径 | 输入 | data |
| --- | --- | --- |
| GET /sessions/:id/output | query shop_id | OutputStatus；没有配置时返回未启用的默认对象 |
| PUT /sessions/:id/output | `{shop_id,width,height,fit,background}` | OutputStatus；保存配置，不签发令牌，不启用输出 |
| POST /sessions/:id/output/issue | `{shop_id}` | OutputIssueResult；启用或轮换，清理旧接收租约，并尝试停止旧媒体 |
| POST /sessions/:id/output/revoke | `{shop_id}` | OutputControlResult；立即撤销令牌、失效租约、暂停场次、epoch+1并取消旧任务，再尝试停止上游 |

issue 不自动恢复已暂停场次。revoke 的状态变化即使上游停止失败也要持久化，并显式返回 `failed`。重新使用管理预览需先撤销独立输出，再由操作者恢复场次和重新连接。

## 输出 API（output_token）

前缀 `/output-api/v1`，所有响应同样为 `{data:...}` 或 `{error:{code,message}}`。

| 方法与路径 | 输入 | data |
| --- | --- | --- |
| GET /status | query receiver_id（UUID，必填） | OutputStatus |
| POST /offer | `{receiver_id,sdp,type:'offer'}` | `{sdp,type:'answer',sessionid,lease_id,output:OutputStatus}` |
| POST /heartbeat | `{receiver_id,lease_id,peer_state,video_ready,audio_ready}` | OutputStatus |
| POST /release | `{receiver_id,lease_id}` | OutputControlResult |

`peer_state` 只能为 `new/connecting/connected/disconnected/failed/closed`。页面每 3 秒上报一次，必须读取实际 `RTCPeerConnection.connectionState`。`video_ready` 需视频轨道存活、video 有可播放帧；`audio_ready` 需音频轨道存活且实际媒体播放已成功、未被静音。自动播放被阻止必须上报 false，并显示本机播放失败，不能只因 peer connected 便称在线。

初次 offer 的租约最多保留 120 秒，用于后端协商及浏览器连接。只有 connected 且视频、音频就绪的心跳才把有效期续到 15 秒后。其他心跳可以报告状态，但不能无限延长未连接租约；过期租约不能通过迟到心跳复活。

已有未过期租约时，任何第二次 offer 都返回 409 `output_busy`，不会偷偷替换现有接收者。若 offer 响应丢失，本页可用自己的 receiver_id 查询 status，得到自己的 lease_id，release 后重新协商；其他页面不得获得该 lease_id。失败重连必须关闭旧 peer，使用退避，不能循环创建多个 peer。

## 生命周期和派发门槛

- 启用独立输出后，原管理预览 `/sessions/:id/media/offer` 返回 409 `output_managed`；最终绑定 SQL 也检查此条件，阻止已经在途的管理预览替换独立输出。
- 独立输出 offer 先持久化唯一租约，再访问 LiveTalking，返回后核验 generation、lease_id、receiver_id、epoch 与场次 active。迟到结果不得绑定，已知上游会话须尝试停止。
- 派发 `send` 在数据库事务中检查当前租约、当前 epoch、上游 sessionid 一致、未过期和 connected/ready 条件。HTTP offer 成功或旧 sessionid 存在均不足以允许派发。
- 接管使场次 paused、epoch+1、租约失效并停止上游；令牌仍可查询 paused 状态。输出页关闭 peer、显示黑底，等待管理端显式 resume；resume 后才能重新 offer。
- 本地场次结束会撤销输出令牌。输出页遇到 401 `output_unauthorized` 应立即关闭 peer、清除当前画面并停止重连；管理端仍能看到 ended 状态。
- release 仅释放自己匹配的租约，并尝试停止该上游，不能释放新页面或新一代令牌建立的租约。它不暂停业务场次、不撤销令牌。
- 服务重启保留配置和有效令牌，但清空所有在线/租约状态。旧页面的心跳返回冲突，必须关闭旧 peer 后重新协商；不能依靠数据库里旧的 sessionid 自动恢复“在线”。
- 接管、结束、撤销先在数据库作废状态，再在同一场次的派发锁下停止上游；恢复要等停止流程结束。上游停止失败不能被写成成功，已经进入 OBS/平台缓存的数据不承诺可以撤回。

常用错误码：401 `output_unauthorized`；409 `output_busy`、`output_managed`、`output_lease_invalid`、`output_offline`、`session_inactive`、`session_ended`；503 `media_not_configured`；502 `media_unavailable`。收到租约冲突时先关闭自己的旧 peer，查询状态；不得冒用别的 receiver_id。

## 本阶段验收边界

自动化验证令牌隔离、重启失效、第二接收者冲突、真实状态上报门槛、接管/撤销/在途 offer 竞态和派发门槛。真实 Windows/WSL、GPU、OBS 音频采集及淘宝接收端仍需目标机器逐项实测；模拟 HTTP 或模拟 peer 状态只能验证软件合同。
