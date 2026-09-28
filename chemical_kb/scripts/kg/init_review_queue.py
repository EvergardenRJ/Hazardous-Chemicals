#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 v0.1 已落盘的 Candidate Assertions 导入 Review Queue（pending.jsonl）。

数据源：data/kg/output/{accident,standard}_candidate_assertions.jsonl 以及
validation_failed.jsonl（若有）。幂等：按 assertion_id 去重，重复初始化不产生重复。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kg.review_manager import ReviewManager
from core.kg.schema_repository import OUTPUT_DIR


def load_candidates():
    rows = []
    for prefix in ("accident", "standard"):
        for suffix in ("candidate_assertions", "validation_failed"):
            p = OUTPUT_DIR / f"{prefix}_{suffix}.jsonl"
            if not p.exists():
                continue
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
    return rows


def main():
    candidates = load_candidates()
    print(f"== Candidate 总数: {len(candidates)} ==")
    mgr = ReviewManager()
    result = mgr.init_queue(candidates)
    print(f"  成功导入 pending: {result['imported']}")
    print(f"  重复跳过: {result['skipped']}")
    print(f"  当前 pending: {result['pending_now']}")
    print(f"  pending 路径: {mgr.pending_file}")
    stats = mgr.get_review_statistics()["counts"]
    print(f"  统计: pending={stats['pending']} approved={stats['approved']} "
          f"rejected={stats['rejected']} modified={stats['modified']} skipped={stats['skipped']}")


if __name__ == "__main__":
    main()
