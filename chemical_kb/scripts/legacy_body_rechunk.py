#!/usr/bin/env python3
"""Create complete, overlapping extraction chunks from stored old document bodies.

The old database contains extracted text, not original DOC/DOCX/PDF binaries.
Outputs remain private under data/legacy and never enter the public keyword DB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from core.config import BASE_DIR

DATABASE = BASE_DIR / "data/legacy/hazmat_legacy.sqlite"
OUTPUT = BASE_DIR / "data/legacy/body_chunks_metadata.json"


def windows(text: str, width: int, overlap: int):
    if width <= overlap or overlap < 0:
        raise ValueError("width must be greater than overlap")
    step = width - overlap
    for ordinal, start in enumerate(range(0, len(text), step)):
        end = min(len(text), start + width)
        yield ordinal, start, end, text[start:end]
        if end == len(text):
            break


def build(database: Path, width: int, overlap: int):
    rows = []
    docs = 0
    characters = 0
    with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as db:
        cursor = db.execute("""
            SELECT v.id,v.document_id,v.content,d.title,d.source_type
            FROM document_versions v JOIN documents d ON d.id=v.document_id
            WHERE v.status='indexed' ORDER BY v.document_id,v.version_number
        """)
        for version_id, doc_id, body, title, source_type in cursor:
            body = str(body or "")
            if not body.strip():
                continue
            docs += 1
            characters += len(body)
            for ordinal, start, end, text in windows(body, width, overlap):
                rows.append({
                    "chunk_id": f"LEGACY_BODY:{version_id}:{ordinal}",
                    "doc_id": "LEGACY:" + doc_id, "title": title,
                    "document_type": source_type,
                    "source": "legacy_document_body",
                    "text": text, "char_count": len(text),
                    "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "ordinal": ordinal,
                    "body_start": start, "body_end": end,
                    "page_start": None, "page_end": None,
                    "quality": "extracted_body_text", "status": "queued",
                })
    return rows, {"documents": docs, "source_characters": characters,
                  "extraction_chunks": len(rows), "width": width, "overlap": overlap}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DATABASE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--width", type=int, default=1800)
    parser.add_argument("--overlap", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, summary = build(args.db, args.width, args.overlap)
    if not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".building")
        temporary.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, args.output)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
