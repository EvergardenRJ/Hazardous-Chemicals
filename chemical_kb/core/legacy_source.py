# -*- coding: utf-8 -*-
"""Read a source document version retained privately in the legacy SQLite DB."""
from __future__ import annotations

import json
import sqlite3
from functools import lru_cache

from core.config import BASE_DIR

DATABASE = BASE_DIR / "data/legacy/hazmat_legacy.sqlite"
PREFIX = "LEGACY:DOCVER:"
BODY_METADATA = BASE_DIR / "data/legacy/body_chunks_metadata.json"


@lru_cache(maxsize=256)
def document_body_metadata(chunk_id: str):
    if not str(chunk_id).startswith(PREFIX) or not DATABASE.exists():
        return None
    version_id = str(chunk_id)[len(PREFIX):]
    if not version_id:
        return None
    with sqlite3.connect(f"file:{DATABASE.resolve().as_posix()}?mode=ro",
                         uri=True, timeout=5) as db:
        row = db.execute("""
            SELECT v.document_id,d.title,d.source_type,v.content
            FROM document_versions v JOIN documents d ON d.id=v.document_id
            WHERE v.id=?
        """, (version_id,)).fetchone()
    if not row:
        return None
    doc_id, title, source_type, body = row
    return {
        "chunk_id": chunk_id, "doc_id": "LEGACY:" + doc_id,
        "title": title, "document_type": source_type,
        "source": "legacy_document_body", "text": body,
        "page_start": None, "page_end": None,
        "char_count": len(body or ""), "quality": "legacy_full_text",
    }



@lru_cache(maxsize=2)
def _body_chunks(mtime: int):
    rows = json.loads(BODY_METADATA.read_text(encoding="utf-8"))
    return {row["chunk_id"]: row for row in rows}


def body_chunk_metadata(chunk_id: str):
    if not str(chunk_id).startswith("LEGACY_BODY:") or not BODY_METADATA.exists():
        return None
    return _body_chunks(BODY_METADATA.stat().st_mtime_ns).get(str(chunk_id))
