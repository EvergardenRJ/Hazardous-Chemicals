#!/usr/bin/env python3
"""Print aggregate main and private legacy extraction progress without source text."""
import json
import sqlite3
from pathlib import Path

from core.config import BASE_DIR


def corpus(path):
    if not path.exists():
        return {"present": False}
    with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=5) as db:
        statuses = dict(db.execute("SELECT status,COUNT(*) FROM chunks GROUP BY status"))
        assertions = db.execute("SELECT COUNT(*),COALESCE(SUM(evidence_ok),0) FROM assertions").fetchone()
        reviewed = {}
        if db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='candidate_audits'").fetchone()[0]:
            reviewed = dict(db.execute(
                "SELECT decision,COUNT(*) FROM candidate_audits GROUP BY decision"
            ))
        return {"chunks": statuses, "candidates": assertions[0],
                "grounded_candidates": assertions[1], "candidate_audits": reviewed}


def main():
    legacy = BASE_DIR / "data/legacy"
    result = {
        "main": corpus(BASE_DIR / "data/kg/batch_extraction/corpus.sqlite"),
        "legacy_corpus": corpus(legacy / "corpus.sqlite"),
        "legacy_body_corpus": corpus(legacy / "body_corpus.sqlite"),
    }
    old_db = legacy / "hazmat_legacy.sqlite"
    if old_db.exists():
        with sqlite3.connect(f"file:{old_db.resolve().as_posix()}?mode=ro", uri=True) as db:
            result["old_relations"] = dict(db.execute(
                "SELECT decision,COUNT(*) FROM legacy_relation_audits GROUP BY decision"
            ))
    checkpoint = legacy / "reembed.sqlite"
    if checkpoint.exists():
        with sqlite3.connect(f"file:{checkpoint.resolve().as_posix()}?mode=ro", uri=True) as db:
            result["reembedded_vectors"] = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    else:
        result["reembedded_vectors"] = 0
    result["legacy_faiss_ready"] = (legacy / "faiss.index").exists()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
