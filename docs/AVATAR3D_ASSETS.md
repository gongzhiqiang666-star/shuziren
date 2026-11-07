# 本地 3D 样例资产与准备方法

本地 3D 页使用真实三维网格、骨骼和嘴形形变，不使用二维人物录像充当三维模型。内置样例用于验证本地渲染、眨眼、头部动作和嘴形驱动；它是基础三维人形美术，不代表照片级人物质量或客户头像已经验收。

## 一、固定的 CC0 人物样例

| 项目 | 记录 |
| --- | --- |
| 上游 | `met4citizen/TalkingHead` 的 `avatars/mpfb.glb` |
| 作者与制作工具 | TalkingHead 项目提供的 MPFB 样例；使用 Blender 和 MakeHuman 的 MPFB 扩展制作 |
| 固定提交 | `8c3fe13df098fac1ad62bb61972a404d2827ba54` |
| 本地位置 | `web/public/avatar-assets/mpfb.glb` |
| 原文件大小 | **36,815,920 字节**，约 35.1 MiB |
| SHA256 | `63c645a2a863b9972e9a9c2ed576a1de4c390b8475508e1473e69c87a3ee299c` |
| 该具体资产的许可 | **CC0**；依据是作者对 `mpfb.glb` 的单独声明，不是代码的 MIT 许可 |
| 格式 | GLB 2.0；7 张 PNG 贴图全部内嵌，无外部贴图地址，无 Draco / Meshopt 解码要求 |
| 结构检查 | 8 个网格，顶点计数合计 53,116，三角形合计 83,686；带身体、眼睛、牙齿和舌头 |

精确来源：

