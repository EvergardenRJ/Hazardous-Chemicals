#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建 Schema 检索索引（schema.index / schema_metadata.json / schema_embeddings.npy）。"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import faiss
import numpy as np

from core.embedding import EmbeddingModel
from core.kg.schema_manager import SchemaManager
from core.kg.schema_repository import SchemaRepository, SCHEMA_INDEX_DIR


def main():
    print("== 构建 Schema Repository ==")
    sm = SchemaManager()
    print(f"  schema_version={sm.version}  entities={sm.entity_count}  relations={sm.relation_count}")
    repo = SchemaRepository(sm)
    items = repo.items
    print(f"  repository items={len(items)}")

    print("== 编码 embedding (BGE-M3) ==")
    emb = EmbeddingModel()
    vecs = []
    for t in [it["embedding_text"] for it in items]:
        v = np.asarray(emb.encode(t), dtype="float32").reshape(1, -1)
        vecs.append(v)
    mat = np.vstack(vecs).astype("float32")
    faiss.normalize_L2(mat)
    print(f"  matrix shape={mat.shape}")

    idx = faiss.IndexFlatIP(mat.shape[1])
    idx.add(mat)
    print(f"  index ntotal={idx.ntotal}")

    SCHEMA_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(idx, str(SCHEMA_INDEX_DIR / "schema.index"))
    np.save(str(SCHEMA_INDEX_DIR / "schema_embeddings.npy"), mat)
    with open(SCHEMA_INDEX_DIR / "schema_metadata.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print("== 验证检索 ==")
    from core.kg.schema_retriever import SchemaRetriever
    ret = SchemaRetriever(embedding_model=emb)
    for query in ["液氯贮槽接受液氯应小于1.20kg/L", "融汇化工液氯充装导致泄漏中毒"]:
        r = ret.retrieve(query, top_k_entities=8, top_k_relations=12)
        print(f"\nQ: {query}")
        print("  entities:", [f"{e['name']}({e['name_zh']})" for e in r["entities"]])
        print("  relations:", [f"{x['name']}({x['name_zh']})" for x in r["relations"]])
    print("\nDONE: schema index built at", SCHEMA_INDEX_DIR)


if __name__ == "__main__":
    main()
