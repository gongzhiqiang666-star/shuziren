# 本地检索与淘宝适配接口（v0.2）

所有接口在 `/api/v1`，仅管理 Bearer 可访问。返回标准 `{data:...}`。外部账号秘密只通过服务器环境配置，不从浏览器上传、不回显。

## 诊断与检索

- `GET /diagnostics` → `{checked_at,checks:[{name,status:'ok'|'unconfigured'|'failed',detail}],note}`，只检查本地服务、数据库和配置，不能证明淘宝已播。
- `POST /retrieval/search` body `{shop_id,session_id,product_id,question}` → `{mode:'keyword'|'bge',matches:[{id,title,content,kind}],note}`，使用与生成相同的范围/有效期过滤。未配置模型为明确关键词模式；配置 BGE 后不可用则报错，不偷偷返回关键词结果。
- `GET /integrations/status` → `{taobao:{configured,shop_id,transport:'top_http_poll',polling,last_poll_at,last_success_at,last_error_code},retrieval:{mode,configured,model}}`。轮询默认关闭，环境 `TAOBAO_POLL_ENABLED=1` 才启动；外部状态无成功证据前不显示已连接。

## 淘宝绑定与事件

- `GET /taobao/rooms?shop_id=UUID` → `Room[]`
- `PUT /taobao/rooms` body `{shop_id,session_id,live_id}` → `Room`；同一个 live_id 只绑定一个本地场次。绑定不表示账号已获平台权限。
- `GET /taobao/events?shop_id=UUID&session_id=UUID(可选)` → `Event[]`（最近100条）
- `POST /taobao/events/replay` body `{shop_id,session_id,message_id,content:{anchorId?,liveId,uniqueCode?,comment,userId?,userNick?}}` → `{event,duplicate}`。此入口始终记录 `source='replay'`，不会确认平台消息，不会自动调用 DeepSeek 或播报。
- `POST /taobao/events/:id/draft` body `{shop_id,product_id}` → `Job`；显式生成该评论的待审核稿，同事件只生成一次（失败/未知调用不自动重试）。先检查场次有效性与评论长度。

`Room={shop_id,session_id,live_id,updated_at}`。

`Event={id,shop_id,session_id,message_id,live_id,comment,source:'taobao'|'replay',dedup_key,status:'pending'|'generating'|'drafted'|'failed'|'ignored',job_id:string|null,error_code,received_at}`。不保存昵称或用户ID；去重依次使用 uniqueCode、TMC message_id；回放与真实消息分离。无法可靠去重的无ID消息拒绝。未知房间/其他topic不会伪造成本店评论。

## TOP 操作

- `POST /taobao/poll` body `{shop_id}` → `{received,stored,duplicates,ignored,confirmed}`；需要后端配置绑定同一个 shop_id 的淘宝应用。按官方 consume → 持久化/去重 → confirm 协议；任一步失败均不假确认。
- `POST /taobao/live-detail` body `{shop_id,session_id}` → `{live_id,data}`，调用官方直播间详情。
- `POST /taobao/items` body `{shop_id,page_no,page_size}` → `{items,total_results}`，读取出售商品（只预览，不覆盖人工资料）。前端选择后经普通商品接口保存并人工审核。
- `POST /taobao/push-item` body `{shop_id,session_id,item_id,request_id:UUID}` → `{request_id,status:'succeeded'|'delivery_unknown'|'failed'}`；显式操作才发出，重复 request_id 返回既有结果、不重发。
- `POST /taobao/report` body `{shop_id,session_id,request_id:UUID,metrics:{...}}` → 同上；指标严格按官方允许字段校验，不接受任意方法名或参数代理。

TMC HTTP 接收是官方支持的较低实时性方案，适合本地联调与小流量测试，不能宣称拥有官方 SDK 长连接的实时性。账号的 API 权限和数据处理许可仍由应用所属平台管理。

## 本地保守处理的协议边界

显式 `messages.tmc_message=[]` 视为成功但没有消息。官方公开示例没有说明无消息时是否省略该字段；缺失或null暂返回 `taobao_empty_response_unverified`，保留为真实账号联调项，不能将任意空对象显示为成功轮询。商品列表要求返回总数与所请求的商品事实，不把遗漏价格/库存字段变成0。

弹卡与状态上报共用场次派发锁，并登记可取消操作。接管/结束改变epoch并取消在途请求；迟到结果记为 `delivery_unknown`，重复request_id只读取既有状态。一般TOP `error_response` 包含远端服务错误，不能证明副作用未发生，按结果不明记录；只有明确的业务拒绝字段才标记failed。

协议依据：[CommentSend主题](https://developer.alibaba.com/docs/topicDetail.htm?apiId=2664)、[TMC consume](https://developer.alibaba.com/docs/api.htm?apiId=21986)、[TOP签名规范](https://developer.alibaba.com/docs/doc.htm.htm?articleId=101617&docType=1&treeId=1)、[TMC HTTP消费与确认说明](https://developer.alibaba.com/docs/doc.htm?articleId=119543&docType=1&treeId=684)。字段缺失的处理和本地epoch约束是本项目的保守实现选择。
