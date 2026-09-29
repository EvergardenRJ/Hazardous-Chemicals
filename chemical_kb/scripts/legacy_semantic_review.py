#!/usr/bin/env python3
"""Source-grounded, resumable semantic review of private legacy relation candidates.

Only assertions independently mapped to the current schema and supported by an
exact source quote are written to the private approved review file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.config import BASE_DIR
from core.kg.extractor import parse_llm_json
from core.kg.schema_manager import SchemaManager

ROOT = BASE_DIR / "data/legacy"
DB = ROOT / "hazmat_legacy.sqlite"
APPROVED = ROOT / "reviewed.jsonl"
SYSTEM = (
    "You audit chemical-safety knowledge graph relationships. Use only the supplied "
    "source passage. Return strict JSON. Reject if the source does not directly state "
    "the exact subject, object, direction and relation. Do not infer a law, duty or "
    "causal link from co-occurrence."
)


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def parsed(raw: str) -> dict:
    value, _ = parse_llm_json(raw)
    return value if isinstance(value, dict) else {}


def entity_id(kind: str, label: str) -> str:
    digest = hashlib.sha1((kind + "|" + normalized(label)).encode("utf-8")).hexdigest()[:20]
    return "LEGACY_ENTITY:" + digest


def relation_options(schema: SchemaManager) -> list[dict]:
    return [
        {"id": row["id"], "name": row.get("name"), "domain": row.get("domain"),
         "range": row.get("range"), "meaning": str(row.get("description") or "")[:110]}
        for row in schema.schema.get("relation_types", [])
    ]


def candidates(db: sqlite3.Connection) -> dict[str, list[tuple]]:
    rows = db.execute("""
        SELECT r.id,r.source_entity,r.relation_type,r.target_entity,
               e.chunk_id,e.excerpt,
               COALESCE(body.document_id,v.document_id) AS document_id,
               COALESCE(body.content,c.text) AS source_text
        FROM graph_relationships r
        JOIN legacy_relation_audits a ON a.relation_id=r.id
        JOIN legacy_relation_evidence e ON e.relation_id=r.id
        LEFT JOIN chunks c ON c.id=e.chunk_id AND e.match_kind<>'document_body'
        LEFT JOIN document_versions v ON v.id=c.document_version_id
        LEFT JOIN document_versions body
          ON body.id=substr(e.chunk_id,8) AND e.match_kind='document_body'
        WHERE a.decision='needs_semantic_review'
          AND COALESCE(body.document_id,v.document_id) IS NOT NULL
        ORDER BY r.id,e.chunk_id
    """)
    groups = defaultdict(list)
    for row in rows:
        groups[row[0]].append(row)
    return groups


def exact_quote(quote: str, source: str, target: str, chunk: str) -> bool:
    text = normalized(quote)
    return (bool(text) and len(text) <= 500 and text in normalized(chunk)
            and normalized(source) in text and normalized(target) in text)


def assess(model, schema, options, row):
    rid, source, old_relation, target, chunk_id, excerpt, doc_id, full_text = row
    prompt = json.dumps({
        "old_triple": {"subject": source, "old_relation": old_relation, "object": target},
        "source_passage": excerpt, "allowed_relation_types": options,
        "task": ("If the passage explicitly supports a relationship between the "
                 "exact named endpoints, map it to ONE allowed relation id and types. "
                 "Otherwise reject or mark uncertain. Return JSON keys decision "
                 "(valid/reject/uncertain), predicate, subject_type, object_type, "
                 "quote, reason. Quote must be a literal substring of the passage "
                 "containing both endpoint names.")
    }, ensure_ascii=False)
    first = parsed(model.generate(prompt, system_prompt=SYSTEM, max_new_tokens=500,
                                  temperature=0.1))
    decision = str(first.get("decision") or "").lower()
    if decision != "valid":
        return ("rejected" if decision == "reject" else "needs_review",
                str(first.get("reason") or "No supported mapping")[:500], None)
    predicate = schema.normalize_relation(str(first.get("predicate") or ""))
    subject_type = schema.normalize_entity_type(str(first.get("subject_type") or ""))
    object_type = schema.normalize_entity_type(str(first.get("object_type") or ""))
    quote = str(first.get("quote") or "").strip()
    if not predicate or not subject_type or not object_type:
        return "needs_review", "Model returned unknown schema type or relation", None
    if not schema.validate_relation_domain(subject_type, predicate, object_type):
        return "needs_review", "Schema domain/range mismatch", None
    if not exact_quote(quote, source, target, excerpt) or not exact_quote(
        quote, source, target, full_text
    ):
        return "needs_review", "Exact quote or endpoints not found in old document evidence", None
    second_prompt = json.dumps({
        "source_passage": excerpt,
        "proposed_assertion": {"subject": source, "subject_type": subject_type,
                               "predicate": predicate, "object": target,
                               "object_type": object_type, "quote": quote},
        "task": ("Independently check the quote and surrounding passage. Is this "
                 "exact directed relation explicitly supported? Return strict JSON "
                 "with decision valid/reject/uncertain and reason. Co-occurrence "
                 "alone is not enough.")
    }, ensure_ascii=False)
    second = parsed(model.generate(second_prompt, system_prompt=SYSTEM,
                                   max_new_tokens=220, temperature=0.1))
    if str(second.get("decision") or "").lower() != "valid":
        status = "rejected" if second.get("decision") == "reject" else "needs_review"
        return status, str(second.get("reason") or "Independent review uncertain")[:500], None
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assertion = {
        "assertion_id": "LEGACYREL:" + rid,
        "subject_id": entity_id(subject_type, source),
        "subject_type": subject_type, "subject_label": source,
        "predicate": predicate,
        "object_id": entity_id(object_type, target),
        "object_type": object_type, "object_label": target, "object_kind": "entity",
        "source_doc_id": "LEGACY:" + doc_id,
        "source_chunk_id": "LEGACY:" + chunk_id,
        "source_text_quote": quote,
        "confidence": 0.9, "recorded_at": now,
        "legacy_relation_id": rid, "legacy_relation_type": old_relation,
    }
    return "approved", "Two-pass source and schema review", assertion


def export_approved(db: sqlite3.Connection) -> int:
    rows = db.execute("""
        SELECT relation_id,assertion_json,reviewed_at,reviewed_by,reason
        FROM legacy_relation_audits
        WHERE decision='approved' AND assertion_json<>'' ORDER BY relation_id
    """).fetchall()
    existing = []
    if APPROVED.exists():
        with APPROVED.open(encoding="utf-8") as stream:
            existing = [json.loads(line) for line in stream if line.strip()]
    known = {row.get("review_id") for row in existing}
    baseline = []
    for rid, payload, when, reviewer, reason in rows:
        review_id = "REV_LEGACY:" + rid
        if review_id in known:
            continue
        assertion = json.loads(payload)
        baseline.append({
            "review_id": review_id, "assertion_id": assertion["assertion_id"],
            "decision": "approved", "original_assertion": assertion,
            "reviewed_at": when, "reviewed_by": reviewer,
            "review_comment": reason
        })
    temporary = APPROVED.with_suffix(".building")
    with temporary.open("w", encoding="utf-8") as stream:
        for record in baseline + existing:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(temporary, APPROVED)
    return len(rows)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with sqlite3.connect(args.db, timeout=60) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(legacy_relation_audits)")}
        if "assertion_json" not in columns:
            db.execute("ALTER TABLE legacy_relation_audits ADD COLUMN assertion_json TEXT NOT NULL DEFAULT ''")
            db.commit()
        groups = candidates(db)
        print(json.dumps({"pending_relations": len(groups)}, ensure_ascii=False), flush=True)
        if args.dry_run:
            return
        for entry in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                command = entry.read_bytes()
            except OSError:
                continue
            if b"scripts/kg/extract_corpus.py" in command and entry.parent.name != str(os.getpid()):
                raise SystemExit("Full-corpus GPU extraction is still running; review deferred")
        if not groups:
            print(json.dumps({"approved_file_rows": export_approved(db)}), flush=True)
            return
        from core.llm import QwenLLM
        model = QwenLLM()
        schema = SchemaManager()
        options = relation_options(schema)
        selected = list(groups.items())[:args.limit or None]
        for position, (rid, evidence) in enumerate(selected, 1):
            outcome = ("needs_review", "No conclusive source evidence", None)
            for row in evidence:
                try:
                    candidate = assess(model, schema, options, row)
                except Exception as exc:
                    candidate = ("needs_semantic_review",
                                 "Model error: " + type(exc).__name__, None)
                if candidate[0] == "approved":
                    outcome = candidate
                    break
                if candidate[0] == "needs_semantic_review":
                    outcome = candidate
                    break
                if outcome[0] != "needs_review" or candidate[0] == "needs_review":
                    outcome = candidate
            status, reason, assertion = outcome
            if status == "needs_semantic_review":
                print(json.dumps({"processed": position, "total": len(selected),
                                  "model_error": True}), flush=True)
                break
            with db:
                db.execute("""
                    UPDATE legacy_relation_audits
                    SET decision=?,reason=?,evidence_chunk_id=?,evidence_quote=?,
                        normalized_predicate=?,reviewed_at=?,reviewed_by=?,
                        assertion_json=?
                    WHERE relation_id=?
                """, (status, reason, evidence[0][4],
                      assertion["source_text_quote"] if assertion else "",
                      assertion["predicate"] if assertion else "",
                      datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "adamin", json.dumps(assertion, ensure_ascii=False) if assertion else "",
                      rid))
            if position == 1 or position % 10 == 0:
                print(json.dumps({"processed": position, "total": len(selected)}), flush=True)
        count = export_approved(db)
        statuses = dict(db.execute(
            "SELECT decision,COUNT(*) FROM legacy_relation_audits GROUP BY decision"
        ))
        print(json.dumps({"audit": statuses, "approved_file_rows": count},
                         ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
