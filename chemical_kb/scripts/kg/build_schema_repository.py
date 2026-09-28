#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 data/kg/schema_repository.json：序列化 SchemaRepository 的 47 条可检索条目。

由真实 SchemaRepository 代码构造（非手抄），作为 Schema Repository 的独立落盘交付物，
与 FAISS 索引配套的 schema_index/schema_metadata.json 同源。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.schema_repository import SchemaRepository, KG_DATA_DIR


def main():
    repo = SchemaRepository()
    items = repo.items

    out = {
        "version": "1.0",
        "schema_version": "1.0",
        "name": "Schema Repository",
        "description": (
            "由 schema_v1.json 构造的可检索条目（15 实体 + 32 关系），"
            "供 Schema Retriever 做向量检索；embedding_text 由 "
            "name + 中文名 + definition + subject/object + aliases + keywords + examples 组合。"
        ),
        "entity_count": len(repo.entity_items()),
        "relation_count": len(repo.relation_items()),
        "total_items": len(items),
        "items": items,
    }

    dest = KG_DATA_DIR / "schema_repository.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("WROTE", dest)
    print("entity_count =", len(repo.entity_items()))
    print("relation_count =", len(repo.relation_items()))
    print("total_items =", len(items))


if __name__ == "__main__":
    main()