- [固定提交中的 GLB](https://github.com/met4citizen/TalkingHead/blob/8c3fe13df098fac1ad62bb61972a404d2827ba54/avatars/mpfb.glb)
- [固定提交的直接下载地址](https://raw.githubusercontent.com/met4citizen/TalkingHead/8c3fe13df098fac1ad62bb61972a404d2827ba54/avatars/mpfb.glb)
- [固定 README 的资产许可段落](https://github.com/met4citizen/TalkingHead/blob/8c3fe13df098fac1ad62bb61972a404d2827ba54/README.md#L367-L376)：`Licenses, attributions and notes related to the index.html web app assets` 段落中，第 373 行专门说明 `mpfb.glb` 使用 CC0。
- [Creative Commons CC0 1.0 说明](https://creativecommons.org/publicdomain/zero/1.0/)与[完整法律文本](https://creativecommons.org/publicdomain/zero/1.0/legalcode)：允许复制、修改、分发和商业使用；不得暗示原作者为本产品背书。
- [固定提交的 MPFB 制作与导出说明](https://github.com/met4citizen/TalkingHead/blob/8c3fe13df098fac1ad62bb61972a404d2827ba54/blender/MPFB/MPFB.md)

因此，此样例可以随产品分发或放入公开仓库；本项目选择用脚本下载并校验，避免将 36.8 MB 大二进制反复写入 Git。分发包保留本来源记录。用户自行导入的模型需另有对应使用权；此样例的 CC0 不会延伸到其他资产、商标或真人肖像。

同一上游中的 `brunette.glb` 明确为非商业用途，Avaturn、AvatarSDK 与 VRoid 示例也分别标注非商业用途，不能因为在 MIT 代码仓库中就一起用于本项目商业分发。本项目不下载这些替代头像、Mixamo 动作或云端语音资产。

## 二、实际可驱动的形变

`base` 网格有 66 个形变目标：52 个 ARKit 名称和 14 个非静音 Oculus 嘴形。已直接读取固定 GLB 的 JSON 验证，不能用文件名或宣传说明代替形变检查。

```text
viseme_PP  viseme_FF  viseme_TH  viseme_DD  viseme_kk
viseme_CH  viseme_SS  viseme_nn  viseme_RR  viseme_aa
viseme_E   viseme_I   viseme_O   viseme_U
```

另有 `jawOpen`、`mouthClose`、`mouthFunnel`、`mouthPucker`、`eyeBlinkLeft`、`eyeBlinkRight` 等。没有 `viseme_sil`；静音时将发音嘴形权重归零。牙齿与舌头也有 `jawOpen` 和部分同名嘴形，驱动时应更新所有相关网格，避免只动脸皮。

骨骼包括 `Armature`、`Hips`、`Spine`、`Neck`、`Head`、`Jaw`、`LeftEye` 与 `RightEye`。骨骼和形变可以在浏览器本地驱动；准确发音、中文口型、真实运行帧率仍需单独测试。

原文件含一张 4096×4096 衣服法线贴图，其余为 1024 或 2048 尺寸；眉毛和睫毛网格也占一定资源。当前未压缩原文件，不从“无需 CUDA”推断任意低端电脑都流畅。之后如制作压缩版本，应保留全部必要骨骼和形变，另记来源、转换参数与新 SHA256。

## 三、一键准备与启动

需要可运行的 Python 3.10+、Node.js 和 npm；建议使用 Node.js 24，也支持满足当前前端依赖的 20.19+ / 22.12+。本工具不安装 Python 包、不启动数据库、不需要 CUDA 或 Docker。首次准备会下载上述 GLB 及 `package-lock.json` 锁定的 npm 依赖。

Linux / macOS / WSL：

```sh
sh scripts/start-avatar3d.sh
```

Windows PowerShell，在项目根目录：

```powershell
powershell -File scripts/start-avatar3d.ps1
```

Windows 启动器实际运行探针，依次检查 `py -3`、`python3`、`python`，不会仅因命令存在就认为 Python 已安装。它优先使用 `npm.cmd`，避免依赖 `npm.ps1` 的执行策略。若组织策略限制执行脚本，按该电脑允许的方式逐条运行下一节中的准备及 npm 命令，不由本脚本修改执行策略。

启动后打开 `http://127.0.0.1:5173/avatar3d`，服务仅监听本机。端口被占用时启动失败，不会悄悄改成另一个端口。关闭终端或按 Ctrl+C 停止；准备和启动命令不会自动开播、推流或调用收费 AI 接口。

### 不下载样例，使用自己的 GLB

```sh
sh scripts/start-avatar3d.sh --no-sample
```

```powershell
powershell -File scripts/start-avatar3d.ps1 --no-sample
```

打开页面后使用本地 GLB 导入功能。自己的文件不会被准备脚本复制或改写；需包含页面支持的骨骼及嘴形形变，单纯有 `.glb` 扩展名不等于能动嘴。

### 只准备，不打开页面

```sh
sh scripts/start-avatar3d.sh --prepare-only
# 也可组合：--no-sample --prepare-only
```

```powershell
powershell -File scripts/start-avatar3d.ps1 --prepare-only
```

这会完成资源校验与 `npm ci`，随后退出，不启动开发服务器。需要启动时，在 `web` 目录执行 `npm run avatar3d`。模型和 npm 依赖都已准备好的离线电脑可直接运行这条命令，无需再次执行 `npm ci`。

## 四、下载、缓存与失败处理

也可以只准备人物文件：

```sh
python3 scripts/avatar3d_setup.py
# Windows：py -3 scripts/avatar3d_setup.py
```

下载器只写固定的 `web/public/avatar-assets/mpfb.glb`，没有任意输出路径参数。已有文件只有在大小和 SHA256 全部正确时才复用；同名文件不同内容、符号链接或非普通文件会被保留并明确拒绝。若这里放了自己的头像，移动到自己的素材目录或使用 `--no-sample`。

网络读取等待上限为 30 秒，总下载等待检查为 180 秒；正在阻塞的读取最多再等一个读取超时。响应和累计字节数都受固定文件大小限制，不接受无限下载。内容先写到同目录临时文件，校验完整后原子替换到最终样例路径。失败或取消不会留下可被误加载的半个 `mpfb.glb`，临时文件会清理。

若网络不能访问 GitHub，可以从上方固定提交的直接地址手动下载，放入固定位置，再运行准备脚本验证；或使用 `--no-sample`。下载失败会返回非零状态，启动脚本不会将失败当作已经准备成功，也不会改用来源不明的镜像。
