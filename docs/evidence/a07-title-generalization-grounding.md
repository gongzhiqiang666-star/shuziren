# CNT-004 标题与话术泛化事实门禁

验证日期：2026-11-14

## 实现

- 抽出 `content_grounding.validate_grounded_claims`，商品话术、标题/标签和泛化话术共用相同数字/价格事实规则。
- 标题和标签组合若出现原口播稿不存在的阿拉伯数字，或原稿没有价格却新增货币表达，明确拒绝。
- 话术泛化的每个候选首次事实不合格时再请求一次；第二次仍不合格则失败，不把编造内容塞入方括号变体。
- 标准 JSON、轻微破损 JSON、标签去重及类型严格校验保持不变。

## 自动化证据

- `tests/test_title_generalization_grounding.py`：3 项通过，覆盖标题数字、标签价格、已有数字/价格和泛化重试。
- `tests/test_generate_title_validation.py`：4 项通过，覆盖标准/破损 JSON 及非法 title/tags 类型。
- `tests/test_structured_speech_grounding.py`：3 项继续通过，证明统一门禁未削弱商品话术保护。
- 恢复基线五关全部退出 0。

## 外部待验

真实 DeepSeek 的标题吸引力、标签相关性、泛化自然度与语义等价仍需人工审核；规则只证明可确定的数字和价格不被新增。
