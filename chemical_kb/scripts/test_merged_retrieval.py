# -*- coding: utf-8 -*-
"""合并后检索测试：A 5 事故查询 + B 3 标准法规回归，Top10（只用 EmbeddingModel + VectorStore 底层 search）。"""
import json
import sys
from pathlib import Path

BASE = "/root/autodl-tmp/chemical_kb"
sys.path.insert(0, BASE)

from core.embedding import EmbeddingModel
from core.vector_store import VectorStore

QUERIES_ACCIDENT = [
    "液氯泄漏事故原因是什么？",
    "危险化学品爆炸事故案例",
    "化工企业火灾事故发生经过",
    "事故调查报告中的整改措施",
    "事故造成人员伤亡的案例",
]
QUERIES_REGRESSION = [
    "液氯储存有哪些安全要求？",
    "液氯泄漏应急处置要求有哪些？",
    "危险化学品储存安全要求",
]


def dtype(m):
    return str(m.get("doc_type") or m.get("document_type") or "")


def is_accident(m):
    return dtype(m) in ("accident", "事故")


def run_query(emb, store, q, top_k=10):
    vec = emb.encode(q)
    results = store.search(vec, top_k=top_k)
    acc = sum(1 for r in results if is_accident(r["metadata"]))
    out = []
    print("Query: %s" % q)
    for rank, r in enumerate(results, 1):
        m = r["metadata"]
        title = str(m.get("title", ""))
        section = str(m.get("section", ""))
        page = str(m.get("page_start", ""))
        text = str(m.get("text", "")).replace("\n", " ")
        rec = {
            "rank": rank,
            "score": round(float(r["score"]), 4),
            "doc_type": dtype(m),
            "title": title,
            "section": section,
            "page": page,
            "text300": text[:300],
        }
        out.append(rec)
        print("  %d. score=%.4f | %s | %s | sec=%s | p=%s" % (
            rank, r["score"], dtype(m), title[:38], section, page))
        print("      %s" % text[:150])
    print("  >>> Top%d: 事故=%d / 标准法规=%d" % (top_k, acc, top_k - acc))
    print("-" * 72)
    return {"query": q, "top_k": top_k, "accident_count": acc,
            "regulation_count": top_k - acc, "results": out}


def main():
    print("加载 EmbeddingModel + VectorStore（合并后主库）...")
    emb = EmbeddingModel()
    store = VectorStore()
    all_res = {"accident_queries": [], "regression_queries": []}
    print("=" * 72)
    print("A. 事故查询")
    print("=" * 72)
    for q in QUERIES_ACCIDENT:
        all_res["accident_queries"].append(run_query(emb, store, q))
    print("=" * 72)
    print("B. 标准法规回归")
    print("=" * 72)
    for q in QUERIES_REGRESSION:
        all_res["regression_queries"].append(run_query(emb, store, q))
    out_path = Path(BASE) / "data" / "vector_store" / "retrieval_test_result.json"
    json.dump(all_res, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("结果已保存:", out_path)


if __name__ == "__main__":
    main()
