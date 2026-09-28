# -*- coding: utf-8 -*-
"""
merge_accident_into_main_vector_store.py

将「事故案例」正式合并进现有主 FAISS 向量知识库（只动 数据层 / FAISS层）。

策略（append，不重算任何历史向量）：
  1. 加载主 FAISS (IndexFlatIP) + 主 metadata (list)
  2. 加载事故 embeddings (.npy) + 事故 metadata (list)
  3. compatibility check（维度 / 索引类型 / 归一化）—— 不兼容立即停止
  4. schema 转换（事故 metadata 对齐主库，source="事故报告"，doc_type="accident"）
  5. 去重（chunk_id 为键）—— 幂等
  6. 若新增=0：直接返回（无备份、无修改）
  7. 备份主 index + metadata + 强绑定 metadata + manifest
  8. append 向量 + append metadata（严格保持顺序一致）
  9. 原子保存（.tmp 校验后 os.replace）
 10. integrity check（ntotal == len(metadata)）+ 输出合并报告

不修改任何 core 文件；保留事故独立索引 data/accident/vector_store/faiss_accident.index。
"""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np

BASE = "/root/autodl-tmp/chemical_kb"

# ---- 主库（将被修改）----
VECTOR_INDEX = Path(BASE) / "data" / "vector_store" / "faiss.index"
VECTOR_METADATA = Path(BASE) / "data" / "vector_store" / "index_metadata.json"
# 主库强绑定 metadata（与 index_metadata.json 内容一致，备份用）
MAIN_EMB_META = Path(BASE) / "data" / "embeddings" / "chunks_metadata.json"

# ---- 事故库（只读，独立索引保留不删）----
ACC_EMB = Path(BASE) / "data" / "accident" / "embeddings" / "chunks_embeddings.npy"
ACC_META = Path(BASE) / "data" / "accident" / "embeddings" / "chunks_metadata.json"
ACC_FAISS = Path(BASE) / "data" / "accident" / "vector_store" / "faiss_accident.index"
ACC_VS_META = Path(BASE) / "data" / "accident" / "vector_store" / "index_metadata.json"

# ---- 输出 ----
MERGE_REPORT = Path(BASE) / "data" / "vector_store" / "merge_report.json"

ACCIDENT_DOC_TYPE = "accident"
ACCIDENT_DOCUMENT_TYPE = "事故"
ACCIDENT_SOURCE = "事故报告"


def log(msg):
    print("[merge] " + msg, flush=True)


def load_main():
    log("加载主 FAISS: %s" % VECTOR_INDEX)
    index = faiss.read_index(str(VECTOR_INDEX))
    meta = json.load(open(VECTOR_METADATA, encoding="utf-8"))
    assert index.ntotal == len(meta), "主库 ntotal(%d) != metadata(%d)" % (index.ntotal, len(meta))
    log("  主 FAISS: ntotal=%d dim=%d type=%s" % (index.ntotal, index.d, type(index).__name__))
    log("  主 metadata: %d 条" % len(meta))
    return index, meta


def load_accident():
    log("加载事故 embeddings + metadata")
    emb = np.load(str(ACC_EMB))
    meta = json.load(open(ACC_META, encoding="utf-8"))
    assert emb.shape[0] == len(meta), "事故 emb行数(%d) != metadata(%d)" % (emb.shape[0], len(meta))
    log("  事故 embeddings: shape=%s dtype=%s" % (emb.shape, emb.dtype))
    log("  事故 metadata: %d 条" % len(meta))
    # 独立事故索引 ntotal 一致性（不修改、只校验）
    acc_idx = faiss.read_index(str(ACC_FAISS))
    assert acc_idx.ntotal == len(meta), "事故独立 FAISS ntotal(%d) != metadata(%d)" % (acc_idx.ntotal, len(meta))
    log("  事故独立 FAISS(保留): ntotal=%d dim=%d type=%s" % (acc_idx.ntotal, acc_idx.d, type(acc_idx).__name__))
    return emb, meta


