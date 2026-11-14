# 轻量 3D 资产与许可记录

## 固定 CC0 人物

| 项目 | 固定值 |
| --- | --- |
| 上游 | `met4citizen/TalkingHead` 的 `avatars/mpfb.glb` |
| 固定提交 | `8c3fe13df098fac1ad62bb61972a404d2827ba54` |
| 大小 | 36,815,920 字节 |
| SHA-256 | `63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c` |
| 许可 | 该具体 `mpfb.glb` 由上游单独声明为 CC0 |
| 格式 | 自包含 GLB 2.0；无外部纹理、Draco 或 Meshopt 依赖 |

来源：

- [固定提交中的资产](https://github.com/met4citizen/TalkingHead/blob/8c3fe13df098fac1ad62bb61972a404d2827ba54/avatars/mpfb.glb)
- [上游固定 README 的资产许可段](https://github.com/met4citizen/TalkingHead/blob/8c3fe13df098fac1ad62bb61972a404d2827ba54/README.md#L367-L376)
- [CC0 1.0 法律文本](https://creativecommons.org/publicdomain/zero/1.0/legalcode)

该 CC0 结论只适用于固定的 `mpfb.glb`，不会扩展到同仓库其他人物、用户模型、商标或真人肖像。上游的部分替代头像明确限制非商业使用，不能随本项目一起分发，也不能因代码仓库采用 MIT 就推断所有资产均可商用。

固定样例含 8 个网格、约 83,686 个三角形和 66 个形变目标，覆盖 Oculus 嘴形及 ARKit 面部名称；牙齿和舌头也有部分形变。样例只证明可驱动结构，不证明中文发音准确、目标设备帧率或真人感。

## HeadAudio

本地声学 Worker 使用随包固定的 HeadAudio MIT 模块和模型文本。`app/vendor/headaudio/LICENSE` 与 `NOTICE.md` 必须随包存在；打包器缺少任一文件即拒绝生成 ZIP。模型 SHA、长度和来源由 Worker 在加载时校验。上游模型主要面向英语，中文精细嘴形仍需独立人工验收。

## 前端依赖

独立包保留 Three.js 与 Vue 的许可文本。所有文件均列入 `MANIFEST.json`，记录字节数和 SHA-256；包不会包含 npm 缓存、源码开发依赖、客户素材、凭据或参考商业程序。
