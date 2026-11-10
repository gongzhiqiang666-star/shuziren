# Windows 控制台源码包

将 `SHUZIREN_PYTHON` 设置为本机 Python 或独立虚拟环境的 `python.exe`，再运行 `packaging\start-console.cmd`。首次隔离验证可传 `--data-directory "C:\验证数据" --port 0`，启动输出会显示本机控制台地址。使用 LLM 功能前，在该环境安装 `packaging/requirements-console.txt`。

源码包包含控制台、恢复源码和依赖版本说明。形象、音频、驱动、模型及 GPU 运行环境需要另行配置。当前媒体运行仍需兼容的外置运行目录。模型和依赖独立交付、升级回滚和干净 Windows 验收另有任务记录。

## 独立媒体运行目录

运行 `python -m scripts.media_runtime initialize --root <媒体运行目录>` 创建布局清单。将目标 Python 环境放在 `_internal/env`，独立环境的入口是 `Scripts/python.exe`。FFmpeg 和 FFprobe 放在 `_internal/env/ffmpeg/bin`。模型及 IndexTTS、WeNet 提供方代码按 `python -m scripts.media_runtime check --root <媒体运行目录>` 的分组清单安装。清单检查关键入口文件，完整依赖、驱动、模型来源和推理能力另行验收。验证过的 Python/CUDA 包版本见 `recovered/requirements-*.txt`。

将该目录填入控制台的运行资源配置。原目录格式也可用于对照验证。独立布局不要求原厂 EXE、启动脚本和原厂应用扩展模块。

可从已获授权的本机参考运行目录准备独立环境。目标必须是新目录，建议预留至少 20 GiB，实际占用取决于参考环境和模型。

```powershell
python -m scripts.stage_media_runtime --reference "<授权参考目录>" --destination "<新媒体目录>"
python -m scripts.media_runtime check --root "<新媒体目录>"
```

此流程复制选定的 Python 和第三方运行环境、提供方源码及模型。将新媒体目录填入控制台配置，使用其中的解释器和依赖。该流程依赖本机已配置的参考资源。输出的 `staging-result.json` 记录解释器重定位和关键入口检查，真实 GPU 推理另行验证。媒体目录保存在仓库外。

维护者从已提交版本运行 `python -m scripts.console_package build --output <zip路径>`。使用 `verify --archive <zip路径>` 核对清单，再以 `install --archive <zip路径> --destination <新目录>` 安装。校验用于发现文件损坏，来源仍需通过可信交付渠道确认。

## 版本管理

从当前维护工具所在目录执行以下命令。`--root` 指向同一个独立安装目录。

```powershell
python -m scripts.console_package deploy --root "C:\数字人控制台" --archive console.zip
python -m scripts.console_package run --root "C:\数字人控制台"
python -m scripts.console_package rollback --root "C:\数字人控制台"
```

首次部署和升级使用同一条 `deploy` 命令。先通过页面退出控制台，再切换版本。各版本保留在 `releases`，用户配置和商品共用 `data`。切换前使用临时数据目录检查候选版本的启动与正常退出，失败时保留当前版本。当前支持同一数据架构的版本切换，跨架构迁移仍待实现。

## 迁移已有控制台数据

退出原控制台，在新安装首次部署前运行以下命令。若目标已经存在 `data`，请使用新的安装目录。

```powershell
python -m scripts.console_package migrate-data --source "<原控制台数据目录>" --root "<新安装目录>"
```

迁移保留配置、商品、话术、已登记音色和形象及其选择状态，源数据可继续使用。媒体目录设置保留原路径，搬到另一台机器时按实际位置更新。缓存、运行日志和平台登录态不随迁移复制，到新环境后可重新登录平台。
