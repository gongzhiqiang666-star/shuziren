# 交给本地 Codex：部署并验证低端 3D 版本

本手册对应 `codex/low-end-3d-preview` 分支的 `/avatar3d`。目标是在你自己的电脑上显示真正的三维人物，输入实际声音，检查口型、播放和录像。GitHub 默认分支不一定已合并这项功能，获取代码时须明确指定分支。

本次只启动 3D 验证页，使用录音或 WAV 即可。所需软件是 Git、Node.js/npm、Python 3.10+ 和支持 WebGL2 的桌面浏览器。建议使用已验证的 Node.js 24；不要求 NVIDIA/CUDA、Docker、PostgreSQL、DeepSeek Key 或 CosyVoice 服务。浏览器图形能力仍会影响实际帧率。

## 1. 直接复制给本地 Codex

```text
请在当前这台电脑上实际部署并运行 shuziren 的低端 3D 本地验证版，完成安装、启动和能执行的验证。

仓库：https://github.com/gongzhiqiang666-star/shuziren.git
分支：codex/low-end-3d-preview
部署手册：docs/CODEX_LOCAL_DEPLOY.md

先检查操作系统、CPU 架构、Git、Node/npm、Python 的实际版本；优先复用可用运行时，推荐 Node.js 24，源码准备需要 Python 3.10+。

在新的独立目录获取指定分支。若当前已有工程，先检查路径、分支和 git status；存在未提交改动或其他工作时另建克隆目录，保留原工程。不要重置、清空、自动 stash 或覆盖用户文件。

读取仓库实际存在的 AGENTS.md / CLAUDE.md，以及 README.md、docs/CODEX_LOCAL_DEPLOY.md、docs/AVATAR3D_LOCAL.md、docs/AVATAR3D_IMPLEMENTATION_STATUS.md。按部署手册执行：
1. 使用已有准备脚本下载并校验 CC0 人物，安装锁文件对应的前端依赖。
2. 执行前端测试和生产构建，记录每条命令的退出码。
3. 用 node scripts/serve_avatar3d.mjs 启动本机服务。默认 5173，冲突时换空闲端口，保留其他项目进程。
4. 检查 /avatar3d、人物文件和声学资源；如果能使用浏览器，实际确认人物显示、旋转、手动嘴形、WAV 导入、播放/暂停/拖动以及录像导出。不能操作浏览器时，明确列为待人工验证，不能把 HTTP 200 当成画面验收。
5. 首轮使用本地录音或 WAV。麦克风授权、中文嘴形观感和真人感由我在现场确认；不要自动配置付费 API 或开始淘宝直播。
6. 把真实部署报告写到 test-results/local-deploy/DEPLOYMENT_REPORT.md，包括工程目录、分支/提交、系统/依赖版本、命令与退出码、访问地址、服务进程/会话、停止方式、已验证项、未验证项及真实错误。不要记录密钥或客户音频内容到 Git。
7. 完成后保留本地预览服务供我使用，并告诉我准确打开哪个地址；如果工具不能持续保留进程，给我在普通终端执行的启动命令，并明确说明当前服务已停止。

按真实结果执行，不要只给操作建议。出现错误先定位并使用本文恢复步骤；有权限或网络阻塞时完成其余检查并说明具体缺项。本次只做本地部署，不需要另外提交、推送、合并或发布。
```

## 2. 先确认本机环境

macOS / Linux：

```sh
git --version
node --version
npm --version
python3 --version
```

Windows PowerShell：

```powershell
git --version
node --version
npm.cmd --version
py -3 --version
```

Windows 没有 `py` 时，继续确认 `python3 --version` 或 `python --version` 哪个确实能运行；后续用实际可用的 Python 3.10+ 命令。仅存在 Windows Store 的命令别名不代表 Python 已可运行。

启动脚本目前接受 Node.js 20.19+、22.12+ 或 24+；本项目本轮使用 24 系列。若电脑已有其他项目依赖特定版本，优先用本机已有版本管理器切换当前终端的运行时。不要为了这一个预览升级其他工程的依赖或更改全局 Python。

