# Main runtime and configuration API recovery

## 商品话术生成

`Api.generate_script` 的包装体/主体为 `0x180036950/0x180037230`，其生成器
闭包包装体/主体为 `0x180036d00/0x180036ec0`。原生签名严格接收
`product_info: dict` 和 `special_instructions: str = ""`，并不是旧恢复版支持的
列表批处理协议。

主体按字典插入顺序遍历商品，仅处理含 `content` 键的值；每项调用
`generate_structured_speech(product["content"], special_instructions)`。非空结果加入
话术列表；假值或异常都写入空话术并把字符串化的商品 ID 加入
`failed_products`，但不会中断后续商品。最终话术以两个换行符连接再 `strip()`。
只有存在失败商品且所有生成结果都为空时才加入
`error="没有成功生成任何话术"`。方法级异常返回空话术、空失败列表和
`生成脚本时发生错误：<异常>`。恢复源码、逐项失败/异常、跳过无 `content`
商品、全部失败和外层异常均已加入回归；完整门禁保持 `128/128 PASS`。

## 文本翻译入口

`Api.translate_text` 的包装体/主体为 `0x18004f510/0x18004f8c0`。包装体要求
`text` 和 `target_language` 都是字符串。主体不按 500 字切片，也不直接拼装
`base_chat` 提示词；它保留非空原文（包括首尾空白），将空目标语言回退为
`zh-CN`，经 `normalize_language_code` 规范化后，一次调用
`translate_text_llm(text, language, raise_on_failure=True)` 并原样返回结果。

翻译异常由该 API 捕获，打印 `翻译失败: <异常>`，并返回单键字典
`{"error": "<异常>"}`。恢复版此前自创的 500 字固定分块、英文系统提示和异常
向外传播已删除。空文本、语言别名、1200 字不分块、失败包络和包装体类型边界
已有聚焦测试；完整门禁保持 `128/128 PASS`。

## LLM 配置保存与连通性测试

`save_llm_config` 包装体/主体为 `0x180068800/0x180068ac0`。原生实现不清洗
字段，也不要求 endpoint/api_key/model 非空；它把调用方字典原样交给
`self._save_user_config({"llm_config": data})`，同步写入
`self.config["llm_config"]`，调用 `_update_managers_config()`，成功仅返回
`status="success"` 和 `message="配置已保存到本地"`。异常返回单键 `error`。

`test_llm_availability` 包装体/主体为 `0x180057640/0x180057900`。它读取
`vendor/model/endpoint/api_key`，将 vendor 转小写；任一缺失时返回包含
`status/message/is_available/is_recommended_provider/provider` 的固定失败结构。
配置齐全时以关键字参数调用 `base_chat(question="回复一个字：好",
sys_prompt="你是一个助手", chat_history=[], llm_config=config)`。非空且 strip 后
有效的回复返回“大模型服务正常”，两个布尔值均为真；假值回复、调用异常和
provider 回退均使用原生五字段协议。配置对象原样保存、管理器刷新、缺失字段、
成功、空回复、异常和类型边界已有聚焦覆盖；完整门禁保持 `128/128 PASS`。

## IP 发布标题和标签

`Api.generate_ip_agent_publish_meta` 的包装体/主体为
`0x180142690/0x180142a40`，包装体严格接收字符串 `project_id` 和字典 `data`。
主体加载 IP 项目；项目不存在时返回 `{"error":"IP项目不存在"}`。文案按
`data.script -> project.rewritten_script -> project.original_script -> ""` 选择并
`strip()`，空文案返回 `{"error":"请先准备文案内容"}`。视频上下文按
`data.video_url -> project.benchmark_url -> ""` 选择，然后只调用一次
`generate_title_and_tags(script, video_url)`。

返回标题会字符串化并去除首尾空白，标签经 `_normalize_publish_tags` 处理；项目
仅保存 `publish_title` 与 `_stringify_publish_tags(tags)` 生成的
`publish_tags_text`。成功结果固定包含 `status/title/tags/project`。异常返回单键
`error="生成发布标题和标签失败: <异常>"`。旧恢复版额外执行的本地视频探测、
静默 LLM 兜底、调用方标题/标签覆盖和封面生成均不属于该入口，现已移除；这些
工作应由独立成片/封面阶段负责。项目缺失、文案优先级、对标 URL 回退、保存增量、
调用方覆盖隔离和异常包络已有聚焦回归。

Recovered in this pass:

- User/private configuration delegation, atomic YAML persistence and recursive
  merge support.
- Token, administrator ID, OEM branding, background image and version APIs.
- Local image/voice/pretrained model enumeration and path-safe deletion.
- Audio-directory counting and bounded cache cleanup.
- Camera enumeration, resolution probing, GPU/CUDA/VRAM reporting and RTX 50
  series recognition.
- ffprobe video dimension/FPS validation with the packaged 25 FPS rule.
- Volcengine image configuration, structured script generation, chunked LLM
  translation, stream URLs and interruption state updates.
- Distribution root and `env`/`env_50` selection, FFMPEG_HOME/PATH/DLL setup,
  startup admin ID and console-output setup.
- Generic YAML/text/subprocess/media-preview helpers used by the main API.

Verification included isolated user configuration, fake OEM/assets, safe model
deletion, real 25/30 FPS sample videos, simulated camera devices, simulated RTX
5090 `nvidia-smi`, mocked LLM calls and a real AVI-to-browser-MP4 conversion.
The full recovered source tree continues to pass `compileall`.
