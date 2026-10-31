# v0.1 本地工作台实现契约

本文件用于前后端和媒体适配并行开发；实际完成与验证结果见交付记录。v0.1 是单操作者、本地运行的可用开发版，不宣称淘宝自动评论、客户GPU或实际直播已经通过验收。完整产品范围仍以 DEVELOPMENT_PLAN.md 为准。

## 目标

- Go/Gin + PostgreSQL 持久化，Vue 3 + TypeScript 本地界面。
- 店铺与商品、人格配置、FAQ/人工维护记忆、场次、DeepSeek草稿、人工审核、持久化语音队列、LiveTalking预览/音频发送/接管。
- 商品和人格版本改变后，旧草稿/音频不得继续审批或派发；接管通过epoch隔离迟到结果。
- 画质参数与验收记录进入工作台，不把人工勾选当自动测量。
- v0.1 检索先采用明确标识的关键词检索。BGE向量检索与淘宝正式授权连接后续接入，不能标成已完成。
- 未配置 DeepSeek/TTS/LiveTalking 时返回明确的不可用状态，不能自动使用伪造回复或其他付费厂商。

## HTTP 约定

API前缀 `/api/v1`。成功 `{ "data": T }`，错误 `{ "error": { "code": "...", "message": "中文说明" } }`。资源ID使用UUID字符串；时间为RFC3339 UTC；金额用整数分。

`GET /healthz` 只返回存活状态，不暴露配置。所有 `/api/v1/*` 必须提供 `Authorization: Bearer <APP_TOKEN>`。口令由环境变量提供，最少24字符，缺少时服务拒绝启动；前端只在当前页面内存中保存口令，刷新后重新输入。浏览器同源请求，开发由Vite代理，不启用宽泛CORS。服务默认只监听127.0.0.1；Docker内部监听0.0.0.0但仅映射宿主机127.0.0.1。

## 数据对象

```ts
type Shop = { id:string; name:string; created_at:string }
type Product = {
  id:string; shop_id:string; title:string; sku:string; description:string;
  specs:string; price_cents:number; stock:number; active:boolean;
  version:number; expires_at:string|null; updated_at:string
}
type Persona = { shop_id:string; name:string; tone:string; prompt:string; version:number; updated_at:string }
type Knowledge = { id:string; shop_id:string; title:string; content:string; kind:'faq'|'memory'; updated_at:string }
type Session = {
  id:string; shop_id:string; title:string; status:'active'|'paused'|'ended';
  epoch:number; media_session_id:string|null; created_at:string; updated_at:string
}
type JobStatus = 'draft'|'blocked'|'approved'|'queued'|'synthesizing'|'ready'|'sending'|'sent'|'cancelled'|'failed'|'delivery_unknown'
type Job = {
  id:string; shop_id:string; session_id:string; product_id:string;
  product_version:number; persona_version:number; epoch:number;
  source:'manual'|'deepseek'; question:string; text:string; status:JobStatus;
  reason:string; error_code:string; input_tokens:number; output_tokens:number;
  created_at:string; updated_at:string
}
type QualityProfile = {
  shop_id:string; avatar_name:string; source_resolution:string;
  model_version:string; canvas_resolution:string; fps:number;
  sync_target_ms:number; notes:string;
  checks: { key:string; label:string; passed:boolean; notes:string }[];
  updated_at:string
}
```

所有店铺资源均检查 `shop_id` 与对象归属。此版本是一个本地操作者管理多店配置，不声称已实现多用户权限系统。

## API 路由

