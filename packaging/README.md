# Windows 控制台源码包

将 `SHUZIREN_PYTHON` 设置为本机 Python 或独立虚拟环境的 `python.exe`，再运行 `packaging\start-console.cmd`。首次隔离验证可传 `--data-directory "C:\验证数据" --port 0`，启动输出会显示本机控制台地址。使用 LLM 功能前，在该环境安装 `packaging/requirements-console.txt`。

源码包包含控制台、恢复源码和依赖版本说明。形象、音频、驱动、模型及 GPU 运行环境需要另行配置。当前媒体运行仍需兼容的外置运行目录。模型和依赖独立交付、升级回滚和干净 Windows 验收另有任务记录。

维护者从已提交版本运行 `python -m scripts.console_package build --output <zip路径>`。使用 `verify --archive <zip路径>` 核对清单，再以 `install --archive <zip路径> --destination <新目录>` 安装。校验用于发现文件损坏，来源仍需通过可信交付渠道确认。

## 版本管理

从当前维护工具所在目录执行以下命令。`--root` 指向同一个独立安装目录。

```powershell
python -m scripts.console_package deploy --root "C:\数字人控制台" --archive console.zip
python -m scripts.console_package run --root "C:\数字人控制台"
python -m scripts.console_package rollback --root "C:\数字人控制台"
```

首次部署和升级使用同一条 `deploy` 命令。先通过页面退出控制台，再切换版本。各版本保留在 `releases`，用户配置和商品共用 `data`。切换前使用临时数据目录检查候选版本的启动与正常退出，失败时保留当前版本。当前支持同一数据架构的版本切换，跨架构迁移仍待实现。
