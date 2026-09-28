#模块引用

from pathlib import Path


BASE_DIR = Path(
    "/root/autodl-tmp/chemical_kb"
)


# 数据

VECTOR_INDEX = (
    BASE_DIR /
    "data/vector_store/faiss.index"
)


VECTOR_METADATA = (
    BASE_DIR /
    "data/vector_store/index_metadata.json"
)


# 模型

EMBED_MODEL = (
    "/root/autodl-tmp/models/bge-m3"
)


RERANK_MODEL = (
    "/root/autodl-tmp/models/bge-reranker-v2-m3"
)


# 参数

FAISS_TOP_K = 50

FINAL_TOP_K = 5