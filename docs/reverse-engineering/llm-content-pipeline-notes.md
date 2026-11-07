# LLM content pipeline recovery

Recovered:

- `tools.llm.base_chat`
- `tools.llm.language_prompts`
- `tools.llm.generalize_sentences`
- `tools.llm.generate_structured_speech`
- `tools.llm.generate_title`

The implementation includes user-config loading, OpenAI-compatible chat
requests, SiliconFlow/DeepSeek thinking control, reasoning-model options, emoji
removal, language aliases/markers, strict non-Han output rules, sentence slicing
and rate limiting, multilingual script retry/filtering, markdown cleanup, and
robust JSON/title parsing.

`Api` now exposes JSON-object extraction, sentence generalization, LLM config
persistence, and availability testing. Tests used mocked HTTP/model responses,
so no external API call or billable token was consumed. They cover request
options, emoji removal, Vietnamese markers, repeated sentence variations,
English retry after invalid Han output, and fenced JSON title/tag parsing.
