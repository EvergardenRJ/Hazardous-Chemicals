#!/usr/bin/env python3
"""Read-only smoke check for private legacy import and API visibility."""
import json
import sqlite3

from app.explorer_api import ROOT, app

legacy = ROOT / "data/legacy/hazmat_legacy.sqlite"
with sqlite3.connect(f"file:{legacy}?mode=ro", uri=True) as db:
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 152
    assert db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 7927
    assert db.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()[0] == 3613
    assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='app_config'").fetchone()[0] == 0
    audit = dict(db.execute("SELECT decision,COUNT(*) FROM legacy_relation_audits GROUP BY decision"))
    title = db.execute("SELECT title FROM documents ORDER BY id LIMIT 1").fetchone()[0]
with app.test_client() as client:
    summary = client.get("/api/summary").get_json()
    docs = client.get("/api/documents", query_string={"q": title, "size": 100}).get_json()
    search = client.get("/api/search", query_string={"q": title[:8]}).get_json()
    graph = client.get("/api/graph", query_string={"mode": "approved"}).get_json()
assert any(row["doc_id"].startswith("LEGACY:") for row in docs["items"])
legacy_approved_edges = sum(str(row["id"]).startswith("LEGACYREL:")
                            for row in graph["edges"])
if audit.get("approved", 0) == 0:
    assert legacy_approved_edges == 0
assert (ROOT / "data/search/keyword.sqlite").exists()
assert (ROOT / "data/legacy/keyword.sqlite").exists()
with sqlite3.connect(ROOT / "data/search/keyword.sqlite") as public_index:
    assert public_index.execute(
        "SELECT COUNT(*) FROM docs WHERE chunk_id LIKE 'LEGACY:%'"
    ).fetchone()[0] == 0
with sqlite3.connect(ROOT / "data/legacy/keyword.sqlite") as private_index:
    assert private_index.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 7927
print(json.dumps({
    "summary_documents": summary["documents"],
    "summary_chunks": summary["chunks"],
    "legacy_document_visible": True,
    "keyword_legacy_hit": any(item["metadata"]["doc_id"].startswith("LEGACY:")
                              for item in search["evidence"]),
    "legacy_relation_audits": audit,
    "legacy_approved_edges": legacy_approved_edges,
}, ensure_ascii=False))
