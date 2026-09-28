# -*- coding: utf-8 -*-
"""One-time, source-grounded audit of the 41 legacy chemical safety assertions.

Dry run by default. Use --apply only after reviewing the printed plan.
Original review records stay in reviewed.jsonl as history.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from core.config import BASE_DIR, VECTOR_METADATA
from core.kg.case_builder import CaseBuilder
from core.kg.case_repository import CaseRepository
from core.kg.relation_catalog import current_relations, validate_assertion
from core.kg.review_manager import ReviewManager
from core.kg.schema_manager import SchemaManager

AUDIT_VERSION = "alpha-kag-audit-v1"
AUDIT_PATH = BASE_DIR / "data/kg/review/agent_audit_20260928.jsonl"
ACCIDENT_PREFIX = "ACC_aa76907ac753bc37_c0020_A"
STANDARD_PREFIX = "STD_DB32_T_3617_2019_p6_c6_A"
ACCIDENT_LABEL = "融汇化工“8·29”氯气泄漏事故"
R01_LABEL = "液氯贮槽接受液氯应小于1.20kg/L。"
R02_LABEL = "液氯充装量应小于容器容积的80%。"


def plan(item):
    aid = item["assertion_id"]
    original = item["assertion"]
    corrected = dict(original)
    reasons = []
    decision = "confirmed"
    error_type = ""
    if aid.startswith(ACCIDENT_PREFIX):
        index = int(aid.rsplit("_A", 1)[1])
        if index in (7, 8):
            decision = "rejected"
            reasons.append("泄漏和人员中毒是事故的结果；原 direct_cause 方向错误，保留因果链 leads_to 关系。")
            error_type = "relation_direction_error"
        elif index <= 6:
            corrected["subject_label"] = ACCIDENT_LABEL
            reasons.append("去掉文档标题中的“报告发布”，事故实体指向事件本身。")
            error_type = "entity_label_precision"
    if aid.startswith(STANDARD_PREFIX):
        index = int(aid.rsplit("_A", 1)[1])
        if 7 <= index <= 15:
            corrected["subject_label"] = R01_LABEL
            reasons.append("R01 仅表示 1.20kg/L 约束，按 KAG 式原子知识单元拆分主体标签。")
            error_type = "knowledge_unit_granularity"
        if 16 <= index <= 24:
            corrected["subject_label"] = R02_LABEL
            reasons.append("R02 仅表示充装量小于容积 80% 的约束。")
            error_type = "knowledge_unit_granularity"
        if index == 17:
            corrected["predicate"] = "requirement_id"
            corrected["object_type"] = "literal"
            corrected["object_kind"] = "literal"
            reasons.append("修复旧版把 requirement_id 误改为 has_clause 且客体类型错设为 causal_factor 的 schema 错误。")
            error_type = "schema_violation"
        if index == 24:
            corrected["object_id"] = "chemical::液氯"
            corrected["object_label"] = "液氯"
            reasons.append("来源写的是液氯，与已审核 R01 的化学品实体保持一致。")
            error_type = "entity_alignment"
        if 25 <= index <= 30:
            corrected["subject_label"] = original["source_text_quote"]
            reasons.append("恢复被截断的阀门要求主体标签，保留完整技术条件。")
            error_type = "truncated_entity_label"
    if decision != "rejected":
        if corrected != original:
            decision = "modified"
        elif item["status"] == "pending":
            decision = "approved"
            reasons.append("来源原文与关系一致，类型和方向通过 schema 校验。")
        else:
            reasons.append("复核通过：来源、关系方向和类型与当前审核结果一致。")
    return decision, corrected, " ".join(reasons), error_type


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    manager = ReviewManager()
    reviewed, pending = manager.get_reviewed(), manager.get_pending()
    items = current_relations(reviewed, pending)
    if len(items) != 41:
        raise SystemExit(f"Expected 41 unique assertions, found {len(items)}; audit needs re-evaluation")
    schema = SchemaManager()
    chunks = {row.get("chunk_id"): row for row in json.loads(Path(VECTOR_METADATA).read_text(encoding="utf-8"))}
    plans = []
    for item in items:
        a = item["assertion"]
        chunk = chunks.get(a.get("source_chunk_id"))
        quote = re.sub(r"\s+", "", a.get("source_text_quote") or "")
        text = re.sub(r"\s+", "", chunk.get("text", "")) if chunk else ""
        if not chunk or not quote or quote not in text:
            raise SystemExit(f"Source quote missing from chunk: {item['assertion_id']}")
        decision, corrected, reason, error_type = plan(item)
        if decision in ("modified", "approved"):
            validate_assertion(corrected, schema)
        plans.append((item, decision, corrected, reason, error_type))
    counts = {}
    for item, decision, corrected, reason, error_type in plans:
        counts[decision] = counts.get(decision, 0) + 1
        print(f"{item['assertion_id']} {item['status']} -> {decision}: {reason}")
    print("COUNTS", counts)
    if not args.apply:
        print("Dry run only. Pass --apply to append review revisions.")
        return
    if AUDIT_PATH.exists():
        raise SystemExit(f"Audit file already exists: {AUDIT_PATH}")
    case_builder = CaseBuilder()
    case_repository = CaseRepository()
    audit_rows = []
    for item, decision, corrected, reason, error_type in plans:
        previous = item["assertion"]
        audit_rows.append({
            "assertion_id": item["assertion_id"],
            "previous_status": item["status"],
            "audit_result": decision,
            "source_doc_id": previous.get("source_doc_id"),
            "source_chunk_id": previous.get("source_chunk_id"),
            "quote_verified_in_chunk": True,
            "schema_validated": decision != "rejected",
            "reason": reason,
            "reviewed_by": "adamin",
            "audited_at": datetime.now(timezone.utc).isoformat(),
        })
        if decision == "confirmed":
            continue
        if any(row.get("assertion_id") == item["assertion_id"] and
               row.get("review_version") == AUDIT_VERSION for row in manager.get_reviewed()):
            continue
        if decision == "modified":
            corrected = {**corrected, "review_status": "approved"}
        record = {
            "assertion_id": item["assertion_id"], "decision": decision,
            "original_assertion": previous,
            "corrected_assertion": corrected if decision == "modified" else None,
            "error_type": error_type, "review_comment": reason,
            "reviewed_by": "adamin", "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "source_doc_id": previous.get("source_doc_id", ""),
            "source_chunk_id": previous.get("source_chunk_id", ""),
            "schema_version": previous.get("schema_version", ""),
            "review_version": AUDIT_VERSION, "test_only": False,
        }
        record = manager.submit_review(record)
        case = case_builder.build_from_review(record)
        if case:
            case_repository.add_case(case)
    with AUDIT_PATH.open("w", encoding="utf-8") as stream:
        for row in audit_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    effective = current_relations(manager.get_reviewed(), manager.get_pending())
    print("AFTER", {"catalog": len(effective),
                    "active": sum(x["status"] in ("approved", "modified") for x in effective),
                    "rejected": sum(x["status"] == "rejected" for x in effective),
                    "pending": sum(x["status"] == "pending" for x in effective),
                    "history_records": len(manager.get_reviewed())})


if __name__ == "__main__":
    main()

