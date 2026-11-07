# main 直播贴片项目管理契约

## 原生证据

以下 `main.pyd` 方法已在 Ghidra 12.1.4 工程 `rea-output/ghidra-main/main.gpr` 中定位并导出
wrapper/body：

| 方法 | wrapper | body |
|---|---:|---:|
| `_get_live_sticker_base_dir` | `0x1800be870` | `0x1800be9d0` |
| `_get_live_sticker_project_dir` | `0x1800bf060` | `0x1800bf320` |
| `_get_live_sticker_project_info_path` | `0x1800bf740` | `0x1800bfa00` |
| `_get_live_sticker_history_dir` | `0x1800bfe20` | `0x1800c00e0` |
| `_get_live_sticker_output_paths` | `0x1800c0500` | `0x1800c07c0` |
| `_default_live_sticker_project_info` | `0x1800e7c90` | `0x1800e8040` |
| `_build_live_sticker_project_summary` | `0x1800e8910` | `0x1800e8cc0` |
| `_load_live_sticker_project` | `0x1800e9940` | `0x1800e9c00` |
| `_save_live_sticker_project` | `0x1800eb560` | `0x1800eb910` |
| `_archive_live_sticker_outputs` | `0x1800efc90` | `0x1800f0040` |
| `_attach_live_sticker_previews` | `0x1800f1b60` | `0x1800f1e20` |
| `create_live_sticker_project` | `0x1800f2d90` | `0x1800f3050` |
| `get_all_live_sticker_projects` | `0x1800f4580` | `0x1800f4a90` |
| `get_live_sticker_project` | `0x1800f6510` | `0x1800f67d0` |
| `update_live_sticker_project` | `0x1800f6fc0` | `0x1800f7370` |
| `delete_live_sticker_project` | `0x1800f7bf0` | `0x1800f7eb0` |

## 存储契约

项目根目录是 `<runtime>/assets/live_sticker_projects`，项目 ID 使用带连字符的
`str(uuid.uuid4())`。每个项目保存 `project_info.yaml` 和可选 `history/<时间戳>/`。

固定输出文件及返回键为：

- `bg` → `背景.png`
- `fg_white` → `前景贴片_绿底.png`
- `fg_alpha` → `前景贴片_透明.png`
- `cover_raw` → `直播间封面_原始.png`
- `cover` → `直播间封面.png`

默认 YAML 是 26 字段结构，使用 `%Y-%m-%d %H:%M:%S` 时间格式，包含商品六字段、三类
提示词、五类输出路径、三类尺寸、单标题/标题列表、标题模型、最近错误以及 `draft` 状态。
恢复版此前使用 `created_at/updated_at/product/images` 的自创结构，且缺少两类前景和原始封面，
现已按原生结构更正。

## API 与兼容行为

- 创建名称先 `strip()`；空名称返回 `{"error": "请输入项目名称"}`。
- 列表按 `update_time` 降序，摘要包含 `id/name/create_time/update_time/preview_url/path/status`。
- 单项目读取为假值时返回 `{"error": "贴片项目不存在"}`。
- 更新返回附带 `fg_white_preview_url` 的完整项目；字符串标题列表兼容中英文逗号。
- 删除不存在项目返回 `error`；成功返回 `status=success,message=删除成功`。
- 历史归档复制背景、绿底前景、透明前景和最终封面。
- 旧项目缺少 `fg_white_path` 时会发现固定文件名；旧 `room_title` 会回填到标题列表。
- Cython Unicode/dict wrapper 的严格参数边界在 Python 恢复层显式保留。

## 验证边界

`verify_main_live_sticker_project_contract` 覆盖完整创建、YAML 字段、改名、读取、列表排序所需
摘要、预览 data URL、旧项目迁移、四文件历史归档、删除和参数类型。真实 Windows 旧项目样本、
文件占用/权限失败、前端预览及连续生成多批贴片仍需在 Windows 进行差分和端到端验证。
