#!/usr/bin/env python3
"""Take a consistent online SQLite checkpoint of a corpus queue."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    source = args.db.resolve()
    if not source.is_file():
        raise SystemExit(f"Corpus database does not exist: {source}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = args.out_dir / f"corpus_checkpoint_{stamp}.sqlite"
    building = target.with_suffix(".sqlite.building")
    try:
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=60) as original:
            with sqlite3.connect(building) as copy:
                original.backup(copy, pages=500)
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Checkpoint integrity check failed")
                states = dict(copy.execute("SELECT status,COUNT(*) FROM chunks GROUP BY status"))
                assertions = copy.execute("SELECT COUNT(*) FROM assertions").fetchone()[0]
        os.replace(building, target)
    finally:
        building.unlink(missing_ok=True)
    print(json.dumps({
        "checkpoint": str(target), "bytes": target.stat().st_size,
        "chunks": states, "candidates": assertions,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
