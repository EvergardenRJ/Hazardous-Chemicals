# Alpha 项目模型目录

> 此文件只记录模型信息和获取方式，不包含权重。服务器盘点日期：2026-09-28。项目内副本位于 models/README.md；实际权重目录为 /root/autodl-tmp/models/。

## 模型在系统中的位置

文档片段 → BGE-M3 生成 1024 维向量 → FAISS 召回 → BGE Reranker 对查询与片段对打分 → Qwen 生成回答、抽取知识图谱断言并做语义审核。

| 用途 | 上游模型与下载链接 | 服务器现有目录 | 目录大小 | 权重参数量（本机文件统计） |
| --- | --- | --- | ---: | ---: |
| 生成与知识图谱 | [Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | /root/autodl-tmp/models/models/Qwen--Qwen3-4B-Instruct-2507/snapshots/master | 约 7.6 GB | 4,022,468,096 |
| 向量嵌入 | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | /root/autodl-tmp/models/bge-m3 | 约 2.2 GB | 567,754,752 |
| 相关性重排 | [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | /root/autodl-tmp/models/bge-reranker-v2-m3 | 约 2.2 GB | 567,755,777 |

参数量由服务器现有权重的张量形状求和得出；目录大小是磁盘占用的近似值。**目前尚未核准这三份本地权重对应的上游 commit revision**。以后要复现相同结果，须在下载清单中记录完整 revision 和重要文件的 SHA-256；不能只写 main 或 master。

## 1. Qwen3-4B-Instruct-2507

- 类型：Qwen3 因果语言模型，非思考模式。上游模型卡称约 4.0B 参数，其中非嵌入参数约 3.6B。
- 本地 config.json：hidden_size=2560，36 层，32 个查询头、8 个键值头，intermediate_size=9728，vocab_size=151936，max_position_embeddings=262144。
- 项目用法：core/llm.py 以 bfloat16 加载；core/rag.py 用于回答；core/kg/extractor.py 与 core/kg/pipeline.py 用于关系抽取；scripts/kg/audit_corpus_candidates.py 用于候选语义审核；此外用于百科生成和部分实体规范化。
- 项目生成上限：批量抽取 max_new_tokens=2048，批量审核 1600；这些是本项目设置，不是模型最大上下文。
- 上游许可：Apache-2.0。模型卡和文件：[Hugging Face](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)。
- 运行限制：4B BF16 权重约 8 GB，实际显存还需容纳缓存和批处理输入；本项目服务器为 RTX 4090 D 24 GB。显存需求会随输入长度和批量变化。

## 2. BGE-M3

- 类型：基于 XLM-RoBERTa 的多语种嵌入模型。模型卡支持 dense、sparse 和 multi-vector；**本项目目前主要使用 dense 向量**，不要把模型能力误写成已实现功能。
- 本地 config.json：hidden_size=1024，24 层，16 个注意力头，intermediate_size=4096，vocab_size=250002，max_position_embeddings=8194。模型卡给出的文本长度为 8192 token，输出 dense 向量为 1024 维。
- 项目用法：core/embedding.py 通过 SentenceTransformer 在 CUDA 上编码，归一化后转 float32；向量写入 data/vector_store/ 的 FAISS 索引，用于相似度召回。
- 上游许可：MIT。模型卡和文件：[Hugging Face](https://huggingface.co/BAAI/bge-m3)。

## 3. BGE Reranker v2 M3

- 类型：基于 XLM-RoBERTa 的序列分类重排模型，输入为“问题、片段”对，输出相关性分数。
- 本地 config.json：hidden_size=1024，24 层，16 个注意力头，intermediate_size=4096，vocab_size=250002，max_position_embeddings=8194。
- 项目用法：core/reranker.py 使用 logits 评分，实际 tokenize 的 max_length=512。core/config.py 设置 FAISS_TOP_K=50、FINAL_TOP_K=5；重排器返回前 5 条。这两个数值是项目检索配置，不是模型架构参数。
- 上游许可：Apache-2.0。模型卡和文件：[Hugging Face](https://huggingface.co/BAAI/bge-reranker-v2-m3)。

## 下载与路径配置

官方 [Hugging Face 下载文档](https://huggingface.co/docs/huggingface_hub/en/guides/download)支持 snapshot_download 按完整 commit revision 下载模型。例如：

~~~python
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="BAAI/bge-m3",
    revision="<核准后的完整commit SHA>",
    local_dir="/root/autodl-tmp/models/bge-m3",
)
~~~

其余两个模型分别替换 repo_id 与目标目录。若暂时未确认 revision，可先从模型页面下载当前版本用于试运行，但不能据此声称与服务器权重完全一致。下载后核对 config.json、权重文件和 SHA-256。

当前 core/config.py 和 core/llm.py 写死了上述服务器绝对路径。未来供其他人部署时，应改用 .env 或配置文件中的 MODEL_DIR、EMBED_MODEL_PATH、RERANK_MODEL_PATH，并提供 .env.example。**只复制本 README 不会使模型自动可用；必须下载权重并设置路径。**
