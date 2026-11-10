# V02-04a 显式LLM配置适配

日期：2026-11-10。当前完成适配层和协议测试，尚未完成控制台生成入口及真实LLM验收。

新增scripts/console_llm.py，专用环境变量SHUZIREN_LLM_ENDPOINT（完整chat/completions地址）、SHUZIREN_LLM_MODEL、SHUZIREN_LLM_API_KEY，及可选SHUZIREN_LLM_TIMEOUT（默认30秒，最大60秒）。不自动读取原包或HuanjingLive用户凭据。配置状态仅返回configured布尔值。地址拒绝userinfo、query及fragment；远程要求HTTPS，本机可HTTP；控制台调用禁止重定向。

复用恢复版提示、语言清理和重试，新增generate_structured_speech_with_config入口。原generate_structured_speech和_retry_without_han签名保持原样。首次直接加关键字参数导致原生签名校验失败；已修正并复测，不降低校验要求。base_chat仅在显式配置含allow_redirects时传入该选项，旧路径保持原调用参数。

生成前读取商品版本快照，成功后事务检查版本及内容再保存source=llm；生成期间编辑商品会拒绝旧结果。上游异常在控制台适配边界转换为固定错误，不回传可能携带凭据的URL、响应体或异常文本。该模块不记录请求/响应日志。当前适配可用于控制台接入，尚未提供取消工作进程和页面异步状态管理，V02-04保持开发中。

验证：test_console_llm.py 6项通过，使用本机真实HTTP传输和可控协议服务验证正常返回、空返回、401/500、读超时、英文含汉字后的重试、生成中编辑导致冲突、缺配置和非法配置。服务返回的是测试文本，不是模型推理，不能计入V02-05。测试凭据为虚构sentinel，未访问外部LLM。

完整check-recovery-baseline.ps1复测通过5组：路径测试、完整性策略测试、功能矩阵、128模块恢复校验、23项proof工具测试。日志分别保留logs/validation/v02-llm-baseline（首次失败）及v02-llm-baseline-fixed（通过），不提交。

## V02-04b 当前实现与验证

scripts/llm_tasks.py使用Windows spawn子进程生成；子进程只返回文本，由父进程检查任务未取消、商品快照有效后入库。取消与写入共享锁，取消后不写入；若先已写入，则如实返回已完成。显式退出回收本实例进程，不凭旧PID结束其他进程。

llm-task.json保存最后任务的ID、商品ID/标题/版本、状态及结果ID/固定错误，不存凭据或完整提示。刷新查询不派发，重启将running标为interrupted，不自动重跑；已有任务时拒绝重复派发。监控最多250秒，覆盖原有最多四次、每次最大60秒请求。取消终止本地工作进程，不代表远端已停止计费。强制杀死宿主时对子进程的回收尚未专门验证。

页面及HTTP已接入生成、取消、查询及轮询，服务close调用清理。9项LLM协议/真实进程测试通过，包括进入HTTP请求后取消、无结果入库、进程结束、重复派发、成功状态持久化、正常退出取消及重启中断标记。17项控制台配置/HTTP测试通过，含缺专用配置明确400且不创建任务。JS语法检查通过。测试文本不是模型推理。

下一步仍为V02-04b：浏览器任务验收、刷新/取消/错误/退出可视验证和完整HTTP成功链。V02-05需用户选择实际服务并在本机配置凭据后，进行两个商品真实生成；目前专用环境变量未发现，不以协议测试替代。
