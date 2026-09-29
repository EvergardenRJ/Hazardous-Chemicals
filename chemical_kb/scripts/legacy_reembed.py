#!/usr/bin/env python3
"""Resumeable BGE-M3 embedding of private legacy chunks into a separate FAISS index."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

import numpy as np

from core.config import BASE_DIR, EMBED_MODEL

ROOT = BASE_DIR / "data/legacy"
META = ROOT / "chunks_metadata.json"
CHECKPOINT = ROOT / "reembed.sqlite"
INDEX = ROOT / "faiss.index"


def checkpoint(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id TEXT PRIMARY KEY, content_hash TEXT NOT NULL,
            dimensions INTEGER NOT NULL, vector BLOB NOT NULL
        )
    """)
    db.commit()
    return db


def build_index(db: sqlite3.Connection, rows: list[dict]) -> int:
    import faiss

    index = faiss.IndexFlatIP(1024)
    batch = []
    for row in rows:
        record = db.execute(
            "SELECT content_hash,dimensions,vector FROM embeddings WHERE chunk_id=?",
            (row["chunk_id"],)
        ).fetchone()
        if record is None or record[0] != row["content_hash"] or record[1] != 1024:
            raise RuntimeError("Embedding checkpoint is incomplete or stale")
        batch.append(np.frombuffer(record[2], dtype="float32"))
        if len(batch) >= 512:
            index.add(np.stack(batch))
            batch.clear()
    if batch:
        index.add(np.stack(batch))
    if index.ntotal != len(rows):
        raise RuntimeError("FAISS count does not match metadata")
    temporary = INDEX.with_suffix(".building")
    faiss.write_index(index, str(temporary))
    os.replace(temporary, INDEX)
    return index.ntotal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows = json.loads(META.read_text(encoding="utf-8"))
    db = checkpoint(CHECKPOINT)
    done = {cid: digest for cid, digest in db.execute(
        "SELECT chunk_id,content_hash FROM embeddings"
    )}
    remaining = [row for row in rows if done.get(row["chunk_id"]) != row["content_hash"]]
    print(json.dumps({"total": len(rows), "checkpointed": len(rows)-len(remaining),
                      "remaining": len(remaining)}, ensure_ascii=False), flush=True)
    if args.dry_run:
        return
    selected = remaining[:args.limit] if args.limit else remaining
    if selected:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBED_MODEL, device="cuda")
        size = max(1, args.batch_size)
        for offset in range(0, len(selected), size):
            group = selected[offset:offset+size]
            vectors = model.encode(
                [row["text"] for row in group], batch_size=size,
                normalize_embeddings=True, show_progress_bar=False
            )
            vectors = np.asarray(vectors, dtype="float32")
            if vectors.shape != (len(group), 1024):
                raise RuntimeError(f"Unexpected embedding shape: {vectors.shape}")
            with db:
                db.executemany(
                    "INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?)",
                    [(row["chunk_id"], row["content_hash"], 1024,
                      vector.tobytes()) for row, vector in zip(group, vectors)]
                )
            if offset == 0 or (offset + len(group)) % 256 == 0:
                print("encoded", offset + len(group), "/", len(selected), flush=True)
    complete = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    if complete >= len(rows):
        print(json.dumps({"faiss_vectors": build_index(db, rows)}), flush=True)
    else:
        print(json.dumps({"checkpointed": complete, "remaining": len(rows)-complete}), flush=True)


if __name__ == "__main__":
    main()
