# 真实浏览器验收

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
