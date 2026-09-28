# -*- coding: utf-8 -*-
"""完整只读检查：主库 vs 事故库 的 index/维度/schema/归一化/一致性。"""
import json
from collections import Counter
from pathlib import Path

import faiss
import numpy as np

BASE = "/root/autodl-tmp/chemical_kb"


def inspect_index(path, label):
    p = Path(path)
    if not p.exists():
        print("[%s] 不存在: %s" % (label, path))
        return None
    idx = faiss.read_index(str(p))
    info = {
        "path": path,
        "size_mb": round(p.stat().st_size / 1024 / 1024, 2),
        "ntotal": idx.ntotal,
        "dim": idx.d,
        "type": type(idx).__name__,
        "is_flat_ip": isinstance(idx, faiss.IndexFlatIP),
    }
    print("[%s]" % label)
    for k, v in info.items():
        print("   %s: %s" % (k, v))
    return info


def inspect_metadata(path, label):
    p = Path(path)
    if not p.exists():
        print("[%s] 不存在: %s" % (label, path))
        return None
    data = json.load(open(p, encoding="utf-8"))
    items = data if isinstance(data, list) else list(data.values())
    print("[%s] 顶层类型=%s, 数量=%d" % (label, type(data).__name__, len(items)))
    if items:
        first = items[0]
        print("[%s] 首条字段名: %s" % (label, list(first.keys())))
        keys = set()
        for it in items:
            keys.update(it.keys())
        print("[%s] 全量字段并集: %s" % (label, sorted(keys)))
        # 字段类型
        print("[%s] 首条字段类型: %s" % (label, {k: type(v).__name__ for k, v in first.items()}))
        # document_type / doc_type 分布
        dt = Counter()
        for it in items:
            dt[str(it.get("document_type", it.get("doc_type", "<缺失>")))] += 1
        print("[%s] document_type/doc_type 分布: %s" % (label, dict(dt)))
        # source 分布
        src = Counter(str(it.get("source", "<缺失>")) for it in items)
        print("[%s] source 分布(前10): %s" % (label, dict(list(src.most_common(10)))))
        # 首条完整样例（text 截断）
        sample = dict(first)
        for k in list(sample.keys()):
            v = sample[k]
            if isinstance(v, str) and len(v) > 200:
                sample[k] = v[:200] + "...<截断>"
        print("[%s] 首条完整样例:")
        print(json.dumps(sample, ensure_ascii=False, indent=2))
    return items


def inspect_npy(path, label):
    p = Path(path)
    if not p.exists():
        print("[%s] 不存在: %s" % (label, path))
        return None
    arr = np.load(str(p), mmap_mode="r")
    print("[%s] shape=%s dtype=%s" % (label, arr.shape, arr.dtype))
    norms = []
    idxs = list(range(0, arr.shape[0], max(1, arr.shape[0] // 5)))[:5]
    for i in idxs:
        v = arr[i].astype(np.float32)
        norms.append(round(float(np.linalg.norm(v)), 5))
    print("[%s] 抽样 L2 norm (5条): %s" % (label, norms))
    return arr.shape


print("=" * 70)
print("【主知识库】")
print("=" * 70)
m_idx = inspect_index(BASE + "/data/vector_store/faiss.index", "主FAISS")
m_meta = inspect_metadata(BASE + "/data/vector_store/index_metadata.json", "主metadata")
m_npy = inspect_npy(BASE + "/data/embeddings/chunks_embeddings.npy", "主embeddings.npy")
# 主 embeddings 下的 chunks_metadata.json 与 vector_store 下是否一致
p1 = Path(BASE + "/data/embeddings/chunks_metadata.json")
p2 = Path(BASE + "/data/vector_store/index_metadata.json")
if p1.exists() and p2.exists():
    print("[主库] embeddings/chunks_metadata.json 与 vector_store/index_metadata.json 内容一致:",
          p1.read_bytes() == p2.read_bytes())

print()
print("=" * 70)
print("【事故库】")
print("=" * 70)
a_idx = inspect_index(BASE + "/data/accident/vector_store/faiss_accident.index", "事故FAISS")
a_meta = inspect_metadata(BASE + "/data/accident/vector_store/index_metadata.json", "事故metadata")
a_npy = inspect_npy(BASE + "/data/accident/embeddings/chunks_embeddings.npy", "事故embeddings.npy")

# 事故 chunks jsonl 行数
chunk_file = Path(BASE + "/data/accident/chunks/chunks_accident.jsonl")
if chunk_file.exists():
    nlines = sum(1 for _ in open(chunk_file, encoding="utf-8"))
    print("[事故] chunks_accident.jsonl 行数:", nlines)
    with open(chunk_file, encoding="utf-8") as f:
        first_line = json.loads(f.readline())
    print("[事故] chunks 首条字段名:", list(first_line.keys()))

print()
print("=" * 70)
print("【一致性检查（事故库）】")
print("=" * 70)
if a_idx and a_meta and a_npy and chunk_file.exists():
    chunk_n = nlines
    emb_n = a_npy[0]
    meta_n = len(a_meta)
    faiss_n = a_idx["ntotal"]
    print("chunk数 =", chunk_n)
    print("embedding行数 =", emb_n)
    print("metadata数 =", meta_n)
    print("FAISS ntotal =", faiss_n)
    ok = (chunk_n == emb_n == meta_n == faiss_n)
    print("四者一致:", ok)

print()
print("=" * 70)
print("【兼容性检查】")
print("=" * 70)
if m_idx and a_idx and m_npy and a_npy:
    print("主向量维度:", m_idx["dim"], " 事故向量维度:", a_idx["dim"],
          " -> 一致:", m_idx["dim"] == a_idx["dim"])
    print("主FAISS类型:", m_idx["type"], " 事故FAISS类型:", a_idx["type"],
          " -> 一致:", m_idx["type"] == a_idx["type"])
    print("都是 IndexFlatIP:", m_idx["is_flat_ip"] and a_idx["is_flat_ip"])
    print("主embeddings行数:", m_npy[0], " 事故embeddings行数:", a_npy[0])
