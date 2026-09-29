#!/usr/bin/env python3
"""Recover candidate source passages for legacy triples; never auto-approve them."""
from __future__ import annotations

import argparse
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
    db.commit()


def excerpt(text: str, source: str, target: str) -> str:
    first, second = text.find(source), text.find(target)
    if first < 0 or second < 0 or abs(first - second) > 500:
        return ""
    left = max(0, min(first, second) - 120)
    right = min(len(text), max(first + len(source), second + len(target)) + 120)
    return text[left:right]


def recover(db: sqlite3.Connection) -> dict:
    prepare(db)
    total = 0
    with_evidence = 0
    direct = 0
    for rid, source, target, old_chunk in db.execute(
        "SELECT id,source_entity,target_entity,source_chunk_id "
        "FROM graph_relationships ORDER BY id"
    ):
        total += 1
        rows = []
        source = (source or "").strip()
        target = (target or "").strip()
        if old_chunk:
            rows = db.execute(
                "SELECT id,text FROM chunks WHERE id=?", (old_chunk,)
            ).fetchall()
        if not rows and len(source) >= 3 and len(target) >= 3:
            rows = db.execute(
                "SELECT chunk_id,text FROM legacy_chunk_fts "
                "WHERE text LIKE ? AND text LIKE ? LIMIT 12",
                ("%" + source + "%", "%" + target + "%")
            ).fetchall()
        evidence = []
        for cid, text in rows:
            quote = excerpt(text or "", source, target)
            if quote:
                evidence.append((rid, cid, quote,
                                 "direct_source_id" if cid == old_chunk else "cooccurrence"))
            if len(evidence) >= 5:
                break
        if evidence:
            with_evidence += 1
            direct += any(row[3] == "direct_source_id" for row in evidence)
            db.executemany(
                "INSERT OR IGNORE INTO legacy_relation_evidence VALUES (?,?,?,?)",
                evidence
            )
        decision = "needs_semantic_review" if evidence else "needs_source"
        reason = ("Entity names co-occur; relation semantics and schema are unverified"
                  if evidence else "No matching source passage recovered")
        db.execute(
            "UPDATE legacy_relation_audits SET decision=?,reason=? "
            "WHERE relation_id=? AND decision='unreviewed'",
            (decision, reason, rid)
        )
        if total % 250 == 0:
            db.commit()
    db.commit()
    return {"total": total, "candidate_evidence": with_evidence,
            "direct_source_matches": direct,
            "needs_source": total - with_evidence,
            "approved": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    with sqlite3.connect(args.db, timeout=60) as db:
        db.execute("PRAGMA journal_mode=WAL")
        print(json.dumps(recover(db), ensure_ascii=False))


if __name__ == "__main__":
    main()
