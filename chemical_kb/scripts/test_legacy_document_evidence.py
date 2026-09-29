#!/usr/bin/env python3
"""Synthetic test: old document body is evidence even when chunks are stale."""
import sqlite3

from scripts.legacy_relation_audit import recover

db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE chunks(id TEXT,text TEXT)")
db.execute("CREATE TABLE document_versions(id TEXT,document_id TEXT,content TEXT,status TEXT)")
db.execute("CREATE TABLE graph_relationships(id TEXT,source_entity TEXT,target_entity TEXT,source_chunk_id TEXT)")
db.execute("CREATE TABLE legacy_relation_audits(relation_id TEXT,decision TEXT,reason TEXT)")
db.execute("INSERT INTO chunks VALUES (?,?)", ("stale", "unrelated chunk text"))
db.execute("INSERT INTO document_versions VALUES (?,?,?,?)",
           ("v1", "d1", "AlphaChem is handled by BetaTeam under this procedure.", "indexed"))
db.execute("INSERT INTO graph_relationships VALUES (?,?,?,?)",
           ("r1", "AlphaChem", "BetaTeam", "missing"))
db.execute("INSERT INTO legacy_relation_audits VALUES (?,?,?)",
           ("r1", "needs_source", ""))
stats = recover(db)
assert stats["document_body_matches"] == 1
assert stats["chunk_body_matches"] == 0
assert db.execute(
    "SELECT decision FROM legacy_relation_audits WHERE relation_id='r1'"
).fetchone()[0] == "needs_semantic_review"
assert db.execute(
    "SELECT chunk_id,match_kind FROM legacy_relation_evidence"
).fetchone() == ("DOCVER:v1", "document_body")
print({"document_body_evidence": True, "stale_chunk_independent": True})
