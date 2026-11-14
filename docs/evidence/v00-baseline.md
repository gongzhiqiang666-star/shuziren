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

后续在 2026-11-14 使用同一原 `.pyd` 直接补齐：返回结构、manifest v2、全部公开默认参数、原始 PCM RMS 和随机分段语义均已实测恢复；同输入同随机种子的规范化 manifest 完全一致，恢复版真实成片规格亦通过。LIV-014 提升为静态验证通过，真实淘宝场次和长稳仍未因此放行；X15-02 的方案对照结论不由本项替代。

## 源码集成边界

从80282eb逐文件引入4个加速脚本、一键验证工具/网页/Windows启动器、配置示例及必要说明；未整分支覆盖recovered、AGENTS或58项矩阵。另一分支Go/Vue/PostgreSQL应用已有代码，保留为V01复用评估对象，不把此前“尚无界面”的推断当事实。

## V00-04 严格原包完整性结果：失败

已执行现有 `scripts/verify_v122_package.py --root D:\TEMP\v122-minimum-proof-ready --output logs/validation/v00-package-integrity.json`。原manifest包含205495文件、52143432469字节；程序完整结束，退出1，checked=205493、missing=2、changed=109。报告和命令日志留本机，严格结果未改写。

| 差异 | 数量 | 具体范围 |
| --- | --- | --- |
| 缺失 | 2 | image_infer_v2/trt_cache_full内旧FP16 engine和profile |
| 变化 | 107 | Python/Numba生成缓存（__pycache__、.pyc、.nbc、.nbi） |
| 变化 | 1 | 该TensorRT缓存目录gpu_info.txt |
| 变化 | 1 | _internal/temp/audio_cache_index.txt |

本报告未列出这些类别之外的源码或模型权重差异，但整个原始归档仍严格失败。现有构建器把完整运行目录所有文件纳入同一个不可变清单，和正常运行会修改缓存的行为冲突；不能删除原失败项或更新哈希冒充原包一致。

下一任务V00-04b：明确并实现发布不可变文件与生成缓存/临时数据的边界，保留严格归档核验，给运行健康检查独立且明确的语义。V00-04c必须验证源码/模型/配置/必需程序缺失或改动仍失败、缓存变化只按明确策略报告、路径异常仍失败。未验证前V00不放行，不启动V01。

## V00-04b/c策略实现与验证续记

已实现 [版本化完整性策略](../INTEGRITY_POLICY.md)：archive默认严格、runtime显式核对原清单的不可变输入，新format2包不复制生成缓存或macOS传输元数据，旧包工具刷新不改runtime原哈希。源码/权重/配置不扩大白名单。Windows入口默认archive，切换模式须显式参数并生成不同报告。

已执行12项规则/隔离CLI测试及23项原工具回归，均退出0；针对程序/配置/模型缺失、同长度改动、非白名单cache路径、空/重复/越界/非法清单、旧清单保护、新包产生缓存后的严格校验和空/重叠目标等场景有断言。完整基线命令复跑，5组检查（4路径、12策略、58项矩阵、128恢复、23工具）全部退出0。实机runtime扫描已完整结束：139273不可变文件检查通过，missing/changed/errors均空、退出0；66222生成条目不认证内容。

全量命令：`env/python.exe -I -X utf8 scripts/verify_v122_package.py --root D:\TEMP\v122-minimum-proof-ready --profile runtime --progress --output logs/validation/v00-runtime-input-integrity.json`。策略分类205495个原记录，其中66218个Python/Numba缓存、3个TRT缓存、1个音频缓存索引不认证内容并在报告逐项标明，其余都使用原记录哈希；这是不同检查范围，不代表严格归档通过。原运行目录和旧manifest没有覆盖/重建。

实际扫描耗时546.72秒。manifest SHA256为 `8e59cbe30acad265451053f3e874c7c7c5c1bd1aaf9af1ac8cd1d7ad13ac212f`，扫描后重新对照仍一致。扫描启动后仅将必需记录从7项补强为含ffprobe的8项，生成分类/哈希算法未变；结束后独立核对8项记录均在已检查清单且文件存在，未以重跑或改报告伪造检查范围。

V00-05核对报告profile/status、manifest不变、条目数量覆盖、8项必需记录及旧严格报告仍失败均通过。此结果放行环境/恢复基线关V00，允许进入V01；不将原生缓存、模型效果、全部差分、真实平台或独立发布标完成。