| 方法与路径 | 输入 | data |
| --- | --- | --- |
| GET /status | 无 | `{version,storage,deepseek:{configured,model},media:{tts_configured,live_configured},taobao:{status},retrieval:{mode}}` |
| GET /shops | 无 | Shop[] |
| POST /shops | `{name}` | Shop |
| GET /products | query shop_id | Product[] |
| POST /products | Product可编辑字段及shop_id，不含id/version/updated_at | Product |
| PUT /products/:id | 同新增，附version作为乐观锁 | Product |
| GET /persona | query shop_id | Persona |
| PUT /persona | `{shop_id,name,tone,prompt,version}` | Persona |
| GET /knowledge | query shop_id | Knowledge[] |
| POST /knowledge | `{shop_id,title,content,kind}` | Knowledge |
| PUT /knowledge/:id | 同新增 | Knowledge |
| DELETE /knowledge/:id | query shop_id | `{deleted:true}` |
| GET /sessions | query shop_id | Session[] |
| POST /sessions | `{shop_id,title}` | Session |
| POST /sessions/:id/takeover | `{shop_id}` | `{session:Session,media_stop_status:'sent'|'not_connected'|'failed'}` |
| POST /sessions/:id/resume | `{shop_id}` | Session |
| POST /sessions/:id/end | `{shop_id}` | `{session:Session,media_stop_status:'sent'|'not_connected'|'failed'}`；仅结束本地场次，不结束淘宝直播；媒体停止失败必须提示 |
| POST /sessions/:id/media/offer | `{shop_id,sdp,type}` | `{sdp,type,sessionid}`；校验并记录上游会话 |
| GET /jobs | query shop_id，可选session_id | Job[]，最近100条 |
| POST /jobs/manual | `{shop_id,session_id,product_id,text}` | draft Job |
| POST /jobs/generate | `{shop_id,session_id,product_id,question}` | draft或blocked Job |
| POST /jobs/:id/approve | `{shop_id}` | approved Job |
| POST /jobs/:id/synthesize | `{shop_id}` | queued Job，后台串行合成 |
| POST /jobs/:id/send | `{shop_id}` | sent Job；只证明上游接收，不证明实际播出 |
| POST /jobs/:id/cancel | `{shop_id}` | Job；已派发任务需场次接管处理 |
| GET /jobs/:id/audio | query shop_id | 受认证保护的audio/wav二进制，前端fetch后生成Blob URL |
| GET /quality | query shop_id | QualityProfile（缺省返回未通过的默认档案） |
| PUT /quality | QualityProfile可编辑字段及shop_id | QualityProfile |

## 核心行为

所有新回复都必须经人工审核；DeepSeek JSON输出 `{answer:string,needs_human:boolean,reason:string}` 经严格解析，不接受空白/截断/额外尾随内容；无法回答时blocked。提示词使用商品事实、有限FAQ/记忆与人格；用户问题不能提升为系统指令。不得宣称自然语言草稿已被自动证明事实无误，界面显示事实来源供审核。

订单个人信息、平台凭据和整个数据库不发给模型。只发送操作者在本工作台录入且选择用于回答的必要商品和知识内容。模型Key仅后端环境变量保存。HTTP错误输出不得泄露上游响应中的Key或请求正文。

生成前快照shop/session/epoch/product_version/persona_version；完成后重新核验。审批、合成领取、合成写回、音频派发均重新检查有效期、当前版本和场次状态。过时返回409并禁止下一步。

语音任务持久化；单个后端实例串行消费，运行时采用数据库级独占工作锁或明确单实例约束，避免同一队列重复执行。服务重启将遗留synthesizing标为failed，将遗留sending标为delivery_unknown，不自动重播。不要将上游HTTP200记为观众已听到。

takeover先在数据库中增加epoch、暂停场次并取消未发送任务，随后停止对应上游媒体。发送与停止需要同一会话的派发互斥，保证迟到派发不会在停止之后重新进入媒体队列。对外发送超时或结果不明确时delivery_unknown，禁止无脑重试。

## 环境变量与媒体模块契约

后端：`APP_ADDR`、`APP_TOKEN`、`DATABASE_URL`、`WEB_DIST`、`AUDIO_DIR`、`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`（默认https://api.deepseek.com）、`DEEPSEEK_MODEL`（默认deepseek-flash）、`TTS_BASE_URL`、`TTS_API_KEY`、`LIVETALKING_BASE_URL`。

Go module `github.com/gongzhiqiang666-star/shuziren/server`。

媒体适配包固定路径 `server/internal/media`，对业务层提供：

```go
type Config struct { TTSBaseURL, TTSAPIKey, LiveTalkingBaseURL string }
type Offer struct { SDP string `json:"sdp"`; Type string `json:"type"` }
type Answer struct { SDP string `json:"sdp"`; Type string `json:"type"`; SessionID string `json:"sessionid"` }
func New(Config) (*Client, error)
func (*Client) TTSConfigured() bool
func (*Client) LiveConfigured() bool
func (*Client) Synthesize(context.Context, string) ([]byte, error) // 校验WAV及大小；音色由本地服务固定
func (*Client) Negotiate(context.Context, Offer) (Answer, error)
func (*Client) SendAudio(context.Context, string, []byte) error
func (*Client) Interrupt(context.Context, string) error
```

本项目的CosyVoice包装服务由 `workers/tts` 提供，`POST /synthesize {text}` 返回WAV，`GET /healthz` 返回是否加载；Bearer认证，模型缺失返回503，不生成模拟声音。提示音频仅通过服务器配置的固定路径加载，HTTP请求不可指定任意磁盘路径。

LiveTalking适配必须核验官方 `/offer`、音频上传和打断接口的实际合同。不得假造上游播放完成回调。Python服务与GPU媒体环境独立安装。
