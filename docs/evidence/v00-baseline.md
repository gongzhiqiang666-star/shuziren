# V00 本机基线验证证据

日期：2026-11-10。本记录为已执行的基线与工具验证，不代表V00全部完成或端到端直播通过。

## 环境与原始参照

- 当前开发分支：codex/phase1-v00，计划基线7a36b4f；已有应用/工具分支80282eb保留。
- 原运行包：D:\TEMP\v122-minimum-proof-ready\runtime\yunchuang_v122。
- 解释器：该包 _internal/env/python.exe，CPython3.10；Windows RTX3060 12GB。
- 原模块清单：排除env/env_50/site-packages/DLLs以及._资源fork后128个，路径集与仓库native-modules.txt中第一方清单一致。
- 未执行付费API、平台登录/发布或商业程序主窗口；原切片子模块仅在临时目录处理FFmpeg合成测试图与正弦音，不使用客户素材。

## 实际命令与结果

以下在仓库根目录执行；PATH显式加入随包FFmpeg。

```powershell
$runtime = 'D:\TEMP\v122-minimum-proof-ready\runtime\yunchuang_v122'
$python = "$runtime\_internal\env\python.exe"
$env:PATH = "$runtime\_internal\env\ffmpeg\bin;" + $env:PATH
& $python -I -X utf8 tests/test_recovery_runtime_paths.py
& $python -I -X utf8 scripts/validate_function_matrix.py
& $python -I -X utf8 recovered/verify_recovery.py --runtime-root $runtime
& $python -X utf8 -m unittest scripts.test_v122_proof
```

| 检查 | 真实结果 | 证明范围 |
| --- | --- | --- |
| 外部路径/资源fork/环境过滤/ASCII符号提取 | 4测试通过、退出0 | 文件识别规则，测试夹具不冒充模型 |
| 恢复全量校验 | 128/128，退出0 | 映射/导入、符号/方法/签名、既有隔离行为、协议及FFmpeg实际媒体分支；不证明所有行为兼容 |
| 既有一键验证工具 | 23测试通过、退出0 | 本地HTTP服务/编排/打包等工具的软件契约，含替身路径；未验真实TTS/人物或浏览器设备 |

日志：logs/validation/v00-recovery-external-runtime-utf8.log、v00-proof-toolkit-tests.log（不进Git）。矩阵在真实切片差异登记后将重新校验统计。

补充复跑：`scripts/check-recovery-baseline.ps1 -RuntimeRoot ...` 在本机依次执行上述4项检查，全部退出0，并写出 `logs/validation/recovery-baseline/summary.json`。该次执行时源码尚有本批未提交修改；提交完成后按提交内容追溯，不能将报告中基线HEAD误当作未修改的测试源码。

退回LIV-014后矩阵复测通过：58项，42静态验证通过、6开发中、10已分析。资源补充检查：UNet、WeNet配置/模型、静音特征、人脸检测、口型权重和遮挡模型配置路径均存在；torch2.6.0+cu118可识别RTX3060 CUDA，ORT1.15.1列出TensorRT/CUDA/CPU provider。这里只证明资源存在/provider可见，不代表各模型已在重建链推理通过。

## Windows执行中修正的验证环境问题

1. 固定仓库原包路径导致扫描0；现支持--runtime-root（不存在立即失败）。
2. 原扫描字符串只识别/分隔符，且macOS的._文件混入；现用os.walk剪枝与文件名过滤。
3. 外部Unix strings缺失；现用等价用途的可打印ASCII片段提取，保留所有符号审计断言。
4. 路径测试假设POSIX、Windows创建标志固定为0；现按路径组件和实际平台契约断言。
5. 安装真实protobuf后，快手测试混用miniproto消息与生成类；现使用实际协议类，同时交叉检查fallback线格式，不删除fallback覆盖。
6. GBK管道导致越南语回归异常；命令显式-X utf8，不吞掉编码错误。

## 脸手切片最小Windows差分

真实输入：FFmpeg生成320×240、25fps、1.2秒测试图和440Hz正弦音，同文件用作face与hand；参数min_clip_ms=400、max_clip_ms=800、face_keep_min_ms=200、rms_silence_thres=.001。

原.pyd：face_count=2、hand_count=2，返回含status=success，face/hand为绝对路径，manifest为version=2字典，有normalize/details/参数。恢复版初次返回face_count=0、hand_count=0，但磁盘存在切片；路径分类修复后既有真实媒体测试通过（2+2段、1080×1920、25fps）。

未解决：完整返回结构、manifest v2、默认参数（原能量阈值200.0等）和分段细节仍需定向对齐。仅记录实际已知差异，不按单个样本猜测所有边界。LIV-014退回开发中，X15-02保持未完成。

## 源码集成边界

从80282eb逐文件引入4个加速脚本、一键验证工具/网页/Windows启动器、配置示例及必要说明；未整分支覆盖recovered、AGENTS或58项矩阵。另一分支Go/Vue/PostgreSQL应用已有代码，保留为V01复用评估对象，不把此前“尚无界面”的推断当事实。
