# -*- coding: utf-8 -*-
"""Review Manager：pending / reviewed 队列 + 统计 + schema extension proposal。

文件布局（data/kg/review/）：
- pending.jsonl                    待审核的 CandidateAssertion
- reviewed.jsonl                   已审核的 ReviewRecord（不物理删除历史）
- schema_extension_proposals.jsonl 待决定的 Schema 扩展提案

原则：只有真实人工输入 approve / reject / modify 才形成 reviewed；Agent 不替用户审核。
"""
import json
from pathlib import Path
from datetime import datetime

from core.config import BASE_DIR

REVIEW_DIR = BASE_DIR / "data" / "kg" / "review"


def _now():
    return datetime.now().isoformat(timespec="seconds")


class ReviewManager:
    def __init__(self, review_dir=None):
        self.review_dir = Path(review_dir) if review_dir else REVIEW_DIR
        self.review_dir.mkdir(parents=True, exist_ok=True)
        self.pending_file = self.review_dir / "pending.jsonl"
        self.reviewed_file = self.review_dir / "reviewed.jsonl"
        self.proposals_file = self.review_dir / "schema_extension_proposals.jsonl"

    # ------------------------------------------------------------------ #
    # 文件 IO
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_jsonl(path):
        if not path.exists():
            return []
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    @staticmethod
    def _append_jsonl(path, rows):
        with open(path, "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    # ------------------------------------------------------------------ #
    # 队列初始化（幂等）
    # ------------------------------------------------------------------ #
    def init_queue(self, assertions, reset=False):
        """把候选断言导入 pending（按 assertion_id 去重）。返回统计 dict。"""
        if reset:
            self.pending_file.write_text("", encoding="utf-8")
        existing = {a.get("assertion_id") for a in self.get_pending()}
        imported = skipped = 0
        rows = []
        for a in assertions:
            aid = a.get("assertion_id", "")
            if not aid or aid in existing:
                skipped += 1
                continue
            row = dict(a)
            row["review_status"] = "pending"
            rows.append(row)
            existing.add(aid)
            imported += 1
        self._append_jsonl(self.pending_file, rows)
        return {"total": len(assertions), "imported": imported, "skipped": skipped,
                "pending_now": len(self.get_pending())}

    # ------------------------------------------------------------------ #
    # 读取
    # ------------------------------------------------------------------ #
    def get_pending(self):
        return self._read_jsonl(self.pending_file)

    def get_reviewed(self):
        return self._read_jsonl(self.reviewed_file)

    def get_next_pending(self):
        rows = self.get_pending()
        return rows[0] if rows else None

    # ------------------------------------------------------------------ #
    # 提交审核
    # ------------------------------------------------------------------ #
    def submit_review(self, record):
        """把 ReviewRecord 写入 reviewed.jsonl，并从 pending 移除对应 assertion_id。"""
        rec = record if isinstance(record, dict) else record.to_dict()
        if not rec.get("review_id"):
            rec["review_id"] = self._make_review_id(rec.get("assertion_id", ""))
        if not rec.get("reviewed_at"):
            rec["reviewed_at"] = _now()
        self._append_jsonl(self.reviewed_file, [rec])
        self._remove_from_pending(rec.get("assertion_id", ""))
        return rec

    def _remove_from_pending(self, assertion_id):
        rows = [a for a in self.get_pending() if a.get("assertion_id") != assertion_id]
        with open(self.pending_file, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    @staticmethod
    def _make_review_id(assertion_id):
        return f"REV_{assertion_id}_{int(datetime.now().timestamp() * 1000000)}"

    # ------------------------------------------------------------------ #
    # Schema Extension Proposal
    # ------------------------------------------------------------------ #
    def add_schema_extension_proposal(self, proposal):
        p = proposal if isinstance(proposal, dict) else proposal.to_dict()
        if not p.get("proposal_id"):
            p["proposal_id"] = self._make_proposal_id()
        if not p.get("created_at"):
            p["created_at"] = _now()
        self._append_jsonl(self.proposals_file, [p])
        return p

    def get_schema_extension_proposals(self):
        return self._read_jsonl(self.proposals_file)

    @staticmethod
    def _make_proposal_id():
        return f"PROP_{int(datetime.now().timestamp() * 1000000)}"

    # ------------------------------------------------------------------ #
    # 统计
    # ------------------------------------------------------------------ #
    def get_review_statistics(self):
        from core.kg.relation_catalog import current_relations
        catalog = current_relations(self.get_reviewed(), self.get_pending())
        counts = {"pending": 0, "approved": 0, "rejected": 0,
                  "modified": 0, "skipped": 0}
        error_dist = {}
        for item in catalog:
            status = item["status"]
            if status in counts:
                counts[status] += 1
        for record in self.get_reviewed():
            et = record.get("error_type")
            if et:
                error_dist[et] = error_dist.get(et, 0) + 1
        counts["total"] = len(catalog)
        return {"counts": counts, "error_type_distribution": error_dist}

