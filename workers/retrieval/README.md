# 本地 BGE 中文语义检索

使用 BAAI 的 `bge-small-zh-v1.5`，CPU 推理，512 维归一化向量。唯一付费 AI 接口仍为 DeepSeek。源码依照 [BAAI 模型卡](https://huggingface.co/BAAI/bge-small-zh-v1.5) 的 CLS pooling、归一化与查询前缀实现；文档文本不加查询前缀。

## 安装

在独立 Python 3.12 环境安装，避免与 CosyVoice CUDA 环境混装：

```bash
python3 -m venv .venv-bge
. .venv-bge/bin/activate
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r workers/retrieval/requirements.txt
python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5', revision='7999e1d3359715c523056ef9478215996d62a620', local_dir='./models/bge-small-zh-v1.5', allow_patterns=['config.json','tokenizer_config.json','tokenizer.json','special_tokens_map.json','vocab.txt','model.safetensors','README.md'])"
```

模型下载是一次性安装动作。服务启动和推理均 `local_files_only=True`、`trust_remote_code=False`，只加载 safetensors；缺少文件返回503，不自动下载，也不生成测试向量。

在本机配置 `BGE_MODEL_DIR` 为绝对路径，`BGE_API_KEY` 为独立随机口令（至少24个非空格ASCII字符），运行：

```bash
uvicorn workers.retrieval.app:app --host 127.0.0.1 --port 9890 --no-access-log
```

工作台后端配置同一 `BGE_API_KEY` 和 `BGE_BASE_URL=http://127.0.0.1:9890`；原生BGE使用9890以避免与LiveTalking常用8010端口冲突。后端在Docker中、worker在宿主机时填写可达宿主机地址，且限制worker只允许本机/容器访问。也可使用 `compose.bge.yaml` 叠加文件，将BGE放入内部Docker网络，不公开其内部8010端口。

### 可选内部容器

先按上文准备本地权重，再在仓库根目录的 `.env` 保留以下配置；口令和目录填自己的值：

```dotenv
COMPOSE_FILE=compose.yaml,compose.bge.yaml
COMPOSE_PATH_SEPARATOR=,
BGE_MODEL_DIR=/本机绝对路径/models/bge-small-zh-v1.5
BGE_API_KEY=填写独立随机口令
```

`COMPOSE_PATH_SEPARATOR=,` 让Linux/WSL和Windows使用相同文件列表。这里的中文口令说明只是占位，实际口令须为至少24个ASCII Bearer字符。`BGE_BASE_URL`可留空，由叠加配置为app设置 `http://bge:8010`。然后执行启动脚本，或 `docker compose up --build -d --wait`。模型权重以只读目录挂载，不放进镜像或Git。

**后续保留这两条COMPOSE配置。** 启动、重启、停止、备份恢复与诊断都会使用同一叠加配置。仅首次命令带 `-f`、后来恢复裸基础配置，会产生有BGE口令但无URL的不完整配置，应用将拒绝启动。卸载BGE叠加时，应同时清空BGE的URL/口令，回到明确的关键词模式。

内部BGE没有宿主端口，不要在宿主机请求 `http://bge:8010`。工作台“联调与淘宝→服务诊断”和 `doctor.py --models` 通过实际后端检查模型；后端看到BGE已加载才报告就绪。CPU模型首次加载需要时间，容器启动成功与模型就绪分别检查。

## 实际行为

- `/health` 与 `/embed` 都要求 Bearer；health只报告就绪、模型与加载文件的SHA256指纹。
- 模型固定为BERT/512维，CPU最多8个线程，每次最多32条、每条4500字；模型输入在512 tokens截断，仅影响检索排名，交给DeepSeek的命中知识仍保留完整原文。
- 后端先按店铺、商品、场次与有效期过滤，再嵌入和检索。当前精确余弦排名在Go中进行，向量持久化在PostgreSQL数组中；本地规模不强制安装pgvector。此实现替代原计划中的pgvector索引部署，大规模索引仍是后续优化项。
- 语义查询仅嵌入当前问题，不附加商品标题，避免标题将“能否退货”偏向“杯子规格”。商品/场次身份用于知识范围过滤，结构化商品事实另行提供给DeepSeek。
- 缓存由店铺/知识ID/内容hash/真实模型指纹隔离；知识改动和模型替换会重新嵌入。以0.35作为工程初始相似度下限、最多6条/6000字，不声称这是经过客户语料调优的阈值。
- 完全未配置BGE时明确使用关键词模式；配置后模型不可用会拒绝生成，不悄悄降级，也不会先调用DeepSeek计费。

## 已执行的验证

2026-10-31，隔离Linux CPU环境安装上述版本并加载固定模型，对“买了不合适可以退吗？”和3条合成FAQ执行真实推理。退货FAQ余弦分数0.603，水杯规格0.246，发货规则0.315，命中预期。模型加载约3.11秒，4条文本的该次推理约0.037秒。这里只记录一次功能冒烟测试，不是吞吐、延迟或检索质量基准。

同日还完成实际Go后端→认证HTTP worker→真实CPU模型→PostgreSQL缓存联调。另一组3条有效FAQ与1条过期FAQ中，退货问题返回退货FAQ第一名，过期项被过滤；3条文档向量实际保存，第二次查询一致，后端健康诊断返回就绪。这验证了本地服务链路，不代表客户知识库的召回率已经评估。

模型权重、虚拟环境和本地口令均不提交Git。安装完成后使用工作台“检索测试”页测试自己的已核验FAQ，再逐条检查命中是否合适。
