# 最小真实直播链路验证手册

本手册只回答一个问题：在一台 Windows/NVIDIA 电脑上，`yunchuang_v122` 参考方案能否把现场新句变成真实语音和数字人画面，并让 OBS 同时录到声音和画面。HTTP 可达不能证明真实播出，本地预览成功也不能证明平台已收到。

## 通过边界

固定链路：现场新句 → 一种本地 TTS → 同一份 WAV 驱动一个数字人 → 虚拟摄像头（或明确选择的 SRS）→ OBS 本地录制。

第一轮到 OBS 为止。没有获准的淘宝测试路径时，平台关保持 `blocked`，本地成功结论只能是 `local_chain_passed_platform_blocked`。不测试弹幕、自动回复、商品弹卡、多模型、多人物、多路并发或八小时稳定性。

## 1. 准备配置

在 Windows PowerShell 中复制模板：

```powershell
Copy-Item config/live-readiness.example.json config/live-readiness.local.json
notepad config/live-readiness.local.json
```

只修改本地绝对路径、引擎名称和 OBS 场景名。不要填写密钥、Cookie、平台账号或令牌。准备一个授权人物、一份授权参考 WAV 与准确转写、一套实际模型权重、原版运行目录、OBS、FFmpeg 和输出所需 DLL/SRS。

## 2. 运行只读预检

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check-live-readiness.ps1 `
  -Manifest config/live-readiness.local.json `
  -Output live-readiness-evidence/windows-preflight.json
```

任一必需项为 `fail` 或 `unverified` 时立即停止，不安装驱动、不自动注册 DLL、不切换云服务。先人工解决缺失条件，再重新预检。

## 3. 初始化证据目录

```powershell
py -3.11 scripts/live_readiness.py init-run `
  --manifest config/live-readiness.local.json `
  --root live-readiness-evidence
```

命令输出本次 UTC 目录。不要把人物、声音、录制、密钥或 Cookie 复制到 Git；证据文件只记录哈希、状态和受控位置标签。

## 4. 生成第一批真实内容

1. 现场输入 5–10 条从未合成过的新句，包含数字、停顿和商品规格。
2. 用清单中唯一的 TTS 生成 WAV；试听确认不是缓存旧音频。
3. 记录原文和 WAV 的 SHA-256。
4. 把同一份 WAV 交给唯一的数字人运行时，禁止试听和口型使用不同音频。
5. 没有新 WAV、模型报错或人物不动时，generation 关标记 `failed` 并立即停止。

## 5. OBS 本地证明

优先按原版方式选择虚拟摄像头；只有清单明确配置 `srs` 时才改用 SRS。OBS 创建单一场景 `minimum-live-proof`，确认视频源和真实音频源，连续录制至少 10 分钟。

回放录制并人工确认：

- 有连续画面且人物口型响应；
- 有可听见的对应语音；
- 声音和画面来自本次新句；
- 没有持续黑屏、静音或明显队列卡死。

只有画面或只有声音都判失败。OBS 界面看见设备名称不能代替回放证据。

## 6. 更新关卡并汇总

在本次目录的 `gates/*.json` 中只填写脱敏证据。generation 的 `wav_sha256` 必须是 64 位小写十六进制；OBS 关同时填写 `video` 和 `audio` 记录标签。然后运行：

```powershell
py -3.11 scripts/live_readiness.py summarize --run live-readiness-evidence/本次UTC目录
```

平台未获准时不要伪造通过。获得批准后，再让淘宝测试观看端实际确认音画，并只更新 platform 关。30 分钟和 8 小时稳定性属于后续关卡，不阻塞第一次 OBS 可行性判断。

## 失败定位

| 现象 | 本轮结论 | 下一动作 |
|---|---|---|
| 模型或人物素材缺失 | blocked | 补齐合法资产并重新盘点 |
| CUDA/Python 导入失败 | failed | 固定驱动、环境和模型版本 |
| TTS 返回成功但没有新 WAV | failed | 查 TTS 日志和输出目录，不进入口型 |
| 虚拟摄像头不存在 | failed | 人工核对 DLL 与 Windows 注册状态 |
| OBS 只有画面 | failed | 核对音频设备与 OBS 音轨 |
| OBS 只有声音 | failed | 核对虚拟摄像头/SRS 与人物进程 |
| 平台账号或路径未获批准 | blocked | 本轮停在 OBS，不继续平台操作 |

## 完成判定

本地最小链路只有在 install、generation、obs 三关都有真实证据时通过。任何一关失败就停止功能开发，先修这一段；这份结果不代表平台接入、长稳或完整产品已经完成。
