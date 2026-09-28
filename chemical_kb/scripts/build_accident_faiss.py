# -*- coding: utf-8 -*-
"""
事故 FAISS 索引 (Phase 6)

创建「独立事故索引」，不触碰现有标准法规 FAISS。
索引类型与现有系统一致：IndexFlatIP（配合已归一化 embedding = 余弦相似度）。
输出 faiss_accident.index + index_metadata.json。
"""
import os
import json
import numpy as np
import faiss

BASE = "/root/autodl-tmp/chemical_kb"
OUT_ROOT = BASE + "/data/accident"

EMBEDDING_FILE = OUT_ROOT + "/embeddings/chunks_embeddings.npy"
METADATA_FILE = OUT_ROOT + "/embeddings/chunks_metadata.json"

VECTOR_DIR = OUT_ROOT + "/vector_store"
INDEX_FILE = VECTOR_DIR + "/faiss_accident.index"
META_OUTPUT = VECTOR_DIR + "/index_metadata.json"


def main():
    os.makedirs(VECTOR_DIR, exist_ok=True)
    print("=" * 60)
    print("加载 embedding")
    embeddings = np.load(EMBEDDING_FILE)
    print("向量 shape:", embeddings.shape)
    embeddings = embeddings.astype("float32")
    dimension = embeddings.shape[1]
    print("维度:", dimension)

    print("=" * 60)
    print("创建 FAISS IndexFlatIP")
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    print("索引数量 ntotal:", index.ntotal)

    print("=" * 60)
    print("保存 FAISS")
    faiss.write_index(index, INDEX_FILE)
    print(INDEX_FILE)

    print("=" * 60)
    print("保存 metadata")
    with open(METADATA_FILE, encoding="utf-8") as f:
        metadata = json.load(f)
    with open(META_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(META_OUTPUT)

    print("=" * 60)
    print("校验")
    print("ntotal:", index.ntotal, "== metadata 数量:", len(metadata),
          "->", "一致" if index.ntotal == len(metadata) else "不一致!")

    print("=" * 60)
    print("FAISS 建立完成")


if __name__ == "__main__":
    main()
