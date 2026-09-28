# -*- coding: utf-8 -*-
"""
事故检索测试 (Phase 7)

在独立事故索引上执行若干查询，打印 Top 5 结果（score/title/section/page/text 前 300 字），
检查语义结果是否基本合理。
"""
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

BASE = "/root/autodl-tmp/chemical_kb"
OUT_ROOT = BASE + "/data/accident"
INDEX_FILE = OUT_ROOT + "/vector_store/faiss_accident.index"
META_FILE = OUT_ROOT + "/vector_store/index_metadata.json"
MODEL_PATH = "/root/autodl-tmp/models/bge-m3"

TOP_K = 5

QUERIES = [
    "液氯泄漏事故原因是什么？",
    "有哪些危险化学品爆炸事故？",
    "化工企业火灾事故的主要原因有哪些？",
    "事故调查报告中有哪些整改措施？",
    "人员伤亡情况如何？",
]


def load_resources():
    print("=" * 60)
    print("加载事故 FAISS")
    index = faiss.read_index(INDEX_FILE)
    print("向量数量:", index.ntotal)
    print("加载 metadata")
    with open(META_FILE, encoding="utf-8") as f:
        metadata = json.load(f)
    print("metadata 数量:", len(metadata))
    print("加载 BGE-M3")
    model = SentenceTransformer(MODEL_PATH, device="cuda")
    model.max_seq_length = 1024
    return index, metadata, model


def search(question, index, metadata, model):
    print("\n" + "=" * 80)
    print("Query: " + question)
    qv = model.encode([question], normalize_embeddings=True).astype("float32")
    scores, ids = index.search(qv, TOP_K)
    print("-" * 80)
    for rank, (idx, score) in enumerate(zip(ids[0], scores[0]), 1):
        if idx < 0 or idx >= len(metadata):
            continue
        item = metadata[idx]
        print("\n[%d]" % rank)
        print("  score : %.4f" % float(score))
        print("  title : %s" % item.get("title", ""))
        print("  section: %s" % item.get("section", ""))
        print("  page  : %s-%s" % (item.get("page_start", ""), item.get("page_end", "")))
        print("  text  : %s" % item.get("text", "")[:300])


def main():
    index, metadata, model = load_resources()
    for q in QUERIES:
        search(q, index, metadata, model)
    print("\n" + "=" * 80)
    print("检索测试完成")


if __name__ == "__main__":
    main()
