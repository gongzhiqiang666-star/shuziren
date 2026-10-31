# shuziren · 淘宝数字人直播本地部署项目

本仓库当前处于开发计划阶段，尚不包含可运行的业务代码。计划状态不代表模型、淘宝账号或真实直播已经验收。

## 确定方向

- 只做淘宝，保留原商品、人格、记忆、审核、插播、接管与恢复功能。
- DeepSeek 是唯一按量付费 AI 接口；CosyVoice3、BGE 和 MuseTalk 优先本地运行。
- Go + Vue + PostgreSQL；Windows 11 + WSL2 为首个验证环境。
- 淘宝连接器及相关数据的位置按实际批准确定，不能预设全部本地。
- 首期单机同时一路，保留多店和多场次配置。

## 开发资料

- [完整开发计划与 WBS](docs/DEVELOPMENT_PLAN.md)
- [验收清单](docs/ACCEPTANCE.md)
- [画质、细节与口型控制](docs/AVATAR_QUALITY.md)
- [依赖和许可记录](docs/DEPENDENCIES.md)
- [GitHub 提交安排](docs/GITHUB_WORKFLOW.md)

## 当前状态

2026-10-31：计划、成本和验收设计完成。尚未开发应用代码，未执行模型部署、GPU压测、淘宝账号登录或真实直播。

项目仓库：[gongzhiqiang666-star/shuziren](https://github.com/gongzhiqiang666-star/shuziren)。用户已于 2026-10-31 指定此仓库；当前可见性为公开，默认分支为 `main`。本次收录开发计划及验收资料，业务实现按工作包后续提交。

工期预算：320小时基础工作 + 64小时联调返工，共384小时。平台审批和硬件等待另计。
