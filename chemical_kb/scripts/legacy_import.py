#!/usr/bin/env python3
"""Create a private, repeatable legacy-data import without copying app secrets.

The source is opened read-only. Outputs must stay under data/legacy (git ignored).
Relations remain unreviewed until evidence, schema and semantic review pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from core.config import BASE_DIR

TABLES = ("documents", "document_versions", "chunks", "graph_entities", "graph_relationships")
LEGACY = BASE_DIR / "data" / "legacy"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_selected(source: Path, destination: Path) -> None:
    src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    tmp = destination.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    dst = sqlite3.connect(tmp)
    try:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Source SQLite integrity check failed")
        for table in TABLES:
            definition = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not definition:
                raise RuntimeError(f"Missing source table: {table}")
            dst.execute(definition[0])
            columns = len(src.execute(f"PRAGMA table_info({table})").fetchall())
            marks = ",".join("?" for _ in range(columns))
            cursor = src.execute(f"SELECT * FROM {table}")
            while rows := cursor.fetchmany(250):
                dst.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
            dst.commit()
        dst.executescript("""
            CREATE TABLE legacy_relation_audits (
                relation_id TEXT PRIMARY KEY, decision TEXT NOT NULL DEFAULT 'unreviewed',
                evidence_chunk_id TEXT NOT NULL DEFAULT '', evidence_quote TEXT NOT NULL DEFAULT '',
                normalized_predicate TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
                reviewed_at TEXT NOT NULL DEFAULT '', reviewed_by TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO legacy_relation_audits(relation_id)
                SELECT id FROM graph_relationships;
            CREATE INDEX legacy_relations_source ON graph_relationships(source_chunk_id);
            CREATE INDEX legacy_chunks_version ON chunks(document_version_id);
        """)
        dst.commit()
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Imported SQLite integrity check failed")
    finally:
        dst.close()
        src.close()
    os.replace(tmp, destination)


def build_metadata(database: Path, destination: Path) -> int:
    db = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    try:
        rows = db.execute("""
            SELECT c.id, d.id, d.title, d.source_type, c.ordinal, c.text,
                   c.section_title, c.content_hash
            FROM chunks c JOIN document_versions v ON v.id=c.document_version_id
            JOIN documents d ON d.id=v.document_id ORDER BY d.id,c.ordinal,c.id
        """)
        metadata = [
            {
                "chunk_id": "LEGACY:" + cid, "doc_id": "LEGACY:" + did,
                "title": title, "document_type": source_type,
                "code": "", "source": "legacy_hazmat_ai_service",
                "page_start": None, "page_end": None, "text": body,
                "section_title": section or "", "ordinal": ordinal,
                "char_count": len(body or ""), "content_hash": content_hash,
                "quality": "legacy_import", "status": "indexed",
            }
            for cid, did, title, source_type, ordinal, body, section, content_hash in rows
        ]
    finally:
        db.close()
    tmp = destination.with_suffix(".building")
    tmp.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, destination)
    return len(metadata)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=LEGACY)
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        parser.error("Source database does not exist")
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    database = out / "hazmat_legacy.sqlite"
    metadata = out / "chunks_metadata.json"
    copy_selected(source, database)
    count = build_metadata(database, metadata)
    with sqlite3.connect(database) as db:
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in TABLES}
        audit = db.execute("SELECT COUNT(*) FROM legacy_relation_audits").fetchone()[0]
    manifest = {
        "source_sha256": checksum(source), "sanitized_sha256": checksum(database),
        "tables": counts, "metadata_chunks": count,
        "relations_unreviewed": audit,
        "legacy_embedding_model": "text-embedding-v4",
        "legacy_embedding_dimensions": 1024,
        "vector_status": "requires_reembedding_with_current_model",
        "relations_status": "private_unreviewed_only",
        "excluded_tables": ["app_config", "index_jobs", "knowledge_bases"],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
