# GitHub提交安排

## 目标

仓库：[gongzhiqiang666-star/shuziren](https://github.com/gongzhiqiang666-star/shuziren)。当前为公开仓库，默认分支为 `main`。

用户已指定目标仓库并完成当前GitHub应用的仓库授权。2026-10-31 初始化前检查时为空仓库，无既有代码或仓库说明。README初始化提交已成功，本次继续收录开发计划。后续开发前读取仓库最新说明、代码和分支状态。

## 初始化与计划提交

先以 `docs: initialize shuziren project overview` 初始化 README；随后以 `docs: add Taobao development and avatar quality plans` 收录开发计划、验收、画质与口型控制、依赖记录、工作流和 .gitignore，并更新README导航。这两次提交都属于项目资料初始化，业务代码尚未实现。

空仓库初始化直接落在 `main`；后续业务改动使用任务分支和 PR。每个工作包按真实进展提交，不预先勾选未完成的验收项。

## 后续工作包

1. 本地运行骨架和配置（W03/W05）。
2. 本地媒体桥接及验证记录（W02/W04）。
3. 商品和本地检索（W06）。
4. DeepSeek及人格记忆（W07/W08）。
5. 淘宝授权连接器（W09）。
6. 本地TTS、缓存及资源控制（W10/W11）。
7. 审核、队列、取消和接管（W12/W13）。
8. 运营台及交付工具（W14/W15）。
9. 集成测试和试点修复（W16/W17）。

## 每次交付

- 提交SHA与具体文件；准确描述已实现和未实现部分。
- 有意义的Go/Vue单元或集成验证，真实命令、退出码与关键日志。
- GPU或淘宝未实测的部分明确标注，不使用Mock结果替代。
- 不提交密钥、Token、模型权重、客户数据、人物声音素材或运行日志。

计划采用codex/任务名称分支和PR组织可审查变更。远程推送前核验目标仓库与最新分支，避免覆盖他人工作。

## v0.1 实现交付

首版业务分支为 `codex/mvp-local-workbench`，从已有计划提交建立。该分支收录业务代码、媒体适配、启动脚本、CI和验证记录，通过PR供审查；完整产品上线验收不随首版提交提前勾选。

v0.1交付范围与验证记录归档在[V01_IMPLEMENTATION_STATUS.md](V01_IMPLEMENTATION_STATUS.md)。测试数据、访问口令、模型和构建产物不提交到公开仓库。

## v0.2 本地完整测试交付

分支 `codex/local-test-ready` 从v0.1已验证提交 `971d1f2f0578234614567a46f33dd1d9a03d84c7` 继续开发，包含独立输出、业务版本/活动/记忆、模板、费用与调度、真实BGE CPU检索、淘宝官方协议适配和运维工具。该分支包含v0.1全部代码，可独立检出运行。

v0.1的PR尚未合并时，v0.2以其业务分支作为PR基线，便于审查本次新增差异。[PR #2](https://github.com/gongzhiqiang666-star/shuziren/pull/2)已创建，应用提交为 `fa2d8c913398602f1768f2b2c54a3cbc7fd4a6f6`，Push/PR的verify和container-startup均通过；未合并到main。当前功能、实际测试与实机待测项见[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)。
