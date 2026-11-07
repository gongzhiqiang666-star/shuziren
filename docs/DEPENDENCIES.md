# 依赖和许可记录

本文件记录v0.2主线与v0.3本地3D预览已采用的依赖、实际验证范围与尚需目标机器准备的模型。尚未安装的媒体模型须在实施时固定revision和文件SHA-256。以下不替代完整依赖及素材授权记录。

## v0.2 已锁定的实现

业务依赖以 `server/go.mod` / `go.sum`、`web/package-lock.json`、`tests/browser/package-lock.json` 和各worker的 `requirements*.txt` 为准。应用构建使用 Go 1.27.3、Node.js 24.22.1、PostgreSQL 16.15；前端 Vue 3.5.44、Vite 7.3.7；浏览器验收使用 Playwright 1.62.1。版本对应实际验证结果见[交付记录](IMPLEMENTATION_STATUS.md)，不能用旧版CI记录代替当前代码验证。

媒体HTTP适配核对上游代码提交：LiveTalking `c7269433a2b6ecebcd9342445d2ecc882c98b0da`、CosyVoice `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`，对应源码链接与安装说明分别见 `server/internal/media/README.md`、`workers/tts/README.md`。这表示核对了接口，不表示已加载其权重或验证真实音画。

CosyVoice包装器使用修复公告后的HTTP依赖版本，不能直接沿用上游旧FastAPI依赖清单。实际轻量环境审计记录见[语音worker说明](../workers/tts/README.md)；完整GPU环境需在安装后再次运行依赖检查与真实合成。CosyVoice/MuseTalk权重revision、头像和声音素材尚待目标环境记录。worker实际加载内容的SHA256指纹用于缓存与已合成任务的身份核验，不将素材台账ID当成真实引擎身份。

## 已实际运行的BGE

本次真实CPU验证使用 `BAAI/bge-small-zh-v1.5`，revision `7999e1d3359715c523056ef9478215996d62a620`；`model.safetensors` 的SHA256为 `354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026`。测试环境是 Python 3.12、CPU Torch 2.15.0、Transformers 5.22.1、safetensors 0.8.0，实际加载512维模型并完成同义问题检索。

服务启动不下载模型、不执行远程仓库代码，只读取本地safetensors。缓存revision同时绑定权重、配置、完整tokenizer文件、worker代码和关键运行库/推理参数；换模型或分词配置会使向量缓存失效。安装与功能测试样例见[BGE说明](../workers/retrieval/README.md)。可选BGE容器配置已通过Compose语法验证；独立CPU运行证据不能代替该镜像的实际构建/启动证据。

## v0.3 本地3D预览的运行依赖与资产

3D预览在浏览器中加载真实网格、骨骼、贴图和嘴形。它与现有CosyVoice/MuseTalk真人视频主线分别验收，不把三维模型能显示、音频能分析当作中文口型质量或淘宝实播已通过。

| 组件 | 固定版本或来源 | 用途及许可 |
| --- | --- | --- |
| Three.js | `0.180.0`，由 `web/package-lock.json` 锁定 | 三维渲染、GLTFLoader与OrbitControls；MIT。发布包保留实际安装包的 `THREE_LICENSE.txt`。 |
| Vue | `3.5.44`，由 `web/package-lock.json` 锁定 | 页面及界面运行时；MIT。发布包保留 `VUE_LICENSE.txt`；当前 `@vue/runtime-dom`、`runtime-core`、`reactivity`、`shared` 的许可文本与其相同，无需重复分发依赖目录。 |
| HeadAudio | `met4citizen/HeadAudio`，提交 `c6d8af35034068b1c98dcc0fa3ec9602d711e784` | 浏览器内MFCC特征与高斯原型分类器，将音频映射为嘴形；MIT。随包保留 `app/vendor/headaudio/LICENSE` 与 `NOTICE.md`。 |
| MPFB三维人物 | `met4citizen/TalkingHead/avatars/mpfb.glb`，提交 `8c3fe13df098fac1ad62bb61972a404d2827ba54` | 该具体样例由作者单独声明为CC0，不从TalkingHead代码的MIT许可推断资产许可。原文件36,815,920字节，SHA256为 `63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c`。 |

HeadAudio的运行代码没有外部依赖；上游训练和测试使用过HeadTTS、webpack、jest，不代表这些软件是本预览的运行服务，也不因此打包它们的依赖树。Node.js是用户运行本地静态服务器时自行提供的运行时，本发布包不附带Node二进制。

随包的 `model-en-mixed.bin` 使用四个HeadTTS音色和英语Harvard Sentences训练。上游明确说明语音活动检测和预测精度存在局限，低信噪比时尤其明显；**中文精细口型尚未验收**。音频产生了嘴形轨道，不代表每个音节映射准确，也不代表具备TTS能力。源码、模型和本地改动记录见随包的HeadAudio `NOTICE.md`。

来源与分发记录：

- [HeadAudio固定提交的MIT许可](https://github.com/met4citizen/HeadAudio/blob/c6d8af35034068b1c98dcc0fa3ec9602d711e784/LICENSE)、[方法及精度边界](https://github.com/met4citizen/HeadAudio/blob/c6d8af35034068b1c98dcc0fa3ec9602d711e784/README.md#introduction)、[模型训练来源](https://github.com/met4citizen/HeadAudio/blob/c6d8af35034068b1c98dcc0fa3ec9602d711e784/README.md#training)。
- [MPFB固定提交的资产许可声明](https://github.com/met4citizen/TalkingHead/blob/8c3fe13df098fac1ad62bb61972a404d2827ba54/README.md#L367-L376)；完整来源、形变清单、哈希和下载校验方式见[3D资产记录](AVATAR3D_ASSETS.md)。
- 发布脚本从本次安装的Three.js和Vue包读取完整许可文本；HeadAudio的许可与NOTICE随静态资源原样进入包。构建工具和测试工具不作为独立运行依赖复制进发布包。

## 模型与上游许可

| 组件 | 计划用途 | 已核实许可或边界 |
| --- | --- | --- |
| LiveTalking | 音视频引擎 | 主代码Apache-2.0；README另有视频水印和标识声明，发布前核对其与许可、实际发布方式的适用关系；依赖与模型另核对 |
| MuseTalk | 实时口型 | 主代码MIT，官方说明权重可商用；测试素材不能直接作为商用资产 |
| Fun-CosyVoice3-0.5B-2512 | 本地TTS | 指定模型卡Apache-2.0；声音素材需有授权 |
| BAAI/bge-small-zh-v1.5 | CPU检索 | 官方模型卡MIT |
| OBS | Windows媒体桥接 | 使用官方发行版；若再分发或修改，按其适用许可履行义务 |

LiveTalking、CosyVoice与BGE运行环境分别固定。不要把不同仓库安装步骤机械混到一个Python环境。

主线显式使用MuseTalk。模型权重、人物视频、声音样本和客户数据不放Git仓库，保存来源和校验记录。BGE已在隔离环境实际下载和运行；CosyVoice3、MuseTalk与人物素材尚未在本次环境加载，不能据此宣称真实数字人质量已经通过。

官方来源见DEVELOPMENT_PLAN.md中的S05至S14。
