#!/usr/bin/env python3
"""Consistent server-side backups of private imported corpus and checkpoints."""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
from pathlib import Path

from core.config import BASE_DIR

SOURCE = BASE_DIR / "data/legacy"
DESTINATION = Path("/autodl-fs/data/alpha-legacy-import")
DATABASES = ("hazmat_legacy.sqlite", "corpus.sqlite", "body_corpus.sqlite",
             "reembed.sqlite", "keyword.sqlite")
FILES = ("README.md", "manifest.json", "chunks_metadata.json",
         "body_chunks_metadata.json", "reviewed.jsonl", "faiss.index")


def backup_sqlite(source: Path, destination: Path) -> None:
    snapshot = destination.with_suffix(".snapshot")
    compressed = destination.with_suffix(destination.suffix + ".building")
    snapshot.unlink(missing_ok=True)
    compressed.unlink(missing_ok=True)
    with sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro",
                         uri=True, timeout=60) as original:
        with sqlite3.connect(snapshot) as copy:
            original.backup(copy, pages=500)
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError(f"Backup integrity check failed: {source.name}")
    try:
        with snapshot.open("rb") as inp, gzip.open(compressed, "wb", compresslevel=4) as out:
            shutil.copyfileobj(inp, out, length=4 * 1024 * 1024)
        os.replace(compressed, destination)
    finally:
        snapshot.unlink(missing_ok=True)
        compressed.unlink(missing_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".building")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DESTINATION)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in DATABASES:
        source = args.source_dir / name
        if source.exists():
            backup_sqlite(source, args.out_dir / (name + ".gz"))
            copied.append(name + ".gz")
    for name in FILES:
        source = args.source_dir / name
        if source.exists():
            copy_file(source, args.out_dir / name)
            copied.append(name)
    print(json.dumps({"backup_files": copied, "count": len(copied)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