缺少前置软件时，可从 [Git](https://git-scm.com/downloads)、[Node.js](https://nodejs.org/en/download)、[Python](https://www.python.org/downloads/) 官方站点选择对应系统/架构的安装包。按照当前电脑及本地 Codex 的权限完成安装；被权限或网络阻塞时，报告实际缺项。

## 3. macOS / Linux：从 GitHub 部署

在你准备用来保存项目的目录执行。以下 `shuziren-local-3d` 必须是尚不存在的新目录；如果同名目录已存在，另选一个名字。每一步成功后再执行下一步。

### 获取代码

```sh
git clone --branch codex/low-end-3d-preview --single-branch https://github.com/gongzhiqiang666-star/shuziren.git shuziren-local-3d
cd shuziren-local-3d
git branch --show-current
git rev-parse HEAD
git status --short
```

确认分支名为 `codex/low-end-3d-preview`。将真实提交 SHA 写入部署报告，不把旧聊天中的 SHA 当成当前代码。

### 准备资源和依赖

```sh
sh scripts/start-avatar3d.sh --prepare-only
```

该步骤会：

- 检查 Node/npm/Python 是否可用。
- 下载固定版本的 CC0 人物，约 36.8 MB，并核对文件大小与 SHA256。
- 在 `web` 目录执行 `npm ci`，安装锁文件指定的依赖。

首次需要访问 GitHub 原始资源和 npm。声学模型已随仓库提交，Python 仅用作资源准备，不需要安装 Python 推理框架。

### 测试与构建

```sh
npm --prefix web test
npm --prefix web run build
```

构建后应存在 `web/dist/index.html`、`web/dist/avatar-assets/mpfb.glb` 和 `web/dist/vendor/headaudio/dist/model-en-mixed.bin`。

### 启动正式预览

```sh
node scripts/serve_avatar3d.mjs --port 5173
```

在浏览器打开 **http://127.0.0.1:5173/avatar3d**。这个终端会持续运行服务，保持它打开；结束时按 `Ctrl+C`。

本手册先构建再使用仓库静态服务，覆盖实际交付所使用的资源路径和 CSP。需要开发热更新时，可在资源准备后运行 `npm --prefix web run avatar3d`；两种服务不要同时使用同一个端口。

## 4. Windows PowerShell：从 GitHub 部署

同样选择不存在的新目录，并逐步检查成功结果。

```powershell
git clone --branch codex/low-end-3d-preview --single-branch https://github.com/gongzhiqiang666-star/shuziren.git shuziren-local-3d
Set-Location shuziren-local-3d
git branch --show-current
git rev-parse HEAD
git status --short
```

准备、测试、构建、启动，依次执行：

```powershell
powershell -File scripts/start-avatar3d.ps1 --prepare-only
npm.cmd --prefix web test
npm.cmd --prefix web run build
node scripts/serve_avatar3d.mjs --port 5173
```

每条外部命令返回后可以用 `$LASTEXITCODE` 查看退出码，非 0 时先处理该步错误。启动服务后该终端会被占用，这是正常状态。

### PowerShell 策略阻止脚本时

直接执行等价命令，无须更改全局执行策略：

```powershell
py -3 scripts/avatar3d_setup.py
npm.cmd --prefix web ci
npm.cmd --prefix web test
npm.cmd --prefix web run build
node scripts/serve_avatar3d.mjs --port 5173
```

若当前可用的是 `python3` 或 `python`，使用它替换上面的 `py -3`。浏览器访问地址同样为 **http://127.0.0.1:5173/avatar3d**。

## 5. 实际验证顺序

| 检查 | 怎么做 | 应记录的结果 |
| --- | --- | --- |
| 页面和资源 | 打开 `/avatar3d`，等待内置人物加载 | 页面地址、人物是否出现、是否有明确错误；不能只记 HTTP 200 |
| 真正三维 | 拖动旋转，滚轮缩放，再重置视角 | 是否能从不同角度观察网格；材质是否完整 |
| 嘴部绑定 | 依次点击闭唇、唇齿、张口、圆唇 | 嘴唇、牙齿及下颌有没有明显异常 |
| 实际音频 | 导入自己的 WAV，或由用户点击录音并授权麦克风 | 文件能否分析、声音是否能播放；WAV 最长 5 分钟/32 MiB，录音最长 60 秒 |
| 播放控制 | 播放、暂停、拖动、重播 | 嘴形是否跟随当前声音位置，停顿是否自然 |
| 成片 | 录制人物与声音，下载后用本机播放器打开 | 声音、连续画面、流畅度和音画同步分别检查；有音视频轨道不等于质量合格 |
| 性能 | 保持人物可见，观察正常观看尺寸下的帧率 | 电脑配置、浏览器、画面尺寸、实际帧率；软件渲染结果单独注明 |
| 保存证据 | 导出页面验证记录，并保留一段实际中文样片 | 保存到本机测试输出目录，不自动加入 Git |

建议先说 20～30 秒中文，包含“爸爸、妈妈、杯子、服务、五百、保温”及几处停顿。查看 [AVATAR3D_LOCAL.md](AVATAR3D_LOCAL.md) 了解校准、轨道和 OBS 窗口采集。

**当前内置人物仍有 CG 感，声学模型以英语训练。** 页面运行成功、轨道绑定成功不能代替中文精细嘴形和真人感验收。浏览器录制要实际回放检查；目标电脑帧率、OBS 采集、自动业务派发和淘宝实播仍属独立验收项。

## 6. 本地 Codex 可选的自动浏览器验收

能使用浏览器工具时优先直接检查目标电脑上的页面。仓库还提供可复跑的 `tests/browser/avatar3d.cjs`；它使用合成测试音检查技术链路，不是中文观感测试。

先保持正式静态服务在运行，然后在**另一终端、同一工程根目录**准备 Playwright：

```sh
npm --prefix tests/browser ci
```

进入 `tests/browser`，执行 `npx playwright install chromium`，再返回工程根目录。Windows 可对应使用 `npm.cmd` 和 `npx.cmd`。安装浏览器需要联网；无法下载时记录该项未执行，并继续人工页面验证。

macOS / Linux：

```sh
AVATAR3D_BASE_URL=http://127.0.0.1:5173 npm --prefix tests/browser run test:avatar3d
```

Windows PowerShell：

```powershell
$env:AVATAR3D_BASE_URL = 'http://127.0.0.1:5173'
npm.cmd --prefix tests/browser run test:avatar3d
```

端口与实际服务保持一致。默认使用 Playwright 安装的 Chromium；必要时用 `BROWSER_EXECUTABLE` 指定真实浏览器可执行文件，或用 `PLAYWRIGHT_MODULE` 指定已有 Playwright 模块。

正常目标机测试不要强制软件渲染。仅在没有可用 GPU 的隔离环境中显式使用 `AVATAR3D_SOFTWARE_GL=1`，并在报告中说明；该模式不能测量用户电脑的核显/独显性能。安装了 FFmpeg 时，脚本额外调用 `ffprobe` 检查录像双流；没安装时单独标记该项未执行。

查看 `test-results/avatar3d/result.json`：`passed` 对应退出 0；不支持原生录制时会报告 `incomplete`、退出 2；失败返回非零值并留下诊断。详细范围见 [浏览器验收说明](../tests/browser/README.md)。

## 7. 常见问题与恢复

| 现象 | 处理方法 |
| --- | --- |
| 目录里找不到 `avatar3d` 文件 | 核对远端归属、分支和提交；使用指定开发分支，保留原工程后另建目录获取 |
| Node/npm/Python 命令不存在或版本不符 | 修复当前终端的运行时；安装后重新打开终端，执行版本检查；Windows 继续探测真实可用 Python |
| 5173 被占用 | 用 `node scripts/serve_avatar3d.mjs --port 5174`，访问对应的 `/avatar3d`；不要结束未知进程 |
| 给启动脚本传 `--port` 被拒绝 | `.sh/.ps1` 只接受 `--prepare-only` 和 `--no-sample`；换端口参数应传给 `serve_avatar3d.mjs` |
| 人物下载超时或网络不通 | 检查对固定 GitHub 原始地址的访问，然后重跑准备脚本；不要更改固定版本或关闭哈希校验 |
| 已有下载 ZIP，希望复用人物 | 将 ZIP 的 `app/avatar-assets/mpfb.glb` 复制到源码 `web/public/avatar-assets/mpfb.glb`，保留原有未知文件，再运行准备脚本校验 |
| 准备脚本提示已有其他内容 | 保留现有文件，先另存至自己的素材目录；脚本不会覆盖非固定样例内容 |
| 采用 `--no-sample` 后没有内置人物 | 这是跳过下载的预期结果，需要在页面导入符合要求的自包含 GLB；不能据此声称内置样例验收通过 |
| 样例已经下载，正式页面仍找不到它 | 样例准备后重新执行 `npm --prefix web run build`；静态服务读取的是 `web/dist` |
| `npm ci` 网络失败 | 按实际网络错误修复连接后重试，保留锁文件；不要用删除锁文件、强制升级依赖或关闭 TLS 校验掩盖错误 |
| 人物空白、没有纹理或提示 WebGL 问题 | 检查浏览器图形能力、硬件加速、页面错误及模型是否完整；使用最新代码的正式静态服务，不用 `file://` 打开 HTML |
| 录音没有权限 | 用户在本机浏览器/系统中允许麦克风；也可先导入 WAV 验证其他路径，不使用替身录音声称麦克风已通过 |
| 录像卡顿或像静止画面 | 保持人物画布可见，检查浏览器图形加速及实际帧率，回放成片；将持续采帧、流畅度、音画同步分开记录 |
| Codex 完成后地址打不开 | 确认本地服务进程是否已退出；在普通终端重新执行启动命令并保留窗口 |

## 8. 重启、已有源码与部署报告

已安装且源码未变化时，进入同一工程目录，直接运行：

```sh
node scripts/serve_avatar3d.mjs --port 5173
```

更新源码之前先检查 `git status --short`。当前目录干净且已在目标分支时，可以使用 `git pull --ff-only origin codex/low-end-3d-preview`；有修改、分支不同或快进失败时，保留现场，另建目录部署。源码更新后重新准备资源与依赖，再测试和构建。

`test-results/` 已被 Git 忽略。本地 Codex 把部署报告写到 `test-results/local-deploy/DEPLOYMENT_REPORT.md`，建议格式：

```text
部署结论：成功 / 部分完成 / 阻塞
验证机器：操作系统、架构、CPU/GPU/内存（按实际可得信息）
工程绝对路径：
分支与提交 SHA：
Node/npm/Python/Git 版本：

实际命令、工作目录、退出码、关键结果：
资源准备：
依赖安装：
前端测试：
生产构建：
启动：
浏览器验证：

访问地址：
服务是否仍在运行、PID或工具会话：
停止或再次启动方式：
样片、截图、验证记录路径：
中文观感 / 目标帧率 / 麦克风 / 录像 / OBS 分项结果：
未执行项与原因：
实际错误、恢复操作与剩余阻塞：
```

现有发布包与源码部署入口不同：发布包使用 `node start.mjs --dir app`；源码工程使用 `node scripts/serve_avatar3d.mjs`。完整高端工作台的 Docker/数据库/模型部署另见 [LOCAL_TEST_RUNBOOK.md](LOCAL_TEST_RUNBOOK.md)，不属于这轮 3D 本地预览的前置步骤。

## 9. 本手册编写时的全新部署复跑

2026-10-31，实际从 GitHub 重新克隆 `codex/low-end-3d-preview`，应用提交为 [`b43f8e15da670f87a5c9477e90239e12e4c34fbc`](https://github.com/gongzhiqiang666-star/shuziren/commit/b43f8e15da670f87a5c9477e90239e12e4c34fbc)。新克隆最初没有 `node_modules` 或人物 GLB；声学二进制模型已正确包含在 Git 中。以下没有复用旧目录的已安装依赖或人物文件。

环境：隔离 Linux x86_64、Node.js 24.22.1、npm 11.9.0、Python 3.12.14、Chromium 156.0.8078.80。**这不是用户的 Mac/Windows 真机。** 浏览器使用 SwiftShader 软件渲染，不代表目标电脑的硬件性能。

| 实际步骤 | 退出码 / 结果 |
| --- | --- |
| `git clone --branch codex/low-end-3d-preview --single-branch ...` | 0；真实获取上述提交 |
| `sh scripts/start-avatar3d.sh --prepare-only` | 0；实际下载 36,815,920 字节人物并通过固定 SHA256；`npm ci` 成功安装 130 个包 |
| `npm --prefix web test` | 0；14 个文件、78 项通过 |
| `npm --prefix web run build` | 0；类型检查与生产构建完成；体积提示不影响退出成功 |
| `node scripts/serve_avatar3d.mjs --port 5187` | 实际监听 `127.0.0.1:5187`，正式页面及资源可访问 |
| `AVATAR3D_BASE_URL=http://127.0.0.1:5187 node tests/browser/avatar3d.cjs` | 0；9 组真实浏览器检查通过，脚本异常、控制台及网络错误均为 0 |
| 退出与清理 | 停止本次预览服务，确认端口不再监听；源码工作树保持干净 |

浏览器命令同时使用已安装的 `PLAYWRIGHT_MODULE`、`BROWSER_EXECUTABLE` 和 `AVATAR3D_SOFTWARE_GL=1`。结果写入新克隆目录的 `test-results/avatar3d/result.json`。原生录像生成 78,272 字节文件，ffprobe 确认 VP9 与 Opus 双流；该低帧率软件环境不能证明成片流畅或音画观感合格。

本次说明新增部署文档，未改变上述应用实现。目标机器麦克风、中文精细口型、真人感、录像流畅度、OBS 及淘宝实播仍需按本手册分别记录。此前同一应用提交的独立 GitHub 检查见 [Actions 结果](https://github.com/gongzhiqiang666-star/shuziren/actions/runs/41200055824)。
