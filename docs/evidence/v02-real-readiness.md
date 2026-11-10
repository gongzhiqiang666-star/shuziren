# V02-05 真实生成验收准备与缺失条件

日期：2026-11-10。当前状态：条件缺失，未放行，不进入V03。

## 本机检查

当前进程未设置SHUZIREN_LLM_ENDPOINT、SHUZIREN_LLM_MODEL、SHUZIREN_LLM_API_KEY，仅检查存在性，不打印秘密。ollama.exe/lms.exe未在PATH发现；常见11434、1234、8000无监听。8080监听进程13192是v179的assets/srs/objs/srs.exe，为媒体服务，不能作为LLM端点。此检查不声称整台电脑不存在任何模型，只说明当前已检查位置没有可直接调用的专用服务。

未擅自读取旧产品凭据，未访问外部模型，未把协议fixture当作真实生成。已询问用户实际服务地址和模型，密钥应只在本机配置。

## 验收脚本

`scripts/validate_real_llm.py`每次创建隔离run目录和SQLite数据库，使用编号008的310毫升青瓷杯、编号3的85×135厘米亚麻桌布。仅发送这些合成商品事实，固定要求不编造价格/优惠/库存等。通过已有任务管理器生成，两结果分别校验商品快照、数量、来源、哈希差异及数据库重开。拒绝fixture/protocol-test模型标记和明确协议输出，不存在自动“验收通过”的结果：生成成功仍为generated-awaiting-human-review。

```powershell
python -X utf8 -m scripts.validate_real_llm --report-directory logs/validation/v02-real --prepare-only
python -X utf8 -m scripts.validate_real_llm --report-directory logs/validation/v02-real
```

本机已执行：prepare-only生成两商品并记录prepared-no-network；真实入口返回not-passed、real_requests_started=false，错误为专用LLM配置缺失。报告仅在本机忽略目录保存。3项测试通过：准备不冒充生成、缺配置不成功、协议模型不冒充真实模型，报告不泄露测试密钥。

## 配置可用后的放行清单

1. 运行真实入口，确认两商品各一条非空话术、输出不同、商品归属和快照正确、重开一致。
2. 人工核对：杯子的容量/材质/颜色不能串到桌布，桌布尺寸/材质/颜色不能串到杯子；无虚构价格、优惠、库存、功效或承诺；语言与口播可用。逐条记录是否通过及修正原因。
3. 在真实服务页面流程验证生成期间编辑商品的旧结果拒绝、失败重试与重开，结合此前协议异常/取消测试确认无串商品、无失败文本入库。
4. 检查日志及任务记录不含实际密钥；报告不记完整端点、认证头或环境变量。只输出是否泄露，不打印命中内容。
5. 将真实服务/模型、实际结果、人工结论和剩余限制记入证据，再决定V02放行。缺任何必需证据不放行。
