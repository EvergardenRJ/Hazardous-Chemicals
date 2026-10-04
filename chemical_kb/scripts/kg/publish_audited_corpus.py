#!/usr/bin/env python3
"""Publish only semantically audited, source-grounded main corpus assertions.

Candidates and deterministic flags stay in corpus.sqlite. This command appends
approved review events only after rechecking the source text and current schema.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.config import BASE_DIR, VECTOR_METADATA
from core.kg.relation_catalog import approved_assertions, validate_assertion
from core.kg.schema_manager import SchemaManager

CORPUS = BASE_DIR / "data/kg/batch_extraction/corpus.sqlite"
REVIEWS = BASE_DIR / "data/kg/review/reviewed.jsonl"
LEGACY_REVIEWS = BASE_DIR / "data/legacy/reviewed.jsonl"
BACKUPS = Path("/autodl-fs/data/alpha-corpus-checkpoints")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def same_text(quote: str, source: str) -> bool:
    compact = lambda value: re.sub(r"\s+", "", str(value or ""))
    return bool(quote) and compact(quote) in compact(source)


def eligible(db, lookup, existing, schema):
    known_ids = {str(row.get("assertion_id") or "") for row in existing}
    known_triples = {
        (a.get("source_chunk_id"), a.get("subject_id"),
         a.get("predicate"), a.get("object_id"))
        for a in approved_assertions(existing)
    }
    accepted = []
    skipped = {"duplicate": 0, "source": 0, "schema": 0, "audit_method": 0}
    cursor = db.execute("""
        SELECT a.assertion_id,a.chunk_id,a.validation_status,a.evidence_ok,
               a.payload,v.reason,v.reviewed_at,v.method
        FROM assertions a JOIN candidate_audits v ON v.assertion_id=a.assertion_id
        WHERE v.decision='valid' ORDER BY a.assertion_id
    """)
    for aid, cid, validation, evidence, payload, reason, reviewed_at, method in cursor:
        public_id = "CORPUS:" + str(aid)
        if public_id in known_ids:
            skipped["duplicate"] += 1
            continue
        if method != "llm-semantic-v1":
            skipped["audit_method"] += 1
            continue
        meta = lookup.get(cid)
        assertion = json.loads(payload)
        if (not meta or validation != "passed" or evidence != 1
                or assertion.get("source_chunk_id") != cid
                or assertion.get("source_doc_id") != meta.get("doc_id")
                or not same_text(assertion.get("source_text_quote"), meta.get("text"))):
            skipped["source"] += 1
            continue
        assertion["assertion_id"] = public_id
        try:
            validate_assertion(assertion, schema)
        except ValueError:
            skipped["schema"] += 1
            continue
        triple = (cid, assertion.get("subject_id"), assertion.get("predicate"),
                  assertion.get("object_id"))
        if triple in known_triples:
            skipped["duplicate"] += 1
            continue
        known_triples.add(triple)
        accepted.append({
            "review_id": "REV_CORPUS:" + str(aid),
            "assertion_id": public_id,
            "decision": "approved",
            "original_assertion": assertion,
            "reviewed_at": reviewed_at or datetime.now(timezone.utc).isoformat(),
            "reviewed_by": "alpha-semantic-audit",
            "review_comment": "Source, schema and semantic audit: " + str(reason or "")[:300],
        })
    return accepted, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=CORPUS)
    parser.add_argument("--metadata", type=Path, default=VECTOR_METADATA)
    parser.add_argument("--reviews", type=Path, default=REVIEWS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    lookup = {row["chunk_id"]: row for row in json.loads(
        args.metadata.read_text(encoding="utf-8"))}
    existing = read_jsonl(args.reviews)
    combined = existing + read_jsonl(LEGACY_REVIEWS)
    with sqlite3.connect(f"file:{args.db.resolve().as_posix()}?mode=ro",
                         uri=True, timeout=10) as db:
        accepted, skipped = eligible(db, lookup, combined, SchemaManager())
    backup = None
    if accepted and not args.dry_run:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = BACKUPS / f"reviewed_before_corpus_{stamp}.jsonl"
        if args.reviews.exists():
            shutil.copy2(args.reviews, backup)
        else:
            backup.write_text("", encoding="utf-8")
        data = "".join(json.dumps(record, ensure_ascii=False) + "\n"
                       for record in accepted).encode("utf-8")
        fd = os.open(args.reviews, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            if os.write(fd, data) != len(data):
                raise OSError("Incomplete review event append")
            os.fsync(fd)
        finally:
            os.close(fd)
    print(json.dumps({"ready": len(accepted), "published": 0 if args.dry_run else len(accepted),
                      "skipped": skipped, "backup": str(backup) if backup else None},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
