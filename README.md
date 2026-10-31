# shuziren · 淘宝数字人本地工作台

v0.1 是可以本地运行的单操作者开发版：管理商品、人格和知识，准备并审核话术，调度本地语音，连接 LiveTalking 预览与人工接管。业务数据保存在 PostgreSQL；DeepSeek 是唯一接入的按量付费 AI 服务。

首版没有获得或模拟淘宝正式授权，也不把媒体接口测试当作真实数字人画质通过。实际验证结果和待完成项见[交付记录](docs/IMPLEMENTATION_STATUS.md)。

## 第一版可以做什么

| 模块 | 当前实现 |
| --- | --- |
| 本地工作台 | Vue 3 + TypeScript 中文界面，口令认证，多店配置，单操作者 |
| 商品事实 | 名称、SKU、规格、价格、库存、启停和有效期；金额以整数分保存，编辑产生版本 |
| 品牌人格 | 名称、语气、表达规则和版本；FAQ、人工维护记忆可增删改 |
| 话术审核 | 人工草稿或 DeepSeek JSON 草稿；需要人工确认后才能合成，未知信息转人工 |
| 队列与接管 | PostgreSQL 持久队列；版本与批次校验；取消、暂停接管、恢复及本地结束 |
| 本地语音 | CosyVoice3 真实调用包装；认证、格式校验、单路合成，无模型时明确不可用 |
| 媒体连接 | LiveTalking WebRTC 协商、同一份 WAV 上传与打断；派发结果不明时禁止自动重播 |
| 画质核验 | 源素材、模型、输出画布、帧率/同步目标和逐项证据记录；人工档案，不是自动测量 |

商品、人格或知识改变后，旧上下文任务不能继续通过审核或派发。接管增加场次批次号，迟到结果不写成可播放音频。媒体“已接收”只表示上游 HTTP 确认，实际播放仍需在接收端核验。

## 快速启动

安装支持 Compose 的 Docker / Docker Desktop，进入仓库目录。

Windows PowerShell：

```powershell
./scripts/start-local.ps1
```

Linux、macOS、WSL：

```sh
sh scripts/start-local.sh
```

首次执行会生成 `.env` 中的随机工作台口令和数据库密码。打开 **http://127.0.0.1:8765**，使用 `.env` 中的 `APP_TOKEN` 登录。此入口默认仅本机可用。

该步骤启动工作台和数据库。没有配置模型服务时，可以先录入商品、配置人格、创建人工草稿并审核；页面会显示 DeepSeek、语音和媒体的未配置状态。配置方法、原生开发启动及备份方式见[本地启动说明](docs/LOCAL_SETUP.md)。

> Docker / Windows 与真实 GPU 的验证状态单独记录在交付记录中；启动文件存在不代表这些目标环境已经通过实测。

## 模型和淘宝的边界

- DeepSeek 只生成文本，由后端读取用户自己的 API Key。不会把 Key 放进浏览器或仓库。
- 本地语音安装见 [workers/tts](workers/tts/README.md)；接口协议见 [media](server/internal/media/README.md)。模型权重和授权人物/声音素材需要另外准备。
- v0.1 使用关键词检索；BGE 向量检索继续保留在完整路线中。
- 淘宝评论、商品同步、弹卡和获准开播链路尚未接入，人工输入问题不是自动评论功能。
- 当前 WebRTC 预览依赖工作台页面。独立 OBS 媒体源与关闭管理页后持续输出的链路尚未实现；不能把首版预览当作无人值守直播输出。
- 第一版单后端实例运行，启动时使用数据库锁防止重复消费。多店配置不等于多用户 SaaS 权限。

## 目录

```text
server/              Go / Gin 服务、迁移、持久队列与适配器
web/                 Vue 工作台与前端测试
workers/tts/         CosyVoice3 HTTP 包装与无 GPU 边界测试
scripts/             Windows / POSIX 本地启动脚本
docs/                计划、质量控制、接口与交付记录
```

## 开发资料

- [完整开发计划与 WBS](docs/DEVELOPMENT_PLAN.md)
- [v0.1 接口契约](docs/MVP_CONTRACT.md)
- [本地启动与操作](docs/LOCAL_SETUP.md)
- [交付状态与验证记录](docs/IMPLEMENTATION_STATUS.md)
- [画质、细节与口型控制](docs/AVATAR_QUALITY.md)
- [完整产品验收清单](docs/ACCEPTANCE.md)
- [依赖和许可记录](docs/DEPENDENCIES.md)
- [GitHub 提交安排](docs/GITHUB_WORKFLOW.md)

完整产品工程预算仍为 320 小时基础工作 + 64 小时联调返工。v0.1 完成的是首个可运行切片，目标 Windows 电脑、GPU、淘宝账号和客户试点继续按原计划推进。
