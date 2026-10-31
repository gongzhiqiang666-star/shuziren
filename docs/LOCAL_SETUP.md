# v0.2 本地启动与使用

v0.2提供本地运营工作台、PostgreSQL数据、DeepSeek文本接口、本地TTS、BGE检索、独立输出和官方淘宝接口适配。完整操作和故障测试见[本地测试手册](LOCAL_TEST_RUNBOOK.md)。真实模型效果、目标Windows电脑与淘宝开播按独立验收记录确认。本版单操作者、单后端实例运行，默认仅监听本机。

本次代码位于 `codex/local-test-ready`；`main` 尚未合并时，先用 `git clone --branch codex/local-test-ready https://github.com/gongzhiqiang666-star/shuziren.git` 获取完整代码。

## 1. 启动工作台与数据库

安装支持Compose的Docker或Docker Desktop。进入仓库目录后：

Windows PowerShell：

```powershell
./scripts/start-local.ps1
```

Linux、macOS或WSL：

```sh
sh scripts/start-local.sh
```

脚本首次运行会生成随机工作台口令和数据库密码，写入不提交Git的`.env`，后续运行保留已有文件。脚本等待工作台与数据库健康检查通过后打印入口；等待失败时先检查日志。打开`http://127.0.0.1:8765`，使用`.env`中的`APP_TOKEN`进入工作台。语音文件与数据库数据分别保存在Docker命名卷中。修改`.env`后重新运行`docker compose up -d`应用配置。

如启用可选BGE容器，先按[BGE说明](../workers/retrieval/README.md)在`.env`持久设置 `COMPOSE_FILE=compose.yaml,compose.bge.yaml` 与 `COMPOSE_PATH_SEPARATOR=,`；此后启动脚本、上述重启命令以及备份恢复都会保留叠加配置。不要只在第一次启动使用`-f`、之后又运行基础配置。

此命令启动工作台和数据库，不会自动安装CUDA、下载数字人权重或获得淘宝权限。Docker构建、Windows驱动和WSL媒体链路的实际验证状态见交付记录，不能从源码存在推断已经通过。

常用命令：

```sh
docker compose ps
docker compose logs --tail=100 app
docker compose down
```

`down`停止服务并保留命名卷。删除数据卷会丢失本地业务资料，日常停止不使用`down -v`。

## 2. 首次使用顺序

1. 创建店铺，录入至少一个有效商品，价格按界面单位输入并由系统保存为整数分。
2. 设置数字人的名称、语气与表达要求，添加有来源、适用范围与有效期的FAQ/记忆，录入商品活动。
3. 创建本地场次。先录入一条人工话术，或用模板展开当前商品事实，体验草稿与审核流程。
4. 配置DeepSeek后，可针对所选商品输入问题并生成草稿；审核时核对商品事实。系统不会自动将草稿播出。
5. 配置本地语音服务后，对已审核草稿发起合成，在工作台试听。
6. 配置LiveTalking后，为场次签发独立输出链接，在独立浏览器或OBS浏览器源打开；看到音视频播放成功且输出在线后，再发送就绪音频。独立输出启用时管理预览不能抢占它的连接。
7. 需要接管时暂停本地场次并停止数字人；结束本地场次不等于结束淘宝直播。

“已发送”只表示媒体服务确认收到，不等于淘宝端已播出。未知发送结果需要先检查媒体状态，不能重复点击当作必然未发送。

## 3. 配置DeepSeek

在`.env`设置：

