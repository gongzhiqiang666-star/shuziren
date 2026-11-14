# Windows 控制台源码包

将 `SHUZIREN_PYTHON` 设置为本机 Python 或独立虚拟环境的 `python.exe`，再运行 `packaging\start-console.cmd`。首次隔离验证可传 `--data-directory "C:\验证数据" --port 0`，启动输出会显示本机控制台地址。使用 LLM 功能前，在该环境安装 `packaging/requirements-console.txt`。

Windows AMD64 的 CPython 3.12 控制台可用固定哈希清单离线安装。先在联网的同规格环境下载对应 wheel，把 wheel 目录与源码包带到目标机，再通过目标虚拟环境安装并核对依赖。此清单覆盖控制台的 HTTP 和 YAML 依赖，媒体依赖按下文准备。

```powershell
python -m pip download --only-binary=:all: --require-hashes -r packaging/requirements-console-win-amd64-py312.lock.txt -d wheels
python -m pip install --no-index --find-links wheels --require-hashes -r packaging/requirements-console-win-amd64-py312.lock.txt
python -m pip check
```

源码包包含控制台、恢复源码和依赖版本说明。形象、音频、驱动、模型及 GPU 运行环境需要另行配置。当前媒体运行仍需兼容的外置运行目录。模型和依赖独立交付、升级回滚和干净 Windows 验收另有任务记录。

若发布包附带 `assets/plugin` 下的可选驱动或运行库安装器，必须先在最终待发布目录生成并复核完整性清单。工具只接受产品代码中已有入口对应的四个固定文件名，拒绝额外 EXE、链接/重解析文件、空文件和超过 1 GiB 的文件；安装器本身仍须由维护者从可信官方来源取得并完成签名审查，不提交到仓库。

```powershell
python -m scripts.plugin_installer_manifest build --plugin-root "<发布目录>\assets\plugin"
python -m scripts.plugin_installer_manifest verify --plugin-root "<发布目录>\assets\plugin"
```

## 独立媒体运行目录

运行 `python -m scripts.media_runtime initialize --root <媒体运行目录>` 创建布局清单。将目标 Python 环境放在 `_internal/env`，独立环境的入口是 `Scripts/python.exe`。FFmpeg 和 FFprobe 放在 `_internal/env/ffmpeg/bin`。模型及 IndexTTS、WeNet 提供方代码按 `python -m scripts.media_runtime check --root <媒体运行目录>` 的分组清单安装。清单检查关键入口文件，完整依赖、驱动、模型来源和推理能力另行验收。验证过的 Python/CUDA 包版本见 `recovered/requirements-*.txt`。

将该目录填入控制台的运行资源配置。原目录格式也可用于对照验证。独立布局不要求原厂 EXE、启动脚本和原厂应用扩展模块。

可从已获授权的本机参考运行目录准备独立环境。目标必须是新目录，建议预留至少 20 GiB，实际占用取决于参考环境和模型。

```powershell
python -m scripts.stage_media_runtime --reference "<授权参考目录>" --destination "<新媒体目录>"
python -m scripts.media_runtime check --root "<新媒体目录>"
```

此流程复制选定的 Python 和第三方运行环境、提供方源码及模型。将新媒体目录填入控制台配置，使用其中的解释器和依赖。该流程依赖本机已配置的参考资源。输出的 `staging-result.json` 记录解释器重定位和关键入口检查，真实 GPU 推理另行验证。媒体目录保存在仓库外。

使用本地视频直驱时，构建媒体目录须附加 `--include-origin-video`。它会带上直驱所需的 WeNet 提供方和静音特征。已有媒体目录缺少组件时，开播入口会列出缺失文件，可从授权参考目录另建媒体目录并更新控制台设置。

将同一参数附加到下文的 `check` 或 `fingerprint` 命令可纳入直驱组件。`verify` 根据原指纹清单判断是否校验这些文件。

移动媒体目录前，可在可信的原目录生成关键文件指纹，并随介质保存清单。到目标目录后校验，再在控制台更新资源路径。校验覆盖预检列出的 Python、FFmpeg、模型和提供方入口文件。

```powershell
python -m scripts.media_runtime fingerprint --root "<媒体目录>" --inventory "<新清单文件>"
python -m scripts.media_runtime verify --root "<迁移后的媒体目录>" --inventory "<原清单文件>"
```

