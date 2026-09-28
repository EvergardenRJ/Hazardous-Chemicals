#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSONL → Neo4j 幂等同步。

数据源：data/kg/review/pending.jsonl（候选）+ reviewed.jsonl（已审核）。
- approved → 原断言（review_status=approved）
- modified → corrected_assertion（review_status=approved）
- rejected → 不进入正常关系网络
节点按 canonical_id MERGE，关系按 assertion_id MERGE，重复运行不重复创建。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.neo4j_store import Neo4jStore
from core.kg.review_manager import ReviewManager


def load_assertions():
    mgr = ReviewManager()
    rows = []
    for a in mgr.get_pending():
        a = dict(a)
        a["review_status"] = "pending"
        rows.append(a)
    for r in mgr.get_reviewed():
        decision = r.get("decision", "")
        if decision == "approved":
            a = dict(r.get("original_assertion") or {})
            a["review_status"] = "approved"
            rows.append(a)
        elif decision == "modified":
            a = dict(r.get("corrected_assertion") or {})
            a["review_status"] = "approved"
            if a.get("assertion_id"):
                rows.append(a)
        # rejected 跳过
    return rows


def main():
    store = Neo4jStore()
    if not store.is_connected():
        print("Neo4j 未连接：请设置 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD 或 configs/kg/neo4j.yaml")
        return 1

    before_n = store.count_nodes()
    before_r = store.count_relations()

    assertions = load_assertions()
    print(f"待同步断言: {len(assertions)}")
    for a in assertions:
        try:
            store.merge_assertion(a)
        except Exception as e:
            print(f"  跳过 {a.get('assertion_id', '?')}: {e}")

    after_n = store.count_nodes()
    after_r = store.count_relations()
    print(f"节点: {before_n} → {after_n}（新增 {after_n - before_n}）")
    print(f"关系: {before_r} → {after_r}（新增 {after_r - before_r}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
