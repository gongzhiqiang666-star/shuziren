# v0.2 本地完整测试手册

本手册将“工作台业务可测”“真实本地模型可测”“淘宝实机验收”分别记录。代码和接口测试通过不自动代表人物画质、口型、显卡性能、平台权限或直播效果通过。测试应在专用测试库与虚构商品数据上进行。

## 一、准备与入口

按 [LOCAL_SETUP.md](LOCAL_SETUP.md) 启动 PostgreSQL 和工作台；Windows 可用 PowerShell 启动脚本，Linux/WSL 用 `sh scripts/start-local.sh`。`.env` 中的工作台口令在本机使用，不放入浏览器URL、Git、截图或测试报告。模型与授权人物素材不随仓库分发。

```sh
python3 scripts/doctor.py
# 原生Go服务通常监听8080：
python3 scripts/doctor.py --mode native --url http://127.0.0.1:8080
```

诊断报告默认写到 `test-results/`，只包含服务状态、版本、硬件摘要与是否配置，不包含密钥、完整上游响应或参考音频转写。DeepSeek检查仅判断是否配置，不发起计费请求。未装模型时可以完成商品、人格、知识、活动、人工草稿、历史恢复和权限隔离测试。

需要真实模型测试时，分别按 [CosyVoice安装](../workers/tts/README.md) 与 [BGE安装](../workers/retrieval/README.md) 准备环境；LiveTalking需单独配置可用的授权头像和MuseTalk权重。运行：

```sh
python3 scripts/doctor.py --models
# 如.env中LiveTalking使用容器可解析、宿主机不可解析的地址，显式指定宿主可达地址：
python3 scripts/doctor.py --models --media-url http://127.0.0.1:8010
```

TTS/BGE检查通过认证的工作台诊断API，从实际后端网络访问worker；TTS要求已加载和内容指纹，BGE只有实际配置时才要求就绪，未配置时应显示关键词模式。容器内部的`bge:8010`无需向宿主机公开。LiveTalking的HTTP检查在宿主机执行；如果配置地址是`host.docker.internal`或其他仅容器可达的名字，用`--media-url`提供宿主可达地址。HTTP可达不能证明WebRTC、声音输出和人物效果通过，显卡驱动信息也不能证明模型吞吐达标。

启用BGE叠加配置后，按[BGE说明](../workers/retrieval/README.md)在`.env`持久保存COMPOSE_FILE和COMPOSE_PATH_SEPARATOR，保证启动、诊断、停止和备份恢复都作用于同一组服务。

## 二、业务测试顺序

| 测试 | 操作与预期 |
|---|---|
| 店铺隔离 | 建立测试店A/B，分别录商品。用A的资源ID和B的shop_id调用API，应返回404或明确拒绝，不展示A资料。 |
| 商品事实 | 建立有效商品，生成/录入草稿。改价格、库存、有效期后旧稿应失效，需要重新生成与审核。历史恢复产生新版本，版本号不回退。 |
| 活动 | 为商品录入有效活动，检查业务快照/生成上下文。改变活动价格或到达开始/结束时刻，旧稿不能继续合成或发送。 |
| 人格 | 修改语气与风格，观察用词变化；商品结构化事实仍须保持。恢复历史创建新版本，旧人格草稿不继续执行。 |
| 长期记忆 | 为记忆填写来源，分别设置店铺/商品/场次范围。过期、删除及不匹配范围的记录不进入上下文；删除后历史可恢复并产生新版本。评论不会自动成为长期事实。 |
| 检索 | 未配置BGE时显示关键词模式。已配置BGE时用同义表达测试命中；模型不可用时明确失败，不伪装语义检索成功。 |
| 素材档案 | 录入授权状态、SHA256和模型版本。同类只启用一条，启用新记录使旧记录停用并留历史。档案显示“记录待联调”，不会直接更改进程外模型配置。 |
| 审核 | 草稿必须人工审核后才能合成。缺少资料或模型返回needs_human时不能审批为普通可播稿。 |
| 成本 | 未填写费率时金额显示未设置；填写实际合同费率后按记录tokens估算。失败、取消或返回后草稿失效的请求仍保留用量/未知用量，不能记作免费。 |
| 版本并发 | 两个页面打开同一版本，先后保存；第二次旧版本写入被拒绝，刷新后才能继续。 |