维护者从已提交版本运行 `python -m scripts.console_package build --output <zip路径>`。使用 `verify --archive <zip路径>` 核对清单，再以 `install --archive <zip路径> --destination <新目录>` 安装。校验用于发现文件损坏，来源仍需通过可信交付渠道确认。

## 版本管理

从当前维护工具所在目录执行以下命令。`--root` 指向同一个独立安装目录。

```powershell
python -m scripts.console_package deploy --root "C:\数字人控制台" --archive console.zip
python -m scripts.console_package run --root "C:\数字人控制台"
python -m scripts.console_package rollback --root "C:\数字人控制台"
```

多店入口使用 `--shop-id <店铺编号>` 隔离数据。可同时使用 `--account-id <账号编号> --access-role viewer|operator|admin` 指定审计身份和限定当前入口权限：只读角色只能查看数据和执行资源预检，运营角色可以控制直播与平台采集，管理员拥有全部写权限。默认账号和角色为 `local` / `admin`，保持单店既有启动方式兼容。授权决策按店写入 `authorization-audit.jsonl`；资源预检是只读操作，不写审计。审计文件达到 4 MiB 后轮换为 `.1`，保留当前代和上一代。账号和角色由受控启动入口指定，`account-id` 只用于归属和审计，不是登录凭据；当前版本尚未提供账号注册、登录、密码或单点登录。

多店工作台中的准备模板保存在安装数据根的共享模板库。模板只包含场次目标、目标人群和本场限制；应用到另一店铺时保留该店铺自己的商品、活动、库存和发货条件。模板名称和通用文本仍由管理员负责脱敏，不应手工填写客户专属价格、活动或账号信息。

首次部署和升级使用同一条 `deploy` 命令。先通过页面退出控制台，再切换版本。各版本保留在 `releases`，用户配置和商品共用 `data`。切换前使用临时数据目录检查候选版本的启动与正常退出，失败时保留当前版本。当前支持同一数据架构的版本切换，跨架构迁移仍待实现。

首次进入控制台后，在设置中保存独立媒体目录并退出。使用下列命令重开，让控制台及其本机设备、图像和推理功能使用已经准备好的媒体环境。也可先通过迁移命令写入媒体目录设置。

```powershell
python -m scripts.console_package run --root "C:\数字人控制台" --with-media
```

已配置独立媒体环境时，升级和回滚也可附加 `--with-media`。候选版本会在隔离数据目录用媒体解释器启动并检查音频设备枚举接口，检查通过后才更新版本指针。

## 迁移已有控制台数据

退出原控制台，在新安装首次部署前运行以下命令。若目标已经存在 `data`，请使用新的安装目录。

```powershell
python -m scripts.console_package migrate-data --source "<原控制台数据目录>" --root "<新安装目录>"
```

迁移保留配置、商品、话术、已登记音色和形象及其选择状态，源数据可继续使用。媒体目录设置保留原路径，搬到另一台机器时按实际位置更新。缓存、运行日志和平台登录态不随迁移复制，到新环境后可重新登录平台。

从 v122 迁移已授权的本地音色和形象时，使用独立媒体环境中的 Python 运行以下命令。音色目录需要 `ref_audio.wav` 和 `ref_text.txt`，形象目录需要成对的 `frames` 和 `positions`。可重复传入 `--voice` 或 `--avatar`，每类只传一个时自动选中，导入多个时可在控制台选择。命令返回原目录名与新素材 ID 的对应关系。

```powershell
python -m scripts.console_package migrate-v122-assets --root "<新安装目录>" --runtime "<独立媒体目录>" --voice "<v122 音色目录>" --avatar "<v122 形象目录>"
```

已取得 v122 直播配置 JSON 时，可用 `migrate-v122-products --root "<新安装目录>" --source "<配置 JSON>"` 导入其中的 `product_scripts`。若同时导入素材，将 `--products "<配置 JSON>"` 加到 `migrate-v122-assets`，整批发布。保存原商品编号、当前商品、话术顺序及原角色信息，导入后请按场次需要选择话术。

旧配置启用多品轮播时，当前商品按清单位置恢复。其余场次按原商品编号恢复。
