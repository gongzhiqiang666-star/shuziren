# A07-05 媒体环境软件门禁

日期：2026-11-14

## 完成范围

- `scripts.media_runtime software` 从三份已提交锁定文件读取所有精确版本，不接受范围版本或重复包名。
- 使用独立媒体目录自身的 Python 读取已安装 distribution 版本，包名按 Python 规范统一连字符、下划线和点号。
- 版本匹配与 `pip check` 依赖完整性分开报告；只有两者同时通过，`ready` 才为 true，命令才退出 0。
- 报告可写入仓库外 JSON，包含 Python 版本、37 个包的预期/实际版本、来源锁文件、逐项结果和有限长度的依赖诊断。
- 该门禁不修改环境，不会在已验证旧 CUDA 环境上自动升级包。

## 本机实测

对象：`D:\TEMP\shuziren-origin-video-media-01`，Python 3.10.16。

- 37/37 个直接锁定包版本匹配，`versions_verified=true`。
- 首轮工具把 `huggingface_hub` 与 `huggingface-hub` 误判为不同名称；修正规范化后实际 1.11.0 匹配，专项 11/11 通过。
- `dependency_check_ok=false`、`ready=false`，退出码 1，证明门禁不会把旧环境错误放行为发布环境。
- 未满足项来自间接/可选依赖及冲突：缺少 opencv-python-headless、tensorboardx、tzdata、mako、pytools、seaborn、ultralytics-thop，以及 JAX/py3langid 对 NumPy、Streamlit 对 protobuf 的版本冲突。
- 完整报告：`logs/validation/a07-media-software-report-02.json`（本机产物，不提交环境或模型）。

下一步是在新目录重建依赖闭合的媒体环境，执行本门禁后再逐引擎跑 IndexTTS、ZipVoice、OmniVoice、视频直驱、虚拟设备与成片回归。旧环境保持不变作为结果对照。

## 2026-11-14 离线重建条件复核

本机 pip 缓存目录存在，但没有检出上述 37 个直接包及缺失依赖所需的可复用 wheel；因此当前不能用 `--no-index` 在新目录重建完整 CUDA 媒体环境。未从旧环境复制 `site-packages`，也未在旧 CUDA 环境中卸载或升级包。

现有 11 条 `pip check` 结果分为两类：

- 新环境必须补齐并重新锁定的实际依赖：FunASR 的 tensorboardx、Pandas 的 tzdata、PyCUDA 的 mako/pytools、Ultralytics 的 seaborn/ultralytics-thop；ddddocr 与 `opencv-python-headless` 还需确定是否进入默认主环境，避免和当前 `opencv-python` 同时提供 `cv2`。
- 不应无条件混入默认媒体环境的冲突工具：JAX/JAXlib 要求 NumPy 至少 1.25，py3langid 要求 NumPy 至少 2.0，Streamlit 要求 protobuf 小于 6；当前模型基线分别固定 NumPy 1.24.0 和 protobuf 6.32.1。

重开条件是准备 Windows AMD64/CPython 3.10/CUDA 11.8 的受控 wheelhouse（含 PyTorch 官方 CUDA wheel 和全部传递依赖）。随后在全新目录按“核心媒体环境＋按需工具环境”拆分安装，分别 `pip check`，再逐引擎真实回归。不能为了让旧环境变绿而改变已经实测的 NumPy/protobuf/CUDA 组合。
