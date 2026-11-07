# `main.pyd` IP-agent recovery notes

- Persistent project: `rea-output/ghidra-main/main`
- Wrapper exports: `rea-output/main-ip-agent-decompiled/`
- Body exports: `rea-output/main-ip-agent-bodies/`
- Method table: `rea-output/main-method-table.tsv`
- State-name table: `rea-output/main-state-names.tsv`

The first IP-agent body group covers `_get_ip_agent_base_dir`,
`_get_ip_agent_project_dir`, `_get_ip_agent_project_info_path`,
`_default_ip_agent_project_info` and `_build_ip_agent_project_summary`.
The native root is `os.path.join(os.path.dirname(__file__), "assets",
"ip_agent_projects")`; it is not derived from `runtime_dir`. The two child
helpers are direct `os.path.join` calls and do not contain the recovery's
invented `Path.resolve()` traversal policy.

`_default_ip_agent_project_info`, wrapper/body `0x1800ce530/0x1800ce8e0`,
creates a 47-entry dictionary. Time is formatted with
`datetime.now().strftime("%Y-%m-%d %H:%M:%S")`, and the native keys are
`create_time`/`update_time`, not `created_at`/`updated_at`. The body-level
dictionary stores benchmark/script/rewrite fields, selected language/voice/model,
preview and result media paths, the complete subtitle configuration, BGM,
cover, final media, publishing platforms/accounts/results and one-click state.
Recovered native defaults include `zh-CN`, voice speed `1.0`, the imported
`DEFAULT_SUBTITLE_STYLE_PRESET`, highlight enabled, animation `fade`, BGM
volume `0.16`, cover template `impact_yellow`, and `publish_platforms=["douyin"]`.
The prior recovery contained only about half of this protocol and invented
eager audio/video output paths plus a `status` field.

`_build_ip_agent_project_summary`, wrapper/body `0x1800cf710/0x1800cfac0`,
returns exactly `id`, `name`, `create_time`, `update_time`, `preview_url` and
`path`. Empty names fall back to `IP项目-<id>`. Missing or nonexistent
`cover_path` falls back to `<project_dir>/result/sample.jpg`; preview encoding
is attempted on that path and `path` is `os.path.abspath(project_dir)`. The
former readiness/status summary was not present in the binary.

A focused schema test locks all 47 keys and critical constants, directory
layout, fallback timestamps, cover behavior and exact six-key summary. The
complete verifier remains `128/128 PASS`. The adjacent load/save/create/list
and media pipeline bodies are exported but not yet all reconciled, so the
IP-agent family remains active work.

`get_ip_agent_creation_assets`, wrapper/body `0x1800e4150/0x1800e42c0`, is
also reconciled. It converts every `SUBTITLE_STYLE_PRESETS` entry to
`value/font_name/highlight_color`, with `Microsoft YaHei` and the empty string
as the two defaults. The successful response contains `status`,
`music=list_music_library(limit=80)`, `fonts=list_font_options()`,
`cover_templates=list_cover_templates()` and `subtitle_styles`. The former
recovery omitted subtitle styles, used `font_options` instead of `fonts`, did
not pass the music limit, and returned the wrong exception envelope. The
native failure response is the single `error` field prefixed with
`获取IP智能体资源失败: `. Both paths now have focused coverage.

`_load_ip_agent_project`, wrapper/body `0x1800d0ad0/0x1800d0d90`, now follows
the native enrichment path. A missing directory or empty YAML returns `None`.
Loaded data is assigned the requested `id` and absolute project `path`; a
missing cover falls back to `result/sample.jpg` before preview encoding. The
three result/subtitled/final video paths independently refresh their browser
preview fields through `_resolve_browser_preview_path` when populated.

`_save_ip_agent_project`, wrapper/body `0x1800d2e50/0x1800d3200`, does not
create projects. It raises `FileNotFoundError("IP项目不存在")` unless the project
directory already exists, reads the old YAML, and merges dictionaries in the
exact order default schema, existing data, then caller data. It forces the
requested `id`, writes `update_time` in `%Y-%m-%d %H:%M:%S` form, fills a falsy
`create_time`, removes `subtitle_debug_json_path`, persists through the YAML
helper, and returns the enriched loader result. Focused tests cover missing
projects, merge precedence, the complete default fill, transient-field
removal, cover fallback and all three preview routes. Full verification is
again `128/128 PASS`.

The public get/update/delete wrappers are also aligned: get maps a falsy load
to `{"error":"IP项目不存在"}`; update passes `data or {}` directly to save;
delete checks `os.path.isdir`, removes the project tree and returns `删除成功`.
Their native error prefixes and response envelopes are locked by regression.

`create_ip_agent_project`, wrapper/body `0x1800e0390/0x1800e0650`, validates
the original string and its stripped value, returning the direct error
`请输入项目名称` for either empty case. It generates `uuid4().hex`, creates the
project directory with `os.makedirs(..., exist_ok=True)`, builds the complete
default record and only then calls the save helper. Success returns
`status/project`; exceptions return the single error field prefixed
`创建IP项目失败: `. This explicit mkdir is the matching half of the native save
helper's “directory must already exist” contract.

`get_all_ip_agent_projects`, wrapper/body `0x1800e1810/0x1800e1d20`, creates
the root directory, iterates `os.listdir`, skips non-directories, loads each
project and appends only truthy records through the summary helper. It sorts by
`item.get("update_time", "")` with `reverse=True`, not the recovery's obsolete
`updated_at` key. Native success and `获取IP项目列表失败: ` error envelopes are
covered, together with directory creation, ignored files and order.

`get_ip_agent_media_data`, wrapper/body `0x1800e53e0/0x1800e56a0`, now uses
`os.path.abspath(file_path or "")`, checks existence, invokes
`_encode_media_data`, and returns exactly `status/file_path/data_url`.
The former runtime-root containment policy and `mime_type/file_name/data`
response were invented. Native errors are `媒体文件不存在`,
`媒体文件过大或读取失败`, and `读取媒体失败: <exception>`.

The adjacent `_encode_media_data` wrapper/body is
`0x1800ca0e0/0x1800ca3a0`. Static initialization at `0x1801a28b6` creates the
integer `0x4000000`, stores it in module-state slot `+0x4fb0`, and the Api class
initializer at `0x1801a8b54` assigns that value to `_INLINE_MEDIA_MAX_BYTES`:
the exact limit is therefore 64 MiB. The helper rejects empty, missing and
oversized files, guesses MIME with an octet-stream fallback, reads binary data,
and emits a Base64 Data URL; any exception returns the empty string. Exact MIME,
fallback, limit, missing-file and exception behavior now have focused tests.
The complete verifier remains `128/128 PASS`.
