# V02-01 商品与话术契约核对

日期：2026-11-10。来源为当前recovered源码、逆向报告和D:/TEMP/shuziren的80282eb源码。未以源码阅读冒充真实LLM生成或原生差分。

## 必须保留的行为

- `recovered/main.py: Api.generate_script(product_info, special_instructions)`接收按商品键组织的dict；无content的条目跳过；有content的逐条生成，单项失败保留空位并记录failed_products；全部失败附error。聚合script是兼容输出，不适合作为新控制台唯一持久化结构，否则无法可靠关联商品。
- `recovered/live_manager_runtime.py: LocalLiveBrain._resolve_product_info`逐项对product_index执行int比较，取同项truthy content并转str；坏项跳过，未匹配回退实例product_info。商品编号不等于下标。组位置和脚本游标也按显式编号查找。
- `recovered/generate_structured_speech.py`保留语言标记、提示构造、清理和重试；底层`llm_base_chat.base_chat`支持显式llm_config，字段endpoint/api_key/model及旧别名。默认读取HuanjingLive用户配置，不能让新控制台无意读取或覆写另一产品的凭据。
- `main_config.load_effective_config`包含旧私密配置迁移写入行为，不能为本控制台只读资源探测直接调用。原配置导入应显式、只读、保留未识别字段。

## 80282eb可复用经验及差异

Go的domain.Product使用UUID/shop_id、标题/SKU/说明/规格、分单位价格、库存、有效期及version。SaveProduct事务校验所属店铺、更新按version比较、保存历史并审计。借鉴稳定身份、版本冲突及不可变生成快照；不能直接拿UUID替换原product_index。DeepSeek客户端将商品事实与风格分开、拒绝空回答、错误显式上报；新的兼容调用应保持已有语言能力，不能因该分支仅支持中文而缩减范围。

本机只检查原config.yaml的字段存在性/类型，没有打印私密值：product_scripts、products、product_info均缺失，llm_config为dict。因此这份默认配置不是已保存商品项目样本。原用户项目格式的未知字段必须保留并登记后续差分，不能自行断言已全兼容。

## 实施任务与验收

| 编号 | 工作 | 通过条件 |
| --- | --- | --- |
| V02-01 | 核对兼容契约及复用决策 | 本记录；稀疏编号与商品关联规则明确，未知项目格式保留为差分项 |
| V02-02 | 商品/话术持久化 | 独立本地数据库，稳定ID+legacy product_index+版本，生成结果绑定商品与输入版本；中文/空输入/冲突/重开/跨商品不串数据测试通过 |
| V02-03 | 本地编辑与选择 | 页面新增/编辑/保存/选定商品及人工话术；刷新和重启恢复，实际浏览器验证；原编号与排序分开 |
| V02-04 | LLM兼容接入 | 显式配置注入现有生成器，保留语言与重试；凭据不回显、不进日志，失败不能写成话术；超时/空返回/授权失败自动化验证 |
| V02-05 | 真实LLM及整体放行 | 本机真实服务至少两个商品各自生成，编辑期间结果冲突可见、失败可重试，人工核对事实归属；重开及日志泄密检查通过 |

V02-02的单机持久化选用Python标准库SQLite，以事务与唯一约束实现身份/版本隔离；这是替代Go分支PostgreSQL的内部实现选择，不改变原用户侧能力。后续多店/容量评测不据此宣告通过。原项目导入保留原载荷，建立可逆映射；未验证的格式不能标注兼容完成。

真实LLM访问条件尚未核实，不读取或复用现有秘密值来推定已授权可调用。可先完成独立配置与本机服务发现；若缺实际调用条件，V02保持未放行，不以测试替身替代。
