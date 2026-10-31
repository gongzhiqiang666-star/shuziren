# v0.1 本地启动与使用

v0.1提供本地运营工作台、PostgreSQL数据、DeepSeek文本接口、本地TTS适配和LiveTalking媒体接口。真实模型效果、目标Windows电脑与淘宝开播必须按独立验收记录确认。首版单操作者、单后端实例运行；应用不能直接暴露到公网。

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
2. 设置数字人的名称、语气与表达要求，添加需要使用的FAQ或人工维护记忆。
3. 创建本地场次。先录入一条人工话术，体验草稿与审核流程。
4. 配置DeepSeek后，可针对所选商品输入问题并生成草稿；审核时核对商品事实。系统不会自动将草稿播出。
5. 配置本地语音服务后，对已审核草稿发起合成，在工作台试听。
6. 配置LiveTalking后，连接数字人预览，将已就绪音频发送到对应媒体会话。
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

首版只采用关键词检索，并明确展示其状态。BGE向量检索、正式淘宝评论同步及自动商品接口属于后续工作，不能把手动输入问题当作平台评论接入。

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

首版预览连接依赖当前工作台页面；离开直播工作台、关闭页面或断开预览后，需要重新建立连接再派发。独立OBS媒体源和关闭管理页后持续输出的链路尚未实现。结束本地场次会返回媒体停止结果；如果停止失败，按界面提示直接在媒体服务或OBS手动停止，并在实际接收端确认。

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
go test ./...
go vet ./...
cd ../web
npm test
npm run build
```

需要真实PostgreSQL集成测试时，为测试进程设置`TEST_DATABASE_URL`，必须指向独立可清理的测试库，不能指向客户资料库。测试数据库与当前应用实例应隔离，避免单实例工作锁互相干扰。

数据库可使用`pg_dump`备份；语音命名卷需要一并保留。`.env`含凭据，应单独妥善保存。升级前先备份，并保留上一个代码版本/镜像；数据库降级兼容性须按实际迁移验证，v0.1不能承诺任意版本可自动回滚。
