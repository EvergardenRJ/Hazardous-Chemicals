# -*- coding: utf-8 -*-
"""Schema Retriever：复用 BGE-M3 对 schema 条目做向量检索，Entity/Relation 分开 TopK。"""
import json

import faiss
import numpy as np

from core.embedding import EmbeddingModel
from core.kg.schema_repository import SCHEMA_INDEX_DIR


class SchemaRetriever:
    """加载 FAISS(IndexFlatIP) + metadata，返回 {entities, relations} TopK。"""

    def __init__(self, index_path=None, metadata_path=None, embedding_model=None):
        index_path = index_path or (SCHEMA_INDEX_DIR / "schema.index")
        metadata_path = metadata_path or (SCHEMA_INDEX_DIR / "schema_metadata.json")
        self.index = faiss.read_index(str(index_path))
        with open(metadata_path, encoding="utf-8") as f:
            self.metadata = json.load(f)
        self.embedding_model = embedding_model or EmbeddingModel()

    def retrieve(self, text, top_k_entities=8, top_k_relations=12):
        """对 text 编码后检索，Entity / Relation 分开取 TopK。

        由于 repository 只有 ~47 条，直接 search k=ntotal 取全量打分，再按 schema_kind
        切分并截取 TopK，保证 Entity 与 Relation 各自独立排序，而不是混排截断。
        """
        vec = self.embedding_model.encode(text)
        vec = np.asarray(vec, dtype="float32")
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        k = self.index.ntotal
        scores, idxs = self.index.search(vec, k)

        entities, relations = [], []
        for score, idx in zip(scores[0], idxs[0]):
            if idx < 0:
                continue
            item = self.metadata[int(idx)]
            entry = {
                "name": item.get("name", ""),
                "name_zh": item.get("name_zh", ""),
                "definition": item.get("definition", ""),
                "score": float(score),
                "subject_types": item.get("subject_types", []),
                "object_types": item.get("object_types", []),
            }
            if item.get("schema_kind") == "entity":
                entities.append(entry)
            else:
                relations.append(entry)
        return {
            "entities": entities[:top_k_entities],
            "relations": relations[:top_k_relations],
        }
