# V02-04a 显式LLM配置适配

日期：2026-11-10。适配层、任务和控制台协议流程已验证，真实LLM效果尚未验收。

新增scripts/console_llm.py，专用环境变量SHUZIREN_LLM_ENDPOINT（完整chat/completions地址）、SHUZIREN_LLM_MODEL、SHUZIREN_LLM_API_KEY，及可选SHUZIREN_LLM_TIMEOUT（默认30秒，最大60秒）。不自动读取原包或HuanjingLive用户凭据。配置状态仅返回configured布尔值。地址拒绝userinfo、query及fragment；远程要求HTTPS，本机可HTTP；控制台调用禁止重定向。

复用恢复版提示、语言清理和重试，新增generate_structured_speech_with_config入口。原generate_structured_speech和_retry_without_han签名保持原样。首次直接加关键字参数导致原生签名校验失败；已修正并复测，不降低校验要求。base_chat仅在显式配置含allow_redirects时传入该选项，旧路径保持原调用参数。

生成前读取商品版本快照，成功后事务检查版本及内容再保存source=llm；生成期间编辑商品会拒绝旧结果。上游异常在控制台适配边界转换为固定错误，不回传可能携带凭据的URL、响应体或异常文本。该模块不记录请求/响应日志。当前适配可用于控制台接入，尚未提供取消工作进程和页面异步状态管理，V02-04保持开发中。

验证：test_console_llm.py 6项通过，使用本机真实HTTP传输和可控协议服务验证正常返回、空返回、401/500、读超时、英文含汉字后的重试、生成中编辑导致冲突、缺配置和非法配置。服务返回的是测试文本，不是模型推理，不能计入V02-05。测试凭据为虚构sentinel，未访问外部LLM。

完整check-recovery-baseline.ps1复测通过5组：路径测试、完整性策略测试、功能矩阵、128模块恢复校验、23项proof工具测试。日志分别保留logs/validation/v02-llm-baseline（首次失败）及v02-llm-baseline-fixed（通过），不提交。

## V02-04b 当前实现与验证

scripts/llm_tasks.py使用Windows spawn子进程生成；子进程只返回文本，由父进程检查任务未取消、商品快照有效后入库。取消与写入共享锁，取消后不写入；若先已写入，则如实返回已完成。显式退出回收本实例进程，不凭旧PID结束其他进程。

llm-task.json保存最后任务的ID、商品ID/标题/版本、状态及结果ID/固定错误，不存凭据或完整提示。刷新查询不派发，重启将running标为interrupted，不自动重跑；已有任务时拒绝重复派发。监控最多250秒，覆盖原有最多四次、每次最大60秒请求。取消终止本地工作进程，不代表远端已停止计费。强制杀死宿主时对子进程的回收尚未专门验证。

页面及HTTP已接入生成、取消、查询及轮询，服务close调用清理。9项LLM协议/真实进程测试通过，包括进入HTTP请求后取消、无结果入库、进程结束、重复派发、成功状态持久化、正常退出取消及重启中断标记。17项控制台配置/HTTP测试通过，含缺专用配置明确400且不创建任务。JS语法检查通过。测试文本不是模型推理。

## V02-04b 本机浏览器放行

运行`python -X utf8 -m scripts.validate_llm_console --data-directory logs/validation/v02-task-ui --port 5188`，只连接本机可控协议服务。fixture-mode.txt可选slow/success/empty/unauthorized；使用虚构凭据，返回文本标有“协议测试文本，非模型生成”。

实测新增测试商品→生成慢请求→刷新仍正在生成（日志仅一次派发）→取消→切401模式再生成，页面失败→切success重试，页面显示成功及话术记录→切slow启动并在生成中退出。进程session96071退出0；最终任务cancelled，数据库只有一条成功测试话术，5188端口可重新绑定；console.log及llm-task.json未出现测试凭据。取消和401任务未存话术。审计记录及截图在本机logs/validation/v02-task-ui/audit.json、task-success.png，不提交。fullPage截图失败后改为保存可视区域截图。

修正了任务初次读取即完成时可能漏刷新话术列表的分支，成功状态始终读取对应商品记录；本次成功展示通过。V02-04b协议/界面范围通过，下一项V02-05，需实际服务地址、模型和本机专用凭据；不以本机协议服务代替模型推理。
