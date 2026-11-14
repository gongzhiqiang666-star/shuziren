# CNT-009 IP 发布标题和标签验证

验证日期：2026-11-14

## 原接口范围校正

原 `.pyd` 主体证据确认该入口只调用一次 `generate_title_and_tags(script, video_url)`，项目只保存 `publish_title` 和 `publish_tags_text`；成功结果只包含 `status/title/tags/project`。因此权威矩阵由“标题、简介、标签”纠正为“标题和标签”，不在兼容入口擅自增加简介字段。

## 验证结果

- 标题/标签继续使用统一数字与价格事实门禁。
- 标题编造 `99` 时 API 返回错误，`_save_ip_agent_project` 调用次数为 0。
- 原稿包含 `530毫升` 时，标题使用 `530` 正常通过；标签去除 `#`、去重，并且只保存原生两个项目字段。
- `tests/test_ip_publish_meta_grounding.py` 2 项、标题结构 4 项、标题事实 3 项及恢复五关通过。

## 外部待验

真实 DeepSeek 标题吸引力、标签相关性及原 `.pyd` 同输入动态差分仍需服务与样本。发布简介若产品后续需要，应作为新能力单独设计，不能冒充原接口恢复。