def check_compatibility(main_index, acc_emb, acc_meta):
    log("=" * 60)
    log("compatibility check")
    log("=" * 60)
    errors = []

    # 1) 索引类型
    main_type = type(main_index).__name__
    if not isinstance(main_index, faiss.IndexFlatIP):
        errors.append("主 FAISS 不是 IndexFlatIP（是 %s），append 不安全" % main_type)
    log("  主 FAISS 类型: %s" % main_type)

    # 2) 维度
    acc_dim = int(acc_emb.shape[1])
    dim_ok = main_index.d == acc_dim
    log("  维度: 主=%d 事故=%d -> %s" % (main_index.d, acc_dim, "一致" if dim_ok else "不一致"))
    if not dim_ok:
        errors.append("维度不一致")

    # 3) 归一化（抽样 L2 norm）
    main_norms = []
    for i in range(0, main_index.ntotal, max(1, main_index.ntotal // 5)):
        v = np.asarray(main_index.reconstruct(int(i)), dtype=np.float32)
        main_norms.append(round(float(np.linalg.norm(v)), 5))
        if len(main_norms) >= 5:
            break
    acc_norms = []
    for i in range(0, acc_emb.shape[0], max(1, acc_emb.shape[0] // 5)):
        acc_norms.append(round(float(np.linalg.norm(acc_emb[int(i)].astype(np.float32))), 5))
        if len(acc_norms) >= 5:
            break
    main_norm_ok = all(abs(n - 1.0) < 0.01 for n in main_norms)
    acc_norm_ok = all(abs(n - 1.0) < 0.01 for n in acc_norms)
    log("  主 L2 norm 抽样: %s -> %s" % (main_norms, "归一化OK" if main_norm_ok else "未归一化"))
    log("  事故 L2 norm 抽样: %s -> %s" % (acc_norms, "归一化OK" if acc_norm_ok else "未归一化"))
    if not main_norm_ok or not acc_norm_ok:
        errors.append("归一化方式不一致")

    if errors:
        log("!!! 兼容性不通过，立即停止，不修改主库:")
        for e in errors:
            log("    - " + e)
        return False, {
            "dimension_match": dim_ok,
            "index_type": main_type,
            "normalized": main_norm_ok and acc_norm_ok,
            "main_norms": main_norms,
            "accident_norms": acc_norms,
        }
    log("  兼容性: 通过")
    return True, {
        "dimension_match": dim_ok,
        "index_type": main_type,
        "normalized": True,
        "main_norms": main_norms,
        "accident_norms": acc_norms,
    }


def transform_accident_meta(item):
    """事故 metadata 对齐主库 schema（保留超集字段，补必要字段）。"""
    m = dict(item)  # 不修改源
    m["doc_type"] = ACCIDENT_DOC_TYPE
    m["document_type"] = ACCIDENT_DOCUMENT_TYPE
    m["source"] = ACCIDENT_SOURCE
    # 事故报告无标准编号，不编造
    m["code"] = str(m.get("code", "") or "")
    # title 兜底：用原文件名去扩展名
    if not m.get("title"):
        m["title"] = Path(str(m.get("source_file", "事故报告"))).stem
    # section 兜底
    if not m.get("section"):
        m["section"] = "正文"
    # 页面兜底
    if not m.get("page_start"):
        m["page_start"] = 1
    if not m.get("page_end"):
        m["page_end"] = 1
    # text 必须有（reranker 依赖）
    if "text" not in m or not m.get("text"):
        raise ValueError("事故 chunk %s 缺少 text 字段" % m.get("chunk_id"))
    return m


def dedup(main_meta, acc_meta):
    """按 chunk_id 去重。返回 (new_indices, dup_count)。"""
    existing = {m.get("chunk_id") for m in main_meta}
    new_idx = []
    dup = 0
    for i, m in enumerate(acc_meta):
        cid = m.get("chunk_id")
        if cid in existing:
            dup += 1
        else:
            new_idx.append(i)
    return new_idx, dup


def backup(main_index, main_meta):
    """第一次修改前备份主库。返回备份目录。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_dir = Path(BASE) / ("backup_before_accident_" + ts)
    bak_dir.mkdir(parents=True, exist_ok=True)
    files = [
        (VECTOR_INDEX, "faiss.index"),
        (VECTOR_METADATA, "index_metadata.json"),
        (MAIN_EMB_META, "chunks_metadata.json"),
    ]
    copied = []
    for src, name in files:
        if src.exists():
            dst = bak_dir / name
            shutil.copy2(str(src), str(dst))
            copied.append({"original": str(src), "backup": str(dst), "size_bytes": src.stat().st_size})
    manifest = {
        "backup_time": datetime.now().isoformat(),
        "backup_dir": str(bak_dir),
        "original_index": str(VECTOR_INDEX),
        "original_metadata": str(VECTOR_METADATA),
        "original_ntotal": int(main_index.ntotal),
        "original_metadata_count": len(main_meta),
        "files": copied,
    }
    with open(bak_dir / "backup_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log("备份完成: %s" % bak_dir)
    log("  原始 ntotal=%d, metadata=%d" % (main_index.ntotal, len(main_meta)))
    return bak_dir, manifest


def atomic_save(index, metadata):
    """写 .tmp → 校验 → os.replace 原子替换。"""
    idx_tmp = str(VECTOR_INDEX) + ".tmp"
    meta_tmp = str(VECTOR_METADATA) + ".tmp"
    faiss.write_index(index, idx_tmp)
    with open(meta_tmp, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)
    # 校验 tmp
    tmp_idx = faiss.read_index(idx_tmp)
    tmp_meta = json.load(open(meta_tmp, encoding="utf-8"))
    assert tmp_idx.ntotal == len(tmp_meta), \
        "tmp 校验失败: ntotal=%d != metadata=%d" % (tmp_idx.ntotal, len(tmp_meta))
    assert tmp_idx.ntotal == index.ntotal, "tmp ntotal 与内存不一致"
    # 替换
    os.replace(idx_tmp, str(VECTOR_INDEX))
    os.replace(meta_tmp, str(VECTOR_METADATA))
    log("原子替换完成: faiss.index + index_metadata.json")


def integrity_check():
    idx = faiss.read_index(str(VECTOR_INDEX))
    meta = json.load(open(VECTOR_METADATA, encoding="utf-8"))
    ok = idx.ntotal == len(meta)
    log("integrity check: ntotal=%d metadata=%d -> %s" % (idx.ntotal, len(meta), "一致" if ok else "不一致"))
    return ok, idx, meta


def main():
    log("=" * 60)
    log("事故案例 → 主 FAISS 向量知识库 合并")
    log("=" * 60)

    main_index, main_meta = load_main()
    acc_emb, acc_meta = load_accident()

    compatible, comp_info = check_compatibility(main_index, acc_emb, acc_meta)
    if not compatible:
        report = {
            "status": "ABORTED_INCOMPATIBLE",
            "before": {"main_vectors": int(main_index.ntotal), "main_metadata": len(main_meta)},
            "accident": {"chunks": len(acc_meta), "new_chunks": 0, "duplicate_chunks": 0},
            "after": {"main_vectors": int(main_index.ntotal), "main_metadata": len(main_meta)},
            "compatibility": comp_info,
            "integrity_check": False,
        }
        json.dump(report, open(MERGE_REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        raise SystemExit(1)

    # 去重
    new_idx, dup_count = dedup(main_meta, acc_meta)
    acc_docs = len({m.get("doc_id") for m in acc_meta})
    log("-" * 60)
    log("去重结果")
    log("  事故总 chunk: %d" % len(acc_meta))
    log("  已存在 chunk: %d" % dup_count)
    log("  新增 chunk: %d" % len(new_idx))
    log("  事故文档数: %d" % acc_docs)

    before_ntotal = int(main_index.ntotal)
    before_meta = len(main_meta)

    report = {
        "status": "",
        "before": {"main_vectors": before_ntotal, "main_metadata": before_meta},
        "accident": {
            "documents": acc_docs,
            "chunks": len(acc_meta),
            "new_chunks": len(new_idx),
            "duplicate_chunks": dup_count,
        },
        "after": {"main_vectors": before_ntotal, "main_metadata": before_meta},
        "compatibility": comp_info,
        "integrity_check": False,
        "backup": None,
    }

    if len(new_idx) == 0:
        log("无新增 chunk（幂等：已全部存在于主库），不做任何修改。")
        report["status"] = "NOOP_IDEMPOTENT"
        ok, _, _ = integrity_check()
        report["integrity_check"] = ok
        json.dump(report, open(MERGE_REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log("合并报告: %s" % MERGE_REPORT)
        return

    # 备份（第一次修改前）
    log("-" * 60)
    bak_dir, manifest = backup(main_index, main_meta)
    report["backup"] = {"dir": str(bak_dir), "manifest": str(bak_dir / "backup_manifest.json")}

    # 转换 metadata（仅新增部分）
    new_meta = [transform_accident_meta(acc_meta[i]) for i in new_idx]
    new_vectors = acc_emb[new_idx].astype("float32")

    # 顺序一致性校验：新增向量行数 == 新增 metadata 条数
    assert new_vectors.shape[0] == len(new_meta), "新增向量/元数据数量不一致"

    # append 向量
    log("-" * 60)
    log("append %d 条事故向量到主 FAISS..." % len(new_idx))
    main_index.add(new_vectors)
    assert main_index.ntotal == before_ntotal + len(new_idx), "append 后 ntotal 不符"

    # append metadata（顺序严格对应）
    merged_meta = list(main_meta) + new_meta
    assert len(merged_meta) == main_index.ntotal, "合并后 metadata 与 ntotal 不一致"

    # 原子保存
    atomic_save(main_index, merged_meta)

    # integrity check
    log("-" * 60)
    ok, idx, meta = integrity_check()

    # 组成分布
    from collections import Counter
    dt = Counter(str(m.get("document_type", m.get("doc_type", "?"))) for m in meta)
    doc_type = Counter(str(m.get("doc_type", m.get("document_type", "?"))) for m in meta)
    log("document_type 分布: %s" % dict(dt))
    log("doc_type 分布: %s" % dict(doc_type))

    report["status"] = "MERGED" if ok else "INTEGRITY_FAILED"
    report["after"] = {"main_vectors": int(idx.ntotal), "main_metadata": len(meta)}
    report["integrity_check"] = ok
    report["distribution"] = {"document_type": dict(dt), "doc_type": dict(doc_type)}
    json.dump(report, open(MERGE_REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("合并报告: %s" % MERGE_REPORT)
    log("=" * 60)
    log("完成。主库: %d -> %d 条" % (before_ntotal, idx.ntotal))


if __name__ == "__main__":
    main()
