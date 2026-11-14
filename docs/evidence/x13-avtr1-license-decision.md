# X13 AVTR-1 适用条件与产品决策

日期：2026-11-14。核对对象：`avaturn-live/avtr-1` 官方仓库当前 `main`。结论：X13-01 完成；当前产品不采用，X13-02/03 不启动。

## 官方组件与运行条件

官方仓库把方案拆成三个独立许可对象，而不是一个统一“开源许可”：

| 组件 | 路径/职责 | 官方许可与产品影响 |
| --- | --- | --- |
| AVTR-1 模型、权重及脚本 | 动作生成及构建/演示工具 | Community License；年收入达到 1000 万美元的实体商业使用需另签协议，并受用途限制 |
| Avaturn Renderer | `src/avtr1_renderer/`，推理、音频编码、形变与合成 | PolyForm Noncommercial；任何商业使用均需独立 Renderer 商业许可 |
| Avaturn Streamer | `src/avaturn_live_streamer/`，音频调度、补偿时钟、事件与双流协调 | PolyForm Noncommercial；任何商业使用均需独立 Streamer 商业许可，并有专利权利保留 |

官方 README 还明确说明预训练 InsightFace SCRFD 和 2D106 模型仅限非商业研究；商业使用必须另获许可或换成许可合适的检测/关键点实现。Renderer 基于 LivePortrait，仍需逐项遵守第三方声明。

当前官方环境是 `linux-64`、Python 3.12、CUDA 12.8，并要求构建多个 TensorRT 引擎；本项目首发目标是 Windows RTX 3060，现有本机环境和已验证链路不能直接复用这些运行条件。权重需通过 Hugging Face 登录下载，不能纳入仓库或默认安装包。

## 产品决策

本项目是可商业交付的数字人直播产品，因此不能把“模型对低收入实体有条件商业许可”误写成整套方案可商用。完整产品若使用官方 Renderer/Streamer，仍必须取得两份独立商业许可；Streamer 的专利声明也禁止把独立重实现视为自然规避路径。

当前决策：

1. 不下载权重、不构建引擎、不运行产品原型，避免在商业目标不满足时投入集成成本。
2. 不复制 Renderer/Streamer 的实现或把其调度细节迁入当前自有直播链。
3. 保留官方资料作为研究情报，不加入入门款或高级款默认依赖。
4. 只有取得覆盖模型、Renderer、Streamer 和所需第三方模型的书面商业授权，并具备 Linux/CUDA 12.8 独立测试机后，才重开 X13-02。
5. 即使未来获得授权，也必须在隔离适配器中与当前链比较中文音频、首帧、25 fps、显存、音画同步、取消恢复、Windows 部署代价和最终接收端画质，通过后才进入 X13-03。

## 验收状态

- X13-01：完成。模型、Renderer、Streamer、InsightFace 依赖、商业门槛、专利及运行环境均已逐对象确认。
- X13-02：不启动，原因是商业许可和目标运行环境条件缺失；这不是原型通过。
- X13-03：不触发，没有合规原型可接入产品。
- X13-04：当前产品“不采用”；研究结论保留，不能归入免费商用开源默认方案。

## 官方来源

- [仓库组件许可总表](https://github.com/avaturn-live/avtr-1/blob/main/LICENSE.md)
- [官方 README 与第三方非商业依赖说明](https://github.com/avaturn-live/avtr-1/blob/main/README.md)
- [模型 Community License](https://github.com/avaturn-live/avtr-1/blob/main/LICENSE-MODEL.md)
- [Streamer 非商业许可](https://github.com/avaturn-live/avtr-1/blob/main/LICENSE-STREAMER.md)
- [Streamer 专利权利保留](https://github.com/avaturn-live/avtr-1/blob/main/PATENTS.md)
- [固定运行环境与依赖](https://github.com/avaturn-live/avtr-1/blob/main/pixi.toml)
- [第三方声明](https://github.com/avaturn-live/avtr-1/blob/main/THIRD-PARTY-NOTICES.md)
