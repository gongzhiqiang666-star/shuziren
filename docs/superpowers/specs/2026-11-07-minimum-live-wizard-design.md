# 最小直播链路验证向导设计

## 目标

在现有本地工作台增加“最小链路验证”页面，让实施人员无需阅读源码或手工编辑 JSON，即可完成检查、按步骤操作、记录证据并得到可信结论。

向导只做检查、引导和记录。它不启动、停止或安装 TTS、数字人、OBS、虚拟摄像头、SRS，也不登录或操作淘宝，不接收平台密钥、Cookie 和令牌。

## 用户路径

左侧导航新增“开播验证”。页面采用单页五步向导：

1. **环境与资产**：展示服务诊断结果，要求实施人员运行 Windows 预检命令，并录入报告中的非敏感结论。
2. **真实语音**：给出明确启动命令占位说明；实施人员在外部启动已选 TTS，输入 5–10 条新句，记录 WAV SHA-256、试听结果和备注。
3. **数字人与 OBS**：提示使用同一 WAV 驱动一个人物；记录虚拟摄像头或 SRS、OBS 画面、声音和回放结果。
4. **平台验证**：默认允许标记“尚未获准/阻塞”；只有取得许可并有观看端证据时才能通过。
5. **结论与导出**：根据关卡记录自动给出 `incomplete`、`failed`、`local_chain_passed_platform_blocked` 或 `platform_chain_passed`，并导出脱敏 JSON。

页面始终显示边界提示：“HTTP 可达、配置存在或工作台 sent 状态均不代表真实播出。”

## 架构

### 前端

新增独立组件 `web/src/readiness/LiveReadinessView.vue`，由现有 `App.vue` 导航加载。组件通过现有 `ApiClient` 调用后端，不使用浏览器本地存储，不读取本地文件路径，不执行 shell 命令。

前端拆分为：

- `types.ts`：运行记录、五道关卡、状态和导出结构；
- `validation.ts`：纯函数校验 SHA-256、必填证据和结论展示；
- `LiveReadinessView.vue`：步骤、按钮、错误和保存反馈。

页面复用现有 panel、badge、alert、button 样式，只新增少量向导布局 CSS。移动端保持纵向单列。

### 后端

新增店铺范围内的验证运行记录 API，数据保存在 PostgreSQL：

- `POST /api/v1/live-readiness/runs`：创建一次运行；
- `GET /api/v1/live-readiness/runs?shop_id=...`：列出运行；
- `GET /api/v1/live-readiness/runs/:id?shop_id=...`：读取详情；
- `PUT /api/v1/live-readiness/runs/:id/gates/:gate`：保存单个关卡；
- `GET /api/v1/live-readiness/runs/:id/export?shop_id=...`：返回脱敏 JSON。

不提供“执行命令”“启动服务”“安装驱动”“上传素材”接口。后端只接受结构化结果和不含秘密的证据标签。

### 数据模型

`LiveReadinessRun`：

```text
id, shop_id, title, created_at, updated_at,
version, output_mode, conclusion
```

`LiveReadinessGate`：

```text
run_id, name, status, evidence_json, note, updated_at
```

关卡名称固定为 `install`、`generation`、`obs`、`platform`、`stability`。状态固定为 `passed`、`failed`、`blocked`。创建时五关全部为 `blocked`，证据原因是 `not_run`。

第一轮结论不要求 stability 通过：install、generation、obs 通过且 platform 阻塞时，结论为 `local_chain_passed_platform_blocked`。

## 证据规则

### install

通过时必须记录：Windows 预检报告标签、NVIDIA 检查通过、资产检查通过、操作者确认。页面展示预检命令，但不读取实施电脑任意路径。

### generation

通过时必须记录：首次新句确认、64 位小写 WAV SHA-256、试听通过、同一 WAV 将用于口型。不得上传 WAV。

### obs

通过时必须记录：输出模式、画面证据标签、声音证据标签、录制回放已核对。只有画面或只有声音都不能通过。

### platform

通过时必须记录：已获授权和观看端证据标签。未获授权应保存为 blocked，而不是 failed。

### stability

第一轮可保持 blocked。执行后记录时长分钟数和人工观察标签；30 分钟或 8 小时都不自动从计时器推断通过。

## 安全与数据边界

- 所有输入字段递归拒绝名称含 password、secret、cookie、session、token、api_key、app_key 或 app_secret 的键。
- 文本字段限制长度并去除首尾空白；证据只允许简短标签，不允许绝对文件路径、URL 查询凭据或原始日志正文。
- SHA-256 必须是 64 位小写十六进制。
- 店铺归属由后端验证；不能跨店读取或修改验证记录。
- 更新使用 version 乐观锁，避免两名浏览器页面互相覆盖。
- 导出不包含管理口令、外部服务地址、素材路径或数据库内部信息。

## 操作命令呈现

页面根据当前步骤展示可复制命令，但不执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-live-readiness.ps1 `
  -Manifest config/live-readiness.local.json `
  -Output live-readiness-evidence/windows-preflight.json
```

TTS、数字人和 OBS 的启动命令由部署人员按实际安装位置写入受控部署说明；页面只给出“在外部终端执行已批准命令”的明确提示，不允许用户在网页输入任意命令。

## 错误和状态反馈

- 后端诊断失败：显示“无法取得检查结果”，不自动判关卡失败。
- 保存冲突：提示刷新当前运行记录，不覆盖他人更改。
- 缺失证据：在字段旁显示具体缺项，禁止保存 passed。
- 关卡失败：保留失败记录和说明，后续修复后可基于最新 version 更新，不删除历史更新时间。
- 平台阻塞：页面明确显示“本地链路可继续验证”，不展示为红色系统故障。

## 测试

### 后端

- 创建运行生成五个 blocked 关卡；
- 各关卡 passed 的必填证据；
- platform blocked 的本地通过结论；
- 敏感键、绝对路径和超长文本拒绝；
- 店铺隔离、version 冲突和不存在记录；
- 导出脱敏及稳定字段顺序。

### 前端

- 导航进入向导；
- 步骤状态和缺项提示；
- generation/OBS 关卡约束；
- platform blocked 的非失败展示；
- 复制命令只复制固定文本；
- 页面不调用启动、安装或平台操作 API；
- 桌面和移动布局。

### 浏览器验收

真实点击创建运行、逐步保存 install/generation/obs、保持 platform blocked，确认结论为 `local_chain_passed_platform_blocked`，导出内容无敏感字段。测试数据只使用假的哈希和证据标签，不冒充真实模型或 OBS 验收。

## 非目标

第一版不执行 PowerShell，不选择本地目录，不上传 WAV/视频，不启动服务，不控制 OBS，不操作淘宝，不判断口型质量，不自动测量音画同步，也不替代 Windows/NVIDIA 实机证据。

## 完成定义

1. 实施人员能从导航进入五步向导；
2. 能创建、恢复和更新一次验证运行；
3. 页面严格阻止证据不完整的 passed 状态；
4. 三个本地关卡通过、平台阻塞时给出正确结论；
5. 能导出不含秘密和本地路径的 JSON；
6. 自动化和浏览器测试证明页面没有进程控制能力；
7. 文档明确外部启动命令由实施人员执行。
