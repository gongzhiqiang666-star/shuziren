# 本地 CosyVoice3 语音服务

该服务真正调用本机 CosyVoice3 的 `AutoModel` 与 `inference_zero_shot`，返回模型生成的 WAV。缺模型、缺运行时、参考声音未授权或加载失败时返回 HTTP 503；不回退到假声音、录音片段或付费 TTS。模型权重与人物声音不随仓库提交。

## 版本与接口依据

核验日期：2026-10-31。核验源码 SHA：`074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc`。

- [官方 example.py](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/example.py) 的 `cosyvoice3_example`：用本地模型目录创建 `AutoModel`；`inference_zero_shot` 接收合成文本、含 CosyVoice3 前缀的参考转写及参考音频文件路径；生成器输出 `tts_speech`，采样率来自模型。
- [官方 cosyvoice.py](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/cosyvoice/cli/cosyvoice.py)：`AutoModel` 根据 YAML 选择版本；目录不存在时会下载。因此包装器先验证本地目录及完整入口文件，并要求 `cosyvoice3.yaml`、拒绝混入旧版本配置，避免隐式下载或错用模型。
- [官方 README](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/README.md) 与 [requirements.txt](https://github.com/QwenAudio/CosyVoice/blob/074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc/requirements.txt)：生产环境按上游 Python 3.10 / CUDA 安装说明准备。HTTP 依赖与模型运行时独立列出，包装器覆盖上游旧的 HTTP 版本约束，具体边界见下文。

官方推荐的权重来源为 [FunAudioLLM/Fun-CosyVoice3-0.5B-2512](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512)。在部署时单独下载并固定权重 revision 与哈希；本仓库未下载、校验或运行这些权重。不能把包装器单元测试当成声音自然度、中文数字发音或实时性能验收。

LiveTalking `/humanaudio` 和 `/interrupt_talk` 的已核验协议、源码 SHA 与交付边界见 [`server/internal/media/README.md`](../../server/internal/media/README.md)。本服务只合成音频，由 Go 工作台将相同文件送入 LiveTalking 作为音频和口型输入。

## 安装

先在独立 GPU 环境按上述官方说明安装 CosyVoice，并检出核验的源码版本。参考命令（将目录替换成自己的外置运行时目录）：

```bash
git clone https://github.com/QwenAudio/CosyVoice.git /opt/cosyvoice
cd /opt/cosyvoice
git checkout 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git submodule update --init --recursive
python -m pip install --upgrade pip==26.2.2
python -m pip install -r requirements.txt
```

使用同一个 GPU Python 环境安装本服务的轻量依赖：

```bash
cd /path/to/shuziren/workers/tts
python -m pip install -r requirements.txt
python -m pip check
```

**HTTP 版本与模型依赖需区分：**上游源码的安装清单固定了 FastAPI 0.115.6 / Pydantic 2.7.0；本服务使用 FastAPI 0.162.0 / Starlette 1.3.1 / Pydantic 2.14.2，以修复旧 Starlette 的已公布问题，并保留 Python 3.10 支持。按上面的顺序先准备模型运行时，再安装本包装器依赖覆盖 HTTP 版本。不要把两份互相矛盾的精确版本清单合并解析，也不要之后重新安装上游清单把 HTTP 版本降回去。

已验证的是独立 HTTP 环境的依赖一致性与边界测试。完整 CosyVoice / CUDA 环境的兼容性仍须在目标 GPU 上执行 `pip check`、真实加载和合成测试；不能因为 HTTP 测试通过就宣称升级后的全套模型依赖已通过验收。

模型目录必须已存在且包含 `cosyvoice3.yaml`、`llm.pt`、`flow.pt`、`hift.pt`、`campplus.onnx`、`speech_tokenizer_v3.onnx`、`spk2info.pt` 和 `CosyVoice-BlankEN/`。包装器会设置 Hugging Face / Transformers 离线模式；部署前完成模型资料准备，缺件时修复配置后重启服务。

不要把 GPU PyTorch 依赖装到 Go 后端容器或前端环境；也不要将 `pip install -r requirements.txt` 误认为已经安装或加载了模型。本次无 GPU 验证只安装了 HTTP 与测试依赖。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `TTS_API_KEY` | 必填；24–512 位 ASCII Bearer 字符。与 Go 后端保持相同值，勿提交仓库 |
| `COSYVOICE_REPO_DIR` | 固定的本地官方源码目录，含 `cosyvoice/` 与 `third_party/Matcha-TTS/` |
| `COSYVOICE_MODEL_DIR` | 固定的本地 CosyVoice3 模型目录；不接受远程模型 ID |
| `COSYVOICE_PROMPT_WAV` | 固定且已获使用授权的本地参考 WAV 路径 |
| `COSYVOICE_PROMPT_TEXT` | 参考声音的准确转写，不含特殊控制前缀；包装器按官方示例添加前缀 |
| `COSYVOICE_PROMPT_AUTHORIZED` | 确认参考声音有使用授权后设为 `1`。此配置记录操作者声明，不替代授权材料 |
| `COSYVOICE_FP16` | 可选；`1` 启用 FP16，默认 `0`。须在目标硬件测量后选择 |

参考 WAV 限单声道 PCM16、8–48 kHz、0.5–30 秒、最多 4 MiB；这是本包装器的输入约束。HTTP 请求不能覆盖参考音频、转写、模型目录或声音身份。启动后如参考文件被替换，服务拒绝继续合成，直到操作者重启并加载新配置。

启动命令：

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 9880 --workers 1 --no-access-log
```

环境变量通过本机配置或密钥管理传入，不在示例命令中写实际 token。Go 后端使用 `TTS_BASE_URL=http://127.0.0.1:9880` 和同一个 `TTS_API_KEY`；如果后端运行在容器中，该地址必须改成能访问宿主 TTS 的受控地址，不能将容器自己的 localhost 当成宿主。

仅启动一个 worker，避免重复占用 GPU。默认不启用 TensorRT、vLLM 或第二个 TTS；后续启用加速必须独立验证性能与声音质量。

## HTTP 合同

两个接口均需 `Authorization: Bearer <TTS_API_KEY>`。无有效 key 时服务拒绝启动；运行时未授权请求返回 401。

| 接口 | 请求/响应 |
| --- | --- |
| `GET /healthz` | 加载成功返回 200 与 `{status:"ready",model_loaded:true,engine:"cosyvoice3",reason:"ready"}`；未就绪返回 503 和稳定原因码，不暴露路径或凭据 |
| `POST /synthesize` | 仅接受 JSON `{text:string}`，最多 2,000 字符；成功返回 `audio/wav`；请求体上限 16 KiB |

返回音频统一为单声道 PCM16 WAV，采样率使用模型真实输出，最多 300 秒 / 32 MiB。拼接同次推理产生的全部片段，拒绝空输出、NaN、全零输出及非法形状。不会用静音或预制录音填补失败。

单次只执行一个推理；并发请求返回 429，不在媒体层堆积过时话术。业务排队由 Go 工作台负责。模型缺失返回 503，模型推理失败返回 500，非法请求返回 422；错误响应不回显用户文本、文件路径、token 或上游异常原文。

HTTP 客户端取消或超时不能抢占已经执行的 PyTorch/GPU 内核。当前推理结束前仍占有工作锁，结果必须由业务层按 epoch 丢弃；本服务不把网络取消写成“已经停止GPU”。对于已经上传到 LiveTalking 的音频，接管还需调用 `/interrupt_talk`，并实测各级输出缓冲。

## 无 GPU 边界测试

另建轻量测试环境，不安装 CosyVoice、PyTorch 或权重：

```bash
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip==26.2.2
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

测试覆盖鉴权、缺模型 503、固定音色与路径限制、请求大小、错误脱敏、忙碌状态、WAV 编码，以及通过测试替身验证官方 `AutoModel`/`inference_zero_shot` 参数形状与音频片段顺序。替身样本只用于测试，不会在生产路径启用，也不证明真实模型出声。仍需在目标 GPU 完成加载、真实合成、同卡资源竞争、口型同步与长时运行验收。

## 已安装 HTTP 依赖的漏洞检查

2026-10-31 使用独立安装的 `pip-audit 2.10.1` 查询 PyPI 漏洞数据。原轻量环境的 Starlette 0.41.3、pytest 8.3.5 和环境自带 pip 25.0.1 被报告存在公告；重复返回的公告按 ID 去重。FastAPI 和 Pydantic 本体未被该次扫描报告漏洞，升级它们是为了采用兼容已修复 Starlette 的框架组合。

修复后对该轻量环境实际安装的 24 个包复扫：`No known vulnerabilities found`，退出码 0；`pip check` 无依赖冲突；34 项无 GPU 边界测试通过。扫描包括 pip 26.2.2、pytest 9.2.0 及本文件所述 HTTP 版本。该结果对应本次扫描时间与安装集合，既不是以后新公告的保证，也不是未安装模型组件的扫描结果。

Starlette 公告包括 [GHSA-82w8-qh3p-5jfq](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq)，其修复版本为 1.3.1。本服务只接受有界 JSON、没有表单解析和静态文件路由，依赖扫描命中不等于这些问题都能通过本服务利用；仍升级已安装依赖，避免保留已知存在问题的版本。

扫描范围仅包括实际安装的 HTTP / 测试环境，未安装、扫描或评价 CosyVoice 模型依赖及权重。生产 GPU 环境应单独扫描实际依赖，不得将轻量环境的检查结果外推为整个媒体系统安全认证。