```dotenv
DEEPSEEK_API_KEY=填写你自己的接口密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

密钥只由后端读取，不在前端填写或展示，也不进入Git仓库。没有密钥时仍可管理商品、人格和人工草稿，AI生成入口会显示未配置。

未配置BGE时明确使用关键词检索；按[BGE安装说明](../workers/retrieval/README.md)配置后使用真实CPU语义检索。模型缺失或身份变化不会伪装成检索成功。费用页需要运营者填写自己的合同费率，缺费率显示未设置，未知token用量保留为未知。每日token预算使用保守预留，属于本地限制，不是服务商账单余额。

淘宝按[集成契约](INTEGRATIONS_CONTRACT.md)在后端环境配置应用和会话凭据，并将凭据绑定到一个本地店铺UUID。完成本地场次与真实直播间映射后，可手动查询直播间/出售商品、拉取评论、弹卡与上报状态。TMC轮询默认关闭，获准接入后才显式启用；本地评论回放始终标为回放，不会冒充平台消息。

## 4. 配置语音与媒体服务

语音服务的安装、模型和参考音色说明见[本地TTS服务](../workers/tts/README.md)。LiveTalking按该项目对应版本说明准备已授权的闭嘴源视频、头像和模型；本项目不会分发人物素材或模型权重。

工作台使用：

```dotenv
TTS_BASE_URL=http://可从工作台后端访问的语音主机:9880
TTS_API_KEY=与语音服务一致的访问口令
LIVETALKING_BASE_URL=http://可从工作台后端访问的媒体主机:8010
```

若工作台在容器内，`127.0.0.1`指容器自身。访问宿主机可使用`host.docker.internal`，但需要服务监听正确的本地/私有网络接口，并限制访问范围。WSL、Windows及Docker之间的实际网络和音频路由必须按目标机器验证；不建议为省配置直接对公网开放模型服务。

媒体协商使用当前LiveTalking的字符串会话ID。浏览器需要能连接协商出的媒体地址；后端HTTP连得上不代表WebRTC媒体网络一定可达。浏览器的自动播放限制可能需要手动点击播放。

独立输出页拥有自己的WebRTC连接，运营台关闭后仍可继续接收。场次链接使用可撤销的专用口令，不放入工作台管理员口令；同一场次只允许一个接收者，输出在线取决于真实轨道、播放结果和持续心跳。设置方法见[独立输出契约](OUTPUT_CONTRACT.md)。仅使用管理预览时，关闭该预览页仍会断开连接。

同一台主机建议为TTS使用9880、LiveTalking使用8010、原生BGE使用9890，避免端口冲突。容器叠加配置中的BGE使用内部8010端口，不公开到宿主机。

接管或结束本地场次会返回媒体停止结果；如果停止失败，按界面提示直接在媒体服务或OBS手动停止，并在实际接收端确认。实际OBS声音捕获与淘宝接收还需目标机器联调。

画质和口型使用[质量控制方案](AVATAR_QUALITY.md)。工作台中保存的是人工填写的档案和检查记录，不是程序自动证明的验收结果。

## 5. 不使用工作台容器的开发方式

安装Go 1.27.3、Node.js 24、PostgreSQL 16或兼容版本。创建独立开发数据库并提供自己的`DATABASE_URL`。Go服务启动时执行内嵌迁移。

```sh
cd web
npm ci
npm run build
cd ../server
# 在当前终端设置APP_TOKEN、DATABASE_URL等环境变量后执行。
WEB_DIST=../web/dist AUDIO_DIR=./data/audio go run ./cmd/server
```

后端默认监听`127.0.0.1:8080`。开发前端也可在另一个终端执行`cd web && npm run dev`，由Vite代理同源API。不要将`.env`直接当作可信shell脚本执行。

## 6. 验证与备份

```sh
cd server
go test -race ./...
go vet ./...
cd ../web
npm test
npm run build
```

需要真实PostgreSQL集成测试时，为测试进程设置`TEST_DATABASE_URL`，必须指向独立可清理的测试库，不能指向客户资料库。测试数据库与当前应用实例应隔离，避免单实例工作锁互相干扰。

维护窗口停止实际输出后，运行 `python3 scripts/backup_restore.py backup backups/before-upgrade`，再用 `verify`子命令校验。备份包含数据库和音频；恢复需要匹配镜像与显式 `--confirm-replace`，并会暂停场次、撤销输出链接、取消旧任务，避免历史内容重播。完整步骤与失败回退见[测试手册](LOCAL_TEST_RUNBOOK.md)。`.env`、模型权重和授权素材单独保存，不包含在业务备份中；不承诺任意数据库版本之间自动降级。
