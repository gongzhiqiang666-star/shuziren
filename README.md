# shuziren · yunchuang_v122 功能兼容重建

本仓库用于在完整保留 `yunchuang_v122` 用户可见功能的前提下，重建可维护、可测试的数字人生产与直播系统。仓库现已收录第一阶段恢复源码及逆向分析证据；这些代码尚未完成 Windows、GPU 和真实平台的全面验收。

## 确定方向

- 最终范围覆盖原产品全部用户可见功能，不因重写方案删减能力。
- 优先模仿原产品已通过生产验证的流程、模块边界、数据格式、接口和异常语义。
- 采用“架构重建 + 关键点定向逆向 + Windows 差分验证”，不追求机器码逐条等价。
- 淘宝、快手、Shopee 等平台能力以及文案、语音、图片、视频、数字人、项目管理、启动和打包流程均纳入功能矩阵。
- GPU、虚拟摄像头、浏览器自动化和平台客户端能力必须在对应真实环境验收。

## 开发资料

- [最终执行计划：入门款、高级款与候选方案验证](docs/DEVELOPMENT_PLAN.md)
- [高级款36项编号任务与验证门槛](docs/ADVANCED_TASKS.md)
- [候选方案56项编号评测与采用决策](docs/CANDIDATE_TASKS.md)
- [本机逐关开发与验证（通过后再进入下一流程）](docs/LOCAL_VALIDATION.md)
- [历史本地化方案（已被当前路线替代）](docs/DEVELOPMENT_PLAN_2026-10-31_ARCHIVE.md)
- [验收清单](docs/ACCEPTANCE.md)
- [画质、细节与口型控制](docs/AVATAR_QUALITY.md)
- [依赖和许可记录](docs/DEPENDENCIES.md)
- [GitHub 提交安排](docs/GITHUB_WORKFLOW.md)
- [重建规则](AGENTS.md)
- [逆向分析总报告](docs/reverse-engineering/yunchuang-v122-reverse-report.md)
- [PYZ 模块清单](docs/reverse-engineering/PYZ-modules.txt)
- [原生模块清单](docs/reverse-engineering/native-modules.txt)
- [第一阶段恢复源码](recovered/)

## 当前状态

2026-11-10：入门款（基础款）与高级款共用底座，按 V00~V09、A01~A07 逐流程开发和本机验证；X01~X14 管理候选方案评测。已核对另一工作区 80282eb 的原生 TensorRT/NVENC、常驻 TTS 局部性能证据；持续新音频入队、平台链路、长稳和独立源码交付仍待验证。当前先统一代码/矩阵和恢复基线；历史 PASS 及短时性能不能替代整流程验收。

2026-11-07：已提交第一阶段恢复源码、模块清单与核心调用链分析。当前验证脚本覆盖模块导入、接口签名和部分重点行为，但不代表所有模块已达到分支等价或生产验收。

项目仓库：[gongzhiqiang666-star/shuziren](https://github.com/gongzhiqiang666-star/shuziren)。原始商业程序、模型权重、CUDA 环境、凭据和用户数据不纳入版本库。

后续以完整功能矩阵和真实业务场景作为验收依据；优先完成可运行核心流程，再对不确定行为进行 Windows 原程序差分验证。
