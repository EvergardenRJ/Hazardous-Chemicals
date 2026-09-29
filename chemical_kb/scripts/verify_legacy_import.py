#!/usr/bin/env python3
"""Read-only smoke check for private legacy import and API visibility."""
import hashlib
import json
import sqlite3

from app.explorer_api import ROOT, app
from core.legacy_source import document_body_metadata, body_chunk_metadata

legacy = ROOT / "data/legacy/hazmat_legacy.sqlite"
with sqlite3.connect(f"file:{legacy}?mode=ro", uri=True) as db:
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 152
    assert db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 7927
    assert db.execute("SELECT COUNT(*) FROM graph_relationships").fetchone()[0] == 3613
    assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='app_config'").fetchone()[0] == 0
    audit = dict(db.execute("SELECT decision,COUNT(*) FROM legacy_relation_audits GROUP BY decision"))
    title = db.execute("SELECT title FROM documents ORDER BY id LIMIT 1").fetchone()[0]
    version_id, doc_id, body = db.execute(
        "SELECT id,document_id,content FROM document_versions ORDER BY id LIMIT 1"
    ).fetchone()
    source = document_body_metadata("LEGACY:DOCVER:" + version_id)
    assert source and source["doc_id"] == "LEGACY:" + doc_id
    assert source["text"] == body
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
body_metadata = ROOT / "data/legacy/body_chunks_metadata.json"
body_source_ready = False
if body_metadata.exists():
    body_rows = json.loads(body_metadata.read_text(encoding="utf-8"))
    assert len(body_rows) == 2775
    assert all(row.get("content_hash") for row in body_rows)
    assert body_chunk_metadata(body_rows[0]["chunk_id"])["text"] == body_rows[0]["text"]
    by_version = {}
    for row in body_rows:
        version = row["chunk_id"].rsplit(":", 1)[0].removeprefix("LEGACY_BODY:")
        by_version.setdefault(version, []).append(row)
    with sqlite3.connect(f"file:{legacy}?mode=ro", uri=True) as db:
        versions = dict(db.execute(
            "SELECT id,content FROM document_versions WHERE status='indexed'"
        ))
    assert set(by_version) == set(versions)
    for version, parts in by_version.items():
        body = versions[version]
        covered = 0
        for row in sorted(parts, key=lambda item: item["body_start"]):
            start, end = row["body_start"], row["body_end"]
            assert start <= covered < end
            assert row["text"] == body[start:end]
            assert row["content_hash"] == hashlib.sha256(row["text"].encode("utf-8")).hexdigest()
            covered = end
        assert covered == len(body)
    body_source_ready = True
assert (ROOT / "data/search/keyword.sqlite").exists()
assert (ROOT / "data/legacy/keyword.sqlite").exists()
with sqlite3.connect(ROOT / "data/search/keyword.sqlite") as public_index:
    assert public_index.execute(
        "SELECT COUNT(*) FROM docs WHERE chunk_id LIKE 'LEGACY:%'"
    ).fetchone()[0] == 0
with sqlite3.connect(ROOT / "data/legacy/keyword.sqlite") as private_index:
    assert private_index.execute("SELECT COUNT(*) FROM docs").fetchone()[0] == 7927 + 2775
    assert private_index.execute("SELECT COUNT(*) FROM docs WHERE chunk_id LIKE 'LEGACY_BODY:%'").fetchone()[0] == 2775
print(json.dumps({
    "summary_documents": summary["documents"],
    "summary_chunks": summary["chunks"],
    "legacy_document_visible": True,
    "old_document_body_resolves": True,
    "rechunked_body_source_resolves": body_source_ready,
    "legacy_full_body_coverage": body_source_ready,
    "keyword_legacy_hit": any(item["metadata"]["doc_id"].startswith("LEGACY:")
                              for item in search["evidence"]),
    "legacy_relation_audits": audit,
    "legacy_approved_edges": legacy_approved_edges,
}, ensure_ascii=False))
