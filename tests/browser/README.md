# 真实浏览器验收

## 低端 3D 本地预览

`avatar3d.cjs` 只需已构建的前端和本地静态服务，不启动 Go、数据库或模型服务。它实际加载固定 CC0 GLB、比较旋转和嘴形的渲染结果、运行本地声学 Worker、核对音频哈希与播放时间轴，并使用浏览器原生 MediaRecorder 导出带音视频的录像。

```sh
python3 scripts/avatar3d_setup.py
npm --prefix web ci
npm --prefix web run build
npm --prefix tests/browser ci
cd tests/browser && npx playwright install chromium && cd ../..
node scripts/serve_avatar3d.mjs --port 5174
```

保持服务运行，在另一终端执行：

```sh
AVATAR3D_BASE_URL=http://127.0.0.1:5174 npm --prefix tests/browser run test:avatar3d
```

`PLAYWRIGHT_MODULE`、`BROWSER_EXECUTABLE` 可指定已有运行环境；无物理 GPU 的 CI 可显式设置 `AVATAR3D_SOFTWARE_GL=1`。安装 FFmpeg 后，脚本还会用 `ffprobe` 检查录像文件确有音视频双流。录像接口不可用会记录未验收并返回非零值，不使用替身录像。

结果、截图和样片写入 `test-results/avatar3d/`，不提交 Git。测试输入是合成 PCM 音调，只证明本地渲染、音频分析、播放和录制链路；不能证明中文口型准确、真人感、目标低配机帧率、麦克风实录、OBS 采集或淘宝实播。CI 使用相同生产静态服务，覆盖其资源路径和 CSP。

## 音视频传输

本测试启动实际 Go 后端、隔离 PostgreSQL schema 和两个真实 Chromium WebRTC peer，播放合成画面及测试音调，验证运营页关闭不影响独立输出、重复接收者不抢占、审核/合成/派发、接管/恢复和撤销。测试媒体服务只在此脚本内启动，生产代码不包含测试成功路径。

需要先完成前后端构建，并提供**专用测试数据库**：

```bash
cd web && npm ci && npm run build && cd ..
cd server && go build -o ../build/shuziren ./cmd/server && cd ..
npm --prefix tests/browser ci
cd tests/browser && npx playwright install chromium && cd ../..
BROWSER_DATABASE_URL='postgres://test_user:test_password@127.0.0.1:5432/shuziren_test?sslmode=disable' npm --prefix tests/browser test
```

脚本只认 `BROWSER_DATABASE_URL`，不读取应用 `DATABASE_URL`；测试前创建随机 schema，退出后只删除自己的 schema。应用单实例锁仍作用于整个数据库，请不要同时在同一测试数据库运行其他后端。需要 `psql` 命令可用。可用 `BROWSER_APP_BINARY`、`PSQL_BINARY`、`BROWSER_EXECUTABLE` 指定本地工具路径。

结果写入 `test-results/browser/transport-result.json`，该目录不提交 Git。此证据**不代表**真实 CosyVoice/MuseTalk 质量、OBS 采集成功或淘宝已播出。真实模型和8小时稳定性另按本地验收手册执行。

## 业务操作与布局

`business.cjs` 使用真实 Chromium、Go API 和 PostgreSQL 操作工作台：商品整数分与历史恢复、人格恢复、带来源和范围的记忆删改恢复、活动、资产、成本、限额、模板应用、人工审核、调度失败门禁、回放去重、关键词检索、未配置淘宝拒绝和独立输出签发。保存桌面与 390px 截图，并检查页面无横向溢出。

```bash
BROWSER_DATABASE_URL='postgres://test_user:test_password@127.0.0.1:5432/shuziren_business_test?sslmode=disable' npm --prefix tests/browser run test:business
```

默认业务服务使用 `127.0.0.1:18081`；可以用 `BROWSER_APP_PORT` 修改。`BROWSER_WEB_DIST` 可指定已构建的前端，脚本会复制到临时目录，避免并行构建改变正在验收的文件。`BROWSER_APP_BINARY`、`PSQL_BINARY`、`BROWSER_EXECUTABLE` 与传输脚本相同。运行时会随机生成口令，写入受限的临时文件，不打印口令；退出后清理临时目录和测试 schema。

结果位于 `test-results/browser-business/business-result.json`，截图为同目录 `business-desktop.png` 与 `business-mobile.png`，失败诊断为 `failure.txt`。该目录已忽略，不提交 Git。业务脚本清空 AI、TTS、媒体和淘宝凭据配置，不使用模型成功替身；缺少 TTS 的未合成计划与缺少淘宝授权的接口应明确拒绝。真实模型、平台商品、OBS 和淘宝播出另行验收。

**两个脚本不得并发使用同一数据库**，即使 schema 不同也会触发业务单实例锁。请使用两个专用可丢弃数据库，或按顺序运行且保证前一实例已退出。
