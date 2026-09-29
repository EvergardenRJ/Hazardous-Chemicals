#!/usr/bin/env python3
"""Recover old-triple evidence from legacy chunks and document body text.

The old database holds extracted body text, not original DOC/PDF binaries.
This pass never approves relations and prints aggregate counts only.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sqlite3
from pathlib import Path

from core.config import BASE_DIR

DEFAULT_DB = BASE_DIR / "data/legacy/hazmat_legacy.sqlite"


def prepare(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS legacy_relation_evidence (
            relation_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
            excerpt TEXT NOT NULL, match_kind TEXT NOT NULL,
            PRIMARY KEY(relation_id, chunk_id)
        )
    """)
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS legacy_chunk_fts USING
        fts5(chunk_id UNINDEXED, text, tokenize='trigram')
    """)
    if db.execute("SELECT COUNT(*) FROM legacy_chunk_fts").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO legacy_chunk_fts(chunk_id,text) VALUES (?,?)",
            db.execute("SELECT id,text FROM chunks")
        )
    db.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS legacy_document_fts USING
        fts5(version_id UNINDEXED, document_id UNINDEXED, text, tokenize='trigram')
    """)
    if db.execute("SELECT COUNT(*) FROM legacy_document_fts").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO legacy_document_fts(version_id,document_id,text) VALUES (?,?,?)",
            db.execute("""
                SELECT v.id,v.document_id,v.content FROM document_versions v
                WHERE v.status='indexed'
            """)
        )
    db.commit()


def positions(text: str, needle: str) -> list[int]:
    result = []
    start = 0
    while True:
        found = text.find(needle, start)
        if found < 0:
            return result
        result.append(found)
        start = found + max(1, len(needle))


def excerpt(text: str, source: str, target: str, max_gap: int = 500) -> str:
    if not source or not target:
        return ""
    sources = positions(text, source)
    targets = positions(text, target)
    if not sources or not targets:
        return ""
    best = None
    for first in sources:
        index = bisect.bisect_left(targets, first)
        for second in targets[max(0, index-1):index+1]:
            if source == target and first == second:
                continue
            gap = abs(first-second)
            if best is None or gap < best[0]:
                best = (gap, first, second)
    if best is None or best[0] > max_gap:
        return ""
    _, first, second = best
    left = max(0, min(first, second)-120)
    right = min(len(text), max(first+len(source), second+len(target))+120)
    return text[left:right]


def matches(db, table: str, column: str, source: str, target: str, limit: int = 30):
    if len(source) < 3 or len(target) < 3:
        return []
    return db.execute(
        f"SELECT {column},text FROM {table} WHERE text LIKE ? AND text LIKE ? LIMIT ?",
        ("%" + source + "%", "%" + target + "%", limit)
    ).fetchall()


def recover(db: sqlite3.Connection) -> dict:
    prepare(db)
    relations = db.execute(
        "SELECT id,source_entity,target_entity,source_chunk_id "
        "FROM graph_relationships ORDER BY id"
    ).fetchall()
    chunk_count = document_count = direct_count = 0
    for index, (rid, source, target, old_chunk) in enumerate(relations, 1):
        source = (source or "").strip()
        target = (target or "").strip()
        chunk_rows = []
        if old_chunk:
            chunk_rows = db.execute(
                "SELECT id,text FROM chunks WHERE id=?", (old_chunk,)
            ).fetchall()
        if not chunk_rows:
            chunk_rows = matches(db, "legacy_chunk_fts", "chunk_id", source, target)
        recovered = []
        for cid, text in chunk_rows:
            quote = excerpt(text or "", source, target)
            if quote:
                recovered.append((rid, cid, quote,
                                  "direct_source_id" if cid == old_chunk else "chunk_body"))
            if len(recovered) >= 5:
                break
        if recovered:
            chunk_count += 1
            direct_count += any(item[3] == "direct_source_id" for item in recovered)
        document_rows = matches(
            db, "legacy_document_fts", "version_id", source, target
        )
        doc_recovered = []
        for version_id, text in document_rows:
            quote = excerpt(text or "", source, target)
            if quote:
                doc_recovered.append((rid, "DOCVER:" + version_id,
                                      quote, "document_body"))
            if len(doc_recovered) >= 5:
                break
        if doc_recovered:
            document_count += 1
        if recovered or doc_recovered:
            db.executemany(
                "INSERT OR IGNORE INTO legacy_relation_evidence VALUES (?,?,?,?)",
                recovered + doc_recovered
            )
        count = db.execute(
            "SELECT COUNT(*) FROM legacy_relation_evidence WHERE relation_id=?", (rid,)
        ).fetchone()[0]
        status = "needs_semantic_review" if count else "needs_source"
        reason = ("Old document/chunk text contains endpoint names; semantics unverified"
                  if count else "No exact nearby endpoint names in old document bodies or chunks")
        db.execute(
            "UPDATE legacy_relation_audits SET decision=?,reason=? "
            "WHERE relation_id=? AND decision IN ('unreviewed','needs_source','needs_semantic_review')",
            (status, reason, rid)
        )
        if index % 250 == 0:
            db.commit()
    db.commit()
    found = db.execute(
        "SELECT COUNT(DISTINCT relation_id) FROM legacy_relation_evidence"
    ).fetchone()[0]
    return {"total": len(relations), "candidate_evidence": found,
            "chunk_body_matches": chunk_count, "document_body_matches": document_count,
            "direct_source_matches": direct_count,
            "needs_source": len(relations)-found, "approved_by_recovery": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    with sqlite3.connect(args.db, timeout=60) as db:
        db.execute("PRAGMA journal_mode=WAL")
        print(json.dumps(recover(db), ensure_ascii=False))


if __name__ == "__main__":
    main()
