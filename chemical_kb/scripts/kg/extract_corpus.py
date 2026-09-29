#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resumeable, source-grounded extraction of every indexed chunk.

Examples:
  python scripts/kg/extract_corpus.py --dry-run
  python scripts/kg/extract_corpus.py --limit 10
  python scripts/kg/extract_corpus.py                 # process all remaining chunks

Candidates stay in a staging database until separately audited and imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
METADATA = ROOT / "data/vector_store/index_metadata.json"
DEFAULT_DB = ROOT / "data/kg/batch_extraction/corpus.sqlite"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, doc_type TEXT,
            status TEXT NOT NULL DEFAULT 'queued', attempt INTEGER NOT NULL DEFAULT 0,
            assertion_count INTEGER NOT NULL DEFAULT 0, passed_count INTEGER NOT NULL DEFAULT 0,
            evidence_count INTEGER NOT NULL DEFAULT 0, unresolved_count INTEGER NOT NULL DEFAULT 0,
            elapsed_seconds REAL, error TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS chunks_status ON chunks(status);
        CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id);
        CREATE TABLE IF NOT EXISTS assertions (
            assertion_id TEXT PRIMARY KEY, chunk_id TEXT NOT NULL,
            validation_status TEXT NOT NULL, evidence_ok INTEGER NOT NULL,
            payload TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES chunks(chunk_id)
        );
        CREATE INDEX IF NOT EXISTS assertions_chunk ON assertions(chunk_id);
    """)
    return db


def round_robin(rows):
    """Visit one chunk from every document before revisiting a document."""
    groups = defaultdict(list)
    for row in rows:
        groups[str(row.get("doc_id") or "")].append(row)
    for group in groups.values():
        group.sort(key=lambda r: str(r.get("chunk_id") or ""))
    doc_order = sorted(groups, key=lambda doc_id: hashlib.sha1(doc_id.encode("utf-8")).hexdigest())
    for index in range(max(map(len, groups.values()), default=0)):
        for doc_id in doc_order:
            if index < len(groups[doc_id]):
                yield groups[doc_id][index]


def prepare(db, rows):
    values = [(str(r.get("chunk_id") or ""), str(r.get("doc_id") or ""),
               str(r.get("doc_type") or r.get("document_type") or ""))
              for r in rows if r.get("chunk_id") and r.get("doc_id")]
    db.executemany("INSERT OR IGNORE INTO chunks(chunk_id,doc_id,doc_type) VALUES(?,?,?)", values)
    db.commit()
    return len(values)


def status_summary(db):
    counts = dict(db.execute("SELECT status,COUNT(*) FROM chunks GROUP BY status").fetchall())
    docs = db.execute("SELECT COUNT(DISTINCT doc_id) FROM chunks WHERE status IN ('done','empty')").fetchone()[0]
    candidates = db.execute("SELECT COUNT(*),SUM(evidence_ok) FROM assertions").fetchone()
    return {"chunks": counts, "processed_docs": docs, "candidates": candidates[0] or 0,
            "evidence_matched": candidates[1] or 0}


def evidence_in_text(quote, text):
    """Ignore OCR line wraps and spaces while preserving character order."""
    return bool(quote) and re.sub(r"\s+", "", str(quote)) in re.sub(r"\s+", "", str(text))


def save_result(db, chunk, result, elapsed):
    chunk_id = chunk["chunk_id"]
    text = str(chunk.get("text") or "")
    assertions = result.get("assertions") or []
    passed = sum(a.get("validation_status") == "passed" for a in assertions)
    evidence = sum(evidence_in_text(a.get("source_text_quote"), text) for a in assertions)
    status = "empty" if not assertions else "done"
    with db:
        db.execute("DELETE FROM assertions WHERE chunk_id=?", (chunk_id,))
        for a in assertions:
            aid = str(a.get("assertion_id") or "")
            if not aid:
                continue
            evidence_ok = int(evidence_in_text(a.get("source_text_quote"), text))
            db.execute("INSERT OR REPLACE INTO assertions VALUES(?,?,?,?,?)",
                       (aid, chunk_id, str(a.get("validation_status") or "unknown"),
                        evidence_ok, json.dumps(a, ensure_ascii=False, default=str)))
        db.execute("""UPDATE chunks SET status=?, attempt=attempt+1, assertion_count=?,
            passed_count=?, evidence_count=?, unresolved_count=?, elapsed_seconds=?,
            error=NULL, updated_at=? WHERE chunk_id=?""",
            (status, len(assertions), passed, evidence,
             len(result.get("unresolved_relations") or []), elapsed, now(), chunk_id))
    return status, len(assertions), passed, evidence


def save_failure(db, chunk_id, status, error, elapsed):
    with db:
        db.execute("""UPDATE chunks SET status=?,attempt=attempt+1,error=?,
            elapsed_seconds=?,updated_at=? WHERE chunk_id=?""",
            (status, str(error)[:2000], elapsed, now(), chunk_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--metadata", type=Path, default=METADATA)
    parser.add_argument("--limit", type=int, default=0, help="Maximum chunks this run; 0 means all")
    parser.add_argument("--batch-size", type=int, default=1, help="GPU inference batch size")
    parser.add_argument("--max-seconds", type=int, default=0, help="Stop cleanly after this time; 0 means no limit")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recheck-evidence", action="store_true", help="Recalculate evidence matches for stored candidates")
    args = parser.parse_args()
    rows = json.loads(args.metadata.read_text(encoding="utf-8"))
    db = connect(args.db)
    total = prepare(db, rows)
    print("inventory", total, "chunks", len({r.get('doc_id') for r in rows}), "documents", flush=True)
    print("before", json.dumps(status_summary(db), ensure_ascii=False), flush=True)
    if args.recheck_evidence:
        texts = {str(r.get("chunk_id")): str(r.get("text") or "") for r in rows}
        for assertion_id, chunk_id, payload in db.execute("SELECT assertion_id,chunk_id,payload FROM assertions").fetchall():
            quote = json.loads(payload).get("source_text_quote")
            db.execute("UPDATE assertions SET evidence_ok=? WHERE assertion_id=?",
                       (int(evidence_in_text(quote, texts.get(chunk_id, ""))), assertion_id))
        db.execute("""UPDATE chunks SET evidence_count=(SELECT COUNT(*) FROM assertions
            WHERE assertions.chunk_id=chunks.chunk_id AND evidence_ok=1)""")
        db.commit()
        print("rechecked", json.dumps(status_summary(db), ensure_ascii=False), flush=True)
        return
    if args.dry_run:
        return
    from core.kg.pipeline import KGExtractionPipeline
    pipeline = KGExtractionPipeline(retriever=None)
    eligible = {"queued"}
    if args.retry_failed:
        eligible.update(("error", "extraction_failed"))
    states = dict(db.execute("SELECT chunk_id,status FROM chunks"))
    selected = [chunk for chunk in round_robin(rows)
                if states.get(str(chunk.get("chunk_id") or "")) in eligible]
    if args.limit:
        selected = selected[:args.limit]
    started = time.monotonic()
    processed = 0
    size = max(1, args.batch_size)
    for offset in range(0, len(selected), size):
        if args.max_seconds and time.monotonic() - started >= args.max_seconds:
            break
        group = selected[offset:offset + size]
        nonempty = [chunk for chunk in group if str(chunk.get("text") or "").strip()]
        batch_t0 = time.monotonic()
        outputs = {}
        if nonempty:
            try:
                results = pipeline.process_batch(nonempty)
                outputs = {chunk["chunk_id"]: result for chunk, result in zip(nonempty, results)}
            except Exception as exc:
                print(f"batch failed ({type(exc).__name__}: {exc}); retrying separately", flush=True)
                if "out of memory" in str(exc).lower():
                    import torch
                    torch.cuda.empty_cache()
                for chunk in nonempty:
                    try:
                        outputs[chunk["chunk_id"]] = pipeline.process_chunk(chunk)
                    except Exception as item_exc:
                        outputs[chunk["chunk_id"]] = item_exc
        elapsed_each = (time.monotonic() - batch_t0) / max(len(nonempty), 1)
        for chunk in group:
            chunk_id = chunk["chunk_id"]
            if not str(chunk.get("text") or "").strip():
                kind, count, passed, evidence = save_result(db, chunk, {"assertions": []}, 0)
            else:
                result = outputs.get(chunk_id)
                if isinstance(result, Exception) or result is None:
                    save_failure(db, chunk_id, "error", repr(result), elapsed_each)
                    kind, count, passed, evidence = "error", 0, 0, 0
                elif result.get("status") == "extraction_failed":
                    save_failure(db, chunk_id, "extraction_failed", "LLM extraction failed", elapsed_each)
                    kind, count, passed, evidence = "extraction_failed", 0, 0, 0
                else:
                    kind, count, passed, evidence = save_result(db, chunk, result, elapsed_each)
            processed += 1
            states[chunk_id] = kind
            if processed <= 5 or processed % 20 == 0:
                print(f"{processed} {chunk_id} {kind} assertions={count} passed={passed} "
                      f"evidence={evidence} seconds~={elapsed_each:.1f}", flush=True)
    print("after", json.dumps(status_summary(db), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
