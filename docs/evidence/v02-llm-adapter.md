# V02-04a 显式LLM配置适配

日期：2026-11-10。当前完成适配层和协议测试，尚未完成控制台生成入口及真实LLM验收。

新增scripts/console_llm.py，专用环境变量SHUZIREN_LLM_ENDPOINT（完整chat/completions地址）、SHUZIREN_LLM_MODEL、SHUZIREN_LLM_API_KEY，及可选SHUZIREN_LLM_TIMEOUT（默认30秒，最大60秒）。不自动读取原包或HuanjingLive用户凭据。配置状态仅返回configured布尔值。地址拒绝userinfo、query及fragment；远程要求HTTPS，本机可HTTP；控制台调用禁止重定向。

复用恢复版提示、语言清理和重试，新增generate_structured_speech_with_config入口。原generate_structured_speech和_retry_without_han签名保持原样。首次直接加关键字参数导致原生签名校验失败；已修正并复测，不降低校验要求。base_chat仅在显式配置含allow_redirects时传入该选项，旧路径保持原调用参数。

生成前读取商品版本快照，成功后事务检查版本及内容再保存source=llm；生成期间编辑商品会拒绝旧结果。上游异常在控制台适配边界转换为固定错误，不回传可能携带凭据的URL、响应体或异常文本。该模块不记录请求/响应日志。当前适配可用于控制台接入，尚未提供取消工作进程和页面异步状态管理，V02-04保持开发中。

验证：test_console_llm.py 6项通过，使用本机真实HTTP传输和可控协议服务验证正常返回、空返回、401/500、读超时、英文含汉字后的重试、生成中编辑导致冲突、缺配置和非法配置。服务返回的是测试文本，不是模型推理，不能计入V02-05。测试凭据为虚构sentinel，未访问外部LLM。

完整check-recovery-baseline.ps1复测通过5组：路径测试、完整性策略测试、功能矩阵、128模块恢复校验、23项proof工具测试。日志分别保留logs/validation/v02-llm-baseline（首次失败）及v02-llm-baseline-fixed（通过），不提交。

下一步V02-04b：页面/HTTP生成入口、任务状态及停止生命周期、错误显示与回归。V02-05需用户选择实际服务并在本机配置凭据后，进行两个商品真实生成；目前专用环境变量未发现，不以协议测试替代。
