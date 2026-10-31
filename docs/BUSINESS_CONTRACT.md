# 本地业务扩展接口（v0.2）

所有路径均在 `/api/v1` 下，管理 Bearer 与现有 API 一致；返回 `{data:...}` / `{error:{code,message}}`。写入使用当前 `version` 乐观锁，恢复历史总是生成新版本。金额 `*_cents` 为整数分；费率 `*_cny_per_million` 为人民币元/百万 tokens，不预填供应商价格。

## 活动

- `GET /promotions?shop_id=UUID` → `Promotion[]`
- `POST /promotions`、`PUT /promotions/:id` → `Promotion`
- `GET /promotions/:id/history?shop_id=UUID` → `HistoryEntry[]`

`Promotion = {id,shop_id,product_id:string|null,title,description,offer_price_cents:number|null,starts_at:ISO,ends_at:ISO,active:boolean,version:number,updated_at:ISO}`。创建 version=0，修改 version>=1；product_id=null 表示全店活动；结束时间必须晚于开始。必须显式录入并启用；在当前商品/场次生成快照时仅纳入生效且未到期的活动，派发时再次核验，活动开始/到期也使旧稿失效。

## 人格与商品历史

- `GET /persona/history?shop_id=UUID` → `HistoryEntry[]`
- `POST /persona/restore` body `{shop_id,version:当前版本,target_version:历史版本}` → `Persona`
- `GET /products/:id/history?shop_id=UUID` → `HistoryEntry[]`
- `POST /products/:id/restore` body `{shop_id,version,target_version}` → `Product`

`HistoryEntry = {version:number,snapshot:object,recorded_at:ISO,deleted:boolean}`。恢复只恢复内容、创建新版本，不回退版本号。

## 知识与长期记忆

原 `/knowledge` 兼容；扩展 UI 使用下列完整接口：

- `GET /knowledge-records?shop_id=UUID` → `KnowledgeRecord[]`（包括删除记录，便于恢复）
- `POST /knowledge-records`、`PUT /knowledge-records/:id` → `KnowledgeRecord`
- `DELETE /knowledge-records/:id?shop_id=UUID&version=N` → `{deleted:true}`
- `GET /knowledge-records/:id/history?shop_id=UUID` → `HistoryEntry[]`
- `POST /knowledge-records/:id/restore` body `{shop_id,version,target_version}` → `KnowledgeRecord`

`KnowledgeRecord = {id,shop_id,title,content,kind:'faq'|'memory',source:string,scope:'shop'|'product'|'session',scope_id:string|null,expires_at:ISO|null,version:number,deleted_at:ISO|null,updated_at:ISO}`。scope=shop时scope_id=null；其他范围必须属于同店。source记录操作者核验的来源，不自动将用户评论变成长期事实。新增version=0，修改version>=1。过期、已删除或范围不符的记录不会进入模型上下文；记录到期也使含旧上下文的任务失效。

## 素材/音色/模型档案

- `GET /assets?shop_id=UUID` → `Asset[]`
- `POST /assets`、`PUT /assets/:id` → `Asset`
- `GET /assets/:id/history?shop_id=UUID` → `HistoryEntry[]`

`Asset = {id,shop_id,kind:'avatar'|'voice'|'model',name,identifier,sha256:string,model_version:string,authorized:boolean,active:boolean,version:number,updated_at:ISO,binding_status:'record_only'}`。sha256为64位小写hex；identifier是运维的本地资产标签，不作为远程请求可任意指定的文件路径。启用须确认授权，每店每种最多启用一条；启用新条目会使旧条目产生停用新版本。档案不会修改进程外的CosyVoice/LiveTalking配置，UI必须写明“记录待联调核对”，不能显示“已切换音色”。启用档案参与任务快照/缓存隔离，编辑后旧任务失效。

## 成本

- `GET /cost-settings?shop_id=UUID` → `CostSettings`
- `PUT /cost-settings` body `CostSettings` → `CostSettings`
- `GET /costs?shop_id=UUID&session_id=UUID(可选)` → `CostSummary`

`CostSettings = {shop_id,input_cny_per_million:number|null,output_cny_per_million:number|null,electricity_cny_per_kwh:number|null,device_watts:number|null,monthly_budget_cny:number|null,notes:string,version:number,updated_at:ISO}`。未设置时version=0，各费率null。无费率时成本null而非0。

`CostSummary = {shop_id,session_id:string,input_tokens,output_tokens,generated_jobs,usage_events,unknown_usage_events,estimated_ai_cny:number|null,estimated_power_cny_per_hour:number|null,currency:'CNY',basis:'operator_entered_rates',settings:CostSettings,note:string}`。统计任务成功返回的tokens，加独立usage事件；接入生成路径后使用usage事件去重。网络取消/超时未返回用量时必须记录unknown，不冒充未计费。电费为额定功率估算，非硬件实测。暂不包括税费、维修、人员与平台费用。

## 任务的业务快照

服务端 Snapshot 增加 `business = {fingerprint,promotions,assets,knowledge_refs,valid_until}`；Job 增加 `business_fingerprint`。知识引用只存id/version/有效期，活动保存版本与时间范围，素材保存版本与hash。时间边界/活动与素材编辑/记忆范围或有效期变更均在审核、合成、发送前核验。旧v0.1任务在迁移后必须重新生成和审核。

上下文先按范围、停用/删除状态和时间过滤，再施加1000条有效知识/活动上限；超过时显式拒绝生成，不截断后假装事实齐全。管理列表显示最近1000条，历史页显示最近1000版；大量历史档案需由运维另行归档。