活动、记忆时效、素材版本均进入任务业务指纹。升级前的v0.1旧草稿没有该指纹，需重新生成和审核。

## 三、独立输出与队列

按照 [OUTPUT_CONTRACT.md](OUTPUT_CONTRACT.md) 在运营台签发当前场次输出链接，并在独立浏览器/OBS浏览器源打开。链接内使用场次专用口令，不是工作台管理员口令。设置OBS浏览器源画布与输出配置一致；扩大画布不会自动提升模型的人脸细节。

完成以下链路测试并记录时间和结果：

1. 输出页取得真实音视频轨道、播放成功后才报告在线。仅HTTP协商成功不能视为已播。
2. 合成一条已审核草稿，试听，再发送。实际接收端检查声音和画面。已发送只代表上游接收，不代表播完或淘宝已接收。
3. 关闭运营台，保留独立输出页，确认媒体不中断。打开第二个输出页应提示已有接收实例，不能偷偷顶掉原连接。
4. 断开输出页网络，超过租约时限后后端不得继续派发。网络恢复按真实连接状态重新协商，不自动重播结果不明的任务。
5. 在合成、协商、发送三个阶段分别触发真人接管。场次暂停、epoch变化，旧批次任务取消；实际媒体停止失败必须显示失败并在OBS/模型端人工停止。
6. 恢复场次后重新生成/审核新稿。撤销或轮换输出口令后旧链接失效；结束场次不能用旧链接重新播出。
7. 两条文本完全相同且引擎内容指纹、店铺及事实版本相同的已审核任务可复用音频缓存。换音色/模型/参考音频、改变活动/商品/人格/记忆后，不得使用旧缓存冒充新合成。

按 [AUTOMATION_CONTRACT.md](AUTOMATION_CONTRACT.md) 在调度页设置优先级、截止时间与单次定时派发。使用一分钟后的计划验证真实调度，断开独立输出后再验证计划失败且不补播；接管/结束应取消旧计划。自动调度也必须经过相同审核、有效期、租约和epoch检查，网络中断后状态不明的发送不自动重试。

## 四、音画传输校准

校准工具产生黑白闪光和同一时间点的蜂鸣，用于检测录制所覆盖链路的音视频时间偏差。它不测量人物发音口型，也不能检测牙齿、嘴周融合或形象失真。

```sh
python3 scripts/media_calibrate.py generate test-results/reference.mkv --fps 25
# 将参考片作为OBS媒体源，按实际使用的输出/录制路径完整录下12秒。
# 保持校准画面铺满输出，不混入音乐、旁白或额外闪光。
python3 scripts/media_calibrate.py analyze test-results/recording.mkv --output test-results/transport-sync.json --fps 25 --target-ms 80
```

若校准画面仅占录制的一块区域，使用经过确认的 `--crop 宽:高:x:y`。工具要求识别到5组、间隔约2秒的闪光/蜂鸣，缺失或多出事件时拒绝给出成功结果。JSON中正偏差表示声音晚于画面；25fps的画面时间分辨率为40ms，声音检测窗口为5ms。80ms是本项目初始工程验收目标，可在客户目标确定后调整，不是人物口型质量评分。

工具自测支持注入已知偏移：

```sh
python3 scripts/media_calibrate.py generate test-results/late-120ms.mkv --audio-offset-ms 120
python3 scripts/media_calibrate.py analyze test-results/late-120ms.mkv --output test-results/late-120ms.json
```

该示例应报告约+120ms并返回退出码2（超出80ms目标）；0表示目标内，1表示无法可靠测量。实际录制必须重新测量，不能用合成参考片的0ms结果代替客户链路验收。

## 五、逐头像口型与细节验收

[lip_sync_50.json](../fixtures/lip_sync_50.json) 含50条自编测试语料，覆盖双唇音、唇齿音、开口/圆唇、平翘舌、鼻音、多音字、数字、单位、英文、长短停顿与接管恢复。文字中的商品和金额都是测试值。

