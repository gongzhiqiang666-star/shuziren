# main / CloneManager 本地资源契约

## 原始样本

- `yunchuang_v122/_internal/main.cp310-win_amd64.pyd`
- `yunchuang_v122/_internal/live/clone_manager.cp310-win_amd64.pyd`
- Ghidra 12.1.4 项目：
  - `rea-output/ghidra-main/main.gpr`
  - `rea-output/ghidra-clone-manager/clone_manager.gpr`

## main API 已确认行为

| 方法 | wrapper / body | 行为 |
|---|---|---|
| `get_local_resources` | `0x1800b9320` / `0x1800b9490` | 调用 `self._clone_manager.get_local_models()` 解包为 `models, voices`；成功返回 `{"models": models, "voices": voices, "status": "success"}`；异常仅返回 `{"error": str(error)}` |
| `delete_model` | `0x1800b7980` / `0x1800b7c40` | wrapper 要求 `str`；调用 `self._clone_manager.delete_model(model_name)`；成功仅返回 `{"status": "success"}`；异常返回 `{"error": "删除模型失败: ..."}` |
| `delete_voice` | `0x1800b8650` / `0x1800b8910` | wrapper 要求 `str`；调用 `self._clone_manager.delete_voice(voice_name)`；成功仅返回 `{"status": "success"}`；异常返回 `{"error": "删除音色失败: ..."}` |

旧恢复实现曾自行扫描 `assets`，并返回 `image_models/voice_models/pretrained_models`，同时改变删除成功和失败的响应格式。该行为已经移除，主 API 现在保持原生委托边界和响应契约。

## CloneManager 静态证据

原生主体地址：

- `_build_model_preview`: `0x180005e50`
- `_build_voice_preview`: `0x1800081d0`
- `delete_model`: `0x1800151b0`
- `delete_voice`: `0x180015d40`
- `_read_model_info`: `0x18001a980`
- `get_local_models`: `0x18001b790`
- `_create_model_info`: wrapper/body `0x180016750` / `0x1800170e0`
- `_create_voice_info`: wrapper/body `0x1800192b0` / `0x180019820`

字符串表初始化函数位于 `0x180022010`。已导出 `rea-output/clone-manager-string-table.tsv`，确认本地资源使用：

- 根目录配置：`image_base_dir`、`voice_base_dir`
- 形象内部变量：`model_id`、`model_name`、`model_path`、`model_info`；持久化和返回使用统一字段名。
- 音色内部变量：`voice_id`、`voice_name`、`voice_path`、`voice_info`、`ref_audio_path`；音色信息和形象信息都写入 `model_info.yaml`，并非 `voice_info.yaml`。
- 预览编码：形象固定以 `data:image/jpeg;base64,` 输出；音色通过 `_encode_file_as_data_url(..., "audio/wav", ...)` 输出。
- 删除：先用 `_resource_dir` 解析资源目录，检查存在性，不存在时抛 `FileNotFoundError`，存在时调用 `shutil.rmtree`，返回 `None`。

### 精确记录结构

`_create_model_info` 和 `_create_voice_info` 的主体证明持久化键不是旧恢复实现采用的 `model_id/model_name` 或 `voice_id/voice_name`，而是统一的 `id/name`。两种资源都写入 `model_info.yaml`，并记录 `create_time`、`provider` 和排序去重后的 `supported_versions`。

`get_local_models` 构造的形象记录共 10 个键：

```text
id, name, create_time, sample_data, supported_versions,
resolution, width, height, kt_board, kt_board_hit
```

其中缺省支持版本为 `["v2"]`，缺省宽高为 `720x1280`；只有信息标记和 KT 缓存文件同时存在时，返回的 `kt_board` 才为真。

音色记录共 6 个键：

```text
id, name, create_time, sample_data, provider, supported_versions
```

缺省支持版本为 `v1/v2/v3/malai_local/vietnam_local`。缺少预览文件时 `sample_data` 为 `None`，而不是空字符串。

## 当前验证边界

`verify_main_local_resources_contract` 已覆盖主 API 的成功响应、异常响应、参数类型和委托参数保真；`verify_clone_manager_local_resources_contract` 已覆盖统一 YAML 结构、形象/音色记录、固定 MIME、KT 缓存判断、删除和目录穿越防护。形象缩略图的精确像素压缩参数、旧资源目录兼容性和 Windows 文件占用异常仍需原 `.pyd` 差分，因此 SYS-007 暂不提升为“静态验证通过”。

