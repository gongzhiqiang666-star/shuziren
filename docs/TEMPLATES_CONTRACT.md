# 商品话术模板

管理 API 前缀 `/api/v1`、正常 data/error envelope。模板用于减少人工重复输入，应用后仍是未审核草稿，不会自动合成或派发。

- `GET /templates?shop_id=UUID` → `SpeechTemplate[]`
- `POST /templates`、`PUT /templates/:id` body `{shop_id,name,body,version}` → `SpeechTemplate`，新增version=0，编辑需当前版本。
- `DELETE /templates/:id?shop_id=UUID&version=N` → `{deleted:true}`。
- `POST /templates/:id/apply` body `{shop_id,session_id,product_id}` → `Job`，只能对同店当前有效商品/场次应用。

`SpeechTemplate={id,shop_id,name,body,version,updated_at}`。name 1..120字，body 1..2000字。只支持以下字面占位符，不执行表达式、脚本或任意字段：

| 占位符 | 当前商品事实 |
| --- | --- |
| `{title}` | 商品名称 |
| `{sku}` | SKU |
| `{price}` | 元金额，保留两位小数，不含“元” |
| `{stock}` | 库存整数 |
| `{specs}` | 规格 |
| `{description}` | 商品描述 |

出现未识别或未闭合的大括号会拒绝，展开后超过2000字也拒绝。使用同一数据库快照渲染，并在保存草稿时再次核验版本；不能把变更前的价格写入变更后的新版本任务。模板中的固定文字由操作者负责核对，系统不推断承诺或自动应用优惠。