对每个计划交付的头像/音色组合完成全部语料。每条先合成实际CosyVoice音频，保存该WAV与引擎指纹；由同一份音频驱动LiveTalking/MuseTalk，录下实际输出。禁止分别生成两份音频用于“声音”和“嘴部驱动”。

记录头像资产SHA256、引擎指纹、模型版本、画布/fps、视频路径、审阅人和结果。先检查读音和停顿，再用慢放与逐帧审阅检查闭唇时刻、嘴角撕裂、牙齿重复/闪烁、下颌变形、肤色边界、眼部稳定及停顿时无声张嘴。传输校准合格后仍须逐条人工口型审阅。发现异常先改源素材/裁剪/发音，复测同一条及相邻音素，避免以过度锐化掩盖嘴周问题。

工作台质量表是人工验收记录；只有该头像在对应机器/版本完成测试，才能勾选相关项。未测项目保持未通过。

## 六、淘宝与长时间测试

使用本地事件回放先验证去重、队列、人工审核、异常处理与接管。真实淘宝对接要求已经获批的应用、会话凭据、直播权限和实际直播间；本地回放必须始终显示回放来源。真实评论获取成功、媒体在浏览器可见与淘宝端收到音画是不同的测试结果。

在目标显卡电脑持续运行8小时，记录每小时显存/RAM、生成与合成时延、失败数、租约状态、待处理任务数量及发送结果不明数。测试中按计划安排断网、模型重启、工作台重启、接管/恢复和费用预算触发。没有运行8小时就不记录“8小时通过”。实际性能指标以目标机器记录为准，不由显卡型号或HTTP成功推断。

## 七、一致备份与恢复

在维护窗口停止实际直播/OBS输出，再运行备份。脚本停止app后分别取得PostgreSQL自定义格式转储与音频卷，写入逐文件SHA256清单；原先运行的app会在finally中重新启动。`.env`、授权素材和外部模型权重需单独保管，业务备份本身包含店铺与记忆资料。

```sh
python3 scripts/backup_restore.py backup backups/before-upgrade
python3 scripts/backup_restore.py verify backups/before-upgrade
```

恢复要求匹配的app镜像，并明确传入替换参数。脚本先验证文件完整性，再自动备份当前状态，然后以数据库单事务恢复并替换音频。恢复后所有未结束场次暂停、epoch递增、输出口令撤销、旧任务取消、在途发送标为结果不明，防止历史备份自动重播。运营人员重新核对资料并恢复场次，重新签发输出链接。

```sh
python3 scripts/backup_restore.py restore backups/before-upgrade --confirm-replace
```

只恢复自己控制、来源可信的备份。恢复失败会尝试使用 `before-restore-*` 快照回退；若回退也失败，app保持停止，先人工恢复再继续写入。镜像不匹配时脚本拒绝自动数据库降级，应先准备匹配的旧镜像。维护锁避免并行备份/恢复；异常退出留下 `.backup-restore.lock` 时，先确认没有维护进程再移除锁。

脚本的故障路径使用隔离替身测试；真实Docker备份/恢复是否通过必须以CI或目标机器执行记录为准。目标Windows/WSL路径、Docker卷权限仍需在目标机复测。

## 八、开发验证命令与证据

```sh
cd server
# TEST_DATABASE_URL必须指向独立测试数据库。
go test -race ./...
go vet ./...
cd ../web
npm ci
npm test
npm run build
cd ..
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

TTS与BGE各自在独立Python环境运行自己的测试，不把模型CPU替身测试标为GPU推理完成。交付记录应列实际命令、版本、日期、成功/失败、未测原因和报告路径。

命令依据：[Docker Compose cp](https://docs.docker.com/reference/cli/docker/compose/cp/)、[Compose stop](https://docs.docker.com/reference/cli/docker/compose/stop/)、[PostgreSQL 16 pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html)、[FFmpeg滤镜说明](https://www.ffmpeg.org/ffmpeg-filters.html)。本仓库脚本中具体阈值、测试语料和恢复失效策略均是项目实现选择。
