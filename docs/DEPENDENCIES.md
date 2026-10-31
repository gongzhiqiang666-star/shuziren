# 依赖和许可记录

当前为选型记录，实施时固定代码提交、模型revision、文件SHA-256和依赖锁定文件。以下不替代完整依赖及素材授权审查。

## v0.1 已锁定的实现

业务依赖以 `server/go.mod` / `go.sum`、`web/package.json` / `package-lock.json` 和 `workers/tts/requirements*.txt` 为准。应用构建使用 Go 1.27.3、Node.js 24.22.1；前端 Vue 3.5.44、Vite 7.3.7。Docker引用的官方版本标签已经核验存在，尚未执行镜像构建和目标Windows安装。

媒体HTTP适配核对上游代码提交：LiveTalking `c7269433a2b6ecebcd9342445d2ecc882c98b0da`、CosyVoice `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`，对应源码链接与安装说明分别见 `server/internal/media/README.md`、`workers/tts/README.md`。这表示核对了接口，不表示已加载其权重或验证真实音画。

CosyVoice包装器使用修复公告后的HTTP依赖版本，不能直接沿用上游旧FastAPI依赖清单。实际轻量环境审计和测试结果见[交付记录](IMPLEMENTATION_STATUS.md)；完整GPU环境需在安装后再次运行依赖检查与真实合成。模型revision、权重校验、头像和声音素材尚待目标环境记录。

## 模型与上游许可

| 组件 | 计划用途 | 已核实许可或边界 |
| --- | --- | --- |
| LiveTalking | 音视频引擎 | 主代码Apache-2.0；README另有视频水印和标识声明，发布前核对其与许可、实际发布方式的适用关系；依赖与模型另核对 |
| MuseTalk | 实时口型 | 主代码MIT，官方说明权重可商用；测试素材不能直接作为商用资产 |
| Fun-CosyVoice3-0.5B-2512 | 本地TTS | 指定模型卡Apache-2.0；声音素材需有授权 |
| BAAI/bge-small-zh-v1.5 | CPU检索 | 官方模型卡MIT |
| OBS | Windows媒体桥接 | 使用官方发行版；若再分发或修改，按其适用许可履行义务 |

LiveTalking、CosyVoice与BGE运行环境分别固定。不要把不同仓库安装步骤机械混到一个Python环境。

主线显式使用MuseTalk。模型权重、人物视频、声音样本和客户数据不放Git仓库，保存来源和校验记录。实际安装步骤和下载清单由W03/W10产出；本包未下载模型。

官方来源见DEVELOPMENT_PLAN.md中的S05至S14。
