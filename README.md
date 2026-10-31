# shuziren · 淘宝数字人本地工作台

v0.2 提供完整的本地测试工作流：维护商品与活动、管理有来源的人格记忆、生成并审核话术、安排语音任务、通过独立输出页接收媒体，以及接管和恢复。业务数据保存到 PostgreSQL，DeepSeek 是唯一远程 AI 提供者；CosyVoice3、BGE 和 LiveTalking/MuseTalk 在本地运行。

软件验证、真实模型验证和淘宝实播分别记录在[交付状态](docs/IMPLEMENTATION_STATUS.md)。本地工作台可以先运行，模型权重、授权人物/声音素材、DeepSeek Key 和淘宝应用权限由实际部署环境提供。

## 已实现的本地功能

| 模块 | 功能 |
| --- | --- |
| 中文工作台 | Vue 3/TypeScript、同源 API、管理口令、多店资料、单操作者 |
| 商品与活动 | SKU、整数分金额、库存、启停、有效期、版本与历史恢复；活动到期会使旧稿失效 |
| 人格与记忆 | 名称、语气、表达规则、历史恢复；FAQ/记忆的来源、店铺/商品/场次范围、有效期、删除与恢复 |
| 话术模板 | 将当前商品事实展开成草稿，模板版本控制，不执行脚本，不自动审核 |
| 本地检索 | 默认明确的关键词模式；可选真实 BGE CPU 语义检索和持久化向量缓存 |
| 生成与费用 | DeepSeek JSON 草稿、可信 token 用量、未知用量、运营者费率估算；请求并发、速率及每日保守额度 |
| 队列与计划 | 人工审核、优先级、截止时间、单次定时派发；重启不补播错过的任务 |
| 语音与缓存 | CosyVoice3 真实推理包装；固定授权参考声音；引擎内容指纹和 WAV 完整性核验，跨任务缓存隔离 |
| 独立输出 | OBS 浏览器源；场次专用可撤销口令、单接收者租约、真实 WebRTC/播放状态心跳；运营台关闭不影响独立接收页 |
| 淘宝适配 | 官方 TOP 签名、直播间详情、出售商品预览、显式弹卡/状态上报、TMC HTTP 消费与确认、事件去重及本地回放 |
| 质量与运维 | 资产版本档案、人工质量核验、50句口型语料、闪光蜂鸣传输校准、配置诊断、带校验与回退的备份恢复 |

商品、人格、记忆、活动、素材、任务期限与场次批次在审核、合成和派发时重新校验。接管会让旧批次失效；未知派发不会自动重试。`sent` 表示媒体服务接受上传，实际播出需检查 OBS 和淘宝接收端。

## 快速启动

在已安装 Docker/Compose 的电脑上获取本次代码。若 `main` 尚未合并开发分支：

```sh
git clone --branch codex/local-test-ready https://github.com/gongzhiqiang666-star/shuziren.git
cd shuziren
```

Windows PowerShell：

```powershell
./scripts/start-local.ps1
```

Linux、macOS 或 WSL：

```sh
sh scripts/start-local.sh
```

首次运行生成 `.env` 中的随机口令和数据库密码。打开 **http://127.0.0.1:8765**，使用本机 `.env` 的 `APP_TOKEN` 登录。默认只监听本机。该命令启动工作台和数据库，不会自动下载模型或开始淘宝直播。

先录入虚构测试商品、场次、活动和知识，走通人工草稿/审核及评论回放。完成后按[本地完整测试手册](docs/LOCAL_TEST_RUNBOOK.md)配置模型、独立输出与目标机器验收。运行诊断：

```sh
python3 scripts/doctor.py
```

## 模型、资产与部署说明

- DeepSeek 生成文本；Key只放后端环境，不进入浏览器。未配置时可使用人工草稿与模板。
- [CosyVoice3](workers/tts/README.md)生成同一份用于试听和嘴部驱动的 WAV；[LiveTalking](server/internal/media/README.md)提供数字人媒体。真实 CUDA 环境、人物素材与声音仍需实机安装和验证。
- [BGE](workers/retrieval/README.md)可在CPU运行，提供可选容器叠加文件 `compose.bge.yaml`。本地精确余弦排名使用PostgreSQL数组缓存，不强制安装pgvector；大规模索引优化仍属后续工作。
- 资产台账记录授权、版本与SHA256；台账编辑不会直接切换进程外的头像/音色。实际切换由本机模型服务配置与重启完成，再核对引擎指纹。初期每个媒体服务配置固定头像/音色、同时验证一路输出。
- 淘宝的配置状态、HTTP协议成功、浏览器收到媒体、OBS采集与淘宝实播是不同证据。接口需要应用实际权限；本地回放始终标为回放。评论不会绕过审核直接播报。
- 单操作者可管理多店资料；不提供多用户 SaaS 角色授权。若向局域网/公网开放，应另行设计身份认证与网络部署。

## 测试与恢复

```sh
cd server && go test -race ./... && go vet ./... && cd ..
cd web && npm ci && npm test && npm run build && cd ..
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/backup_restore.py backup backups/before-upgrade
python3 scripts/backup_restore.py verify backups/before-upgrade
```

Go数据库测试需显式设置专用 `TEST_DATABASE_URL`；未设置会跳过数据库测试，不能因此声称数据库路径已验收。真实浏览器测试说明见 [tests/browser](tests/browser/README.md)。备份恢复须在维护窗口执行，恢复要求显式 `--confirm-replace`，会暂停场次、撤销旧输出链接并取消旧任务，防止历史内容突然重播。

## 文档

- [当前交付状态与证据](docs/IMPLEMENTATION_STATUS.md)
- [完整开发计划](docs/DEVELOPMENT_PLAN.md)与[本地测试范围](docs/LOCAL_TEST_CONTRACT.md)
- [启动说明](docs/LOCAL_SETUP.md)与[完整测试手册](docs/LOCAL_TEST_RUNBOOK.md)
- [独立输出](docs/OUTPUT_CONTRACT.md)、[业务版本](docs/BUSINESS_CONTRACT.md)、[限额/缓存/调度](docs/AUTOMATION_CONTRACT.md)、[话术模板](docs/TEMPLATES_CONTRACT.md)、[淘宝与检索](docs/INTEGRATIONS_CONTRACT.md)
- [画质、细节与口型方案](docs/AVATAR_QUALITY.md)、[验收清单](docs/ACCEPTANCE.md)、[依赖与许可](docs/DEPENDENCIES.md)
