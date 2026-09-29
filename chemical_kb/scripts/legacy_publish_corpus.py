#!/usr/bin/env python3
"""Publish only source-grounded, schema-valid, semantically audited legacy chunks."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.config import BASE_DIR
from core.kg.relation_catalog import validate_assertion, approved_assertions
from core.kg.schema_manager import SchemaManager

ROOT = BASE_DIR / "data/legacy"
CORPUS = ROOT / "corpus.sqlite"
METADATA = ROOT / "chunks_metadata.json"
REVIEWS = ROOT / "reviewed.jsonl"


def same_text(quote: str, source: str) -> bool:
    compact = lambda value: re.sub(r"\s+", "", str(value or ""))
    return bool(quote) and compact(quote) in compact(source)


def rows_to_publish(db, lookup, existing, schema):
    known_ids = {str(row.get("assertion_id") or "") for row in existing}
    known_triples = {
        (a.get("source_chunk_id"), a.get("subject_label"),
         a.get("predicate"), a.get("object_label"))
        for a in approved_assertions(existing)
    }
    accepted = []
    skipped = {"duplicate": 0, "source": 0, "schema": 0}
    cursor = db.execute("""
        SELECT a.assertion_id,a.chunk_id,a.validation_status,a.evidence_ok,
               a.payload,v.reason,v.reviewed_at
        FROM assertions a JOIN candidate_audits v ON v.assertion_id=a.assertion_id
        WHERE v.decision='valid' ORDER BY a.assertion_id
    """)
    for aid, cid, validation, evidence, payload, reason, when in cursor:
        new_id = "LEGACYCORPUS:" + aid
        if new_id in known_ids:
            skipped["duplicate"] += 1
            continue
        meta = lookup.get(cid)
        assertion = json.loads(payload)
        if (not meta or validation != "passed" or not evidence
                or assertion.get("source_chunk_id") != cid
                or assertion.get("source_doc_id") != meta["doc_id"]
                or not same_text(assertion.get("source_text_quote"),
                                 meta.get("text"))):
            skipped["source"] += 1
            continue
        assertion["assertion_id"] = new_id
        try:
            validate_assertion(assertion, schema)
        except ValueError:
            skipped["schema"] += 1
            continue
        triple = (cid, assertion.get("subject_label"), assertion.get("predicate"),
                  assertion.get("object_label"))
        if triple in known_triples:
            skipped["duplicate"] += 1
            continue
        known_triples.add(triple)
        accepted.append({
            "review_id": "REV_LEGACYCORPUS:" + aid,
            "assertion_id": new_id, "decision": "approved",
            "original_assertion": assertion,
            "reviewed_at": when or datetime.now(timezone.utc).isoformat(),
            "reviewed_by": "adamin",
            "review_comment": "Legacy corpus source, schema and semantic audit: " +
                              str(reason or "")[:300],
        })
    return accepted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=CORPUS)
    parser.add_argument("--metadata", type=Path, default=METADATA)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    lookup = {row["chunk_id"]: row for row in json.loads(
        args.metadata.read_text(encoding="utf-8")
    )}
    existing = []
    if REVIEWS.exists():
        with REVIEWS.open(encoding="utf-8") as stream:
            existing = [json.loads(line) for line in stream if line.strip()]
    with sqlite3.connect(f"file:{args.db.resolve().as_posix()}?mode=ro", uri=True) as db:
        accepted, skipped = rows_to_publish(db, lookup, existing, SchemaManager())
    if not args.dry_run and accepted:
        temporary = REVIEWS.with_suffix(".building")
        with temporary.open("w", encoding="utf-8") as stream:
            for record in accepted + existing:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.replace(temporary, REVIEWS)
    print(json.dumps({"ready": len(accepted), "skipped": skipped,
                      "published": 0 if args.dry_run else len(accepted)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
