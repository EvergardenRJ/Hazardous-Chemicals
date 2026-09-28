# -*- coding: utf-8 -*-
"""Standalone API and static server for the React knowledge explorer.

Run with: python -m app.explorer_api --host 127.0.0.1 --port 8503
The Streamlit application remains available as a separate legacy entry point.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from core.config import BASE_DIR, VECTOR_METADATA
from core.entity_registry import EntityRegistry
from core.kg.relation_catalog import current_relations, validate_assertion
from core.kg.schema_manager import SchemaManager
from core.knowledge import KeywordIndex, _approved, active_at, entity_candidates, export_graph, find_conflicts

ROOT = BASE_DIR
DIST = ROOT / "explorer_web" / "dist"
WIKI_ROOT = ROOT / "data" / "wiki"
REVIEW_ROOT = ROOT / "data" / "kg" / "review"
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
_model_lock = threading.Lock()
_rag = None


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _read_jsonl(path):
    if not Path(path).exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


@lru_cache(maxsize=2)
def _metadata_cached(mtime):
    return _read_json(VECTOR_METADATA, [])


def _metadata():
    try:
        return _metadata_cached(VECTOR_METADATA.stat().st_mtime_ns)
    except FileNotFoundError:
        return []


def _reviews():
    return _read_jsonl(REVIEW_ROOT / "reviewed.jsonl"), _read_jsonl(REVIEW_ROOT / "pending.jsonl")


def _graph(mode="all", as_of=None):
    reviewed, pending = _reviews()
    registry = EntityRegistry()
    nodes, edges = {}, []
    def add(row, status):
        if not isinstance(row, dict) or not active_at(row, as_of):
            return
        if row.get("object_kind") == "literal":
            return
        sid, oid = registry.resolve(row.get("subject_id", "")), registry.resolve(row.get("object_id", ""))
        if not sid or not oid:
            return
        for side, cid in (("subject", sid), ("object", oid)):
            if cid not in nodes:
                nodes[cid] = {"id": cid, "label": row.get(side + "_label") or cid,
                              "type": row.get(side + "_type") or "entity",
                              "source_doc_id": row.get("source_doc_id", "")}
        aid = str(row.get("assertion_id") or f"{sid}-{row.get('predicate')}-{oid}")
        edges.append({"id": aid, "source": sid, "target": oid,
                      "predicate": row.get("predicate", ""), "status": status,
                      "confidence": row.get("confidence", 0),
                      "source_doc_id": row.get("source_doc_id", ""),
                      "source_chunk_id": row.get("source_chunk_id", ""),
                      "source_text_quote": row.get("source_text_quote", ""),
                      "page_start": row.get("page_start", ""),
                      "page_end": row.get("page_end", ""),
                      "valid_from": row.get("valid_from", ""),
                      "valid_to": row.get("valid_to", ""),
                      "recorded_at": row.get("recorded_at") or row.get("created_at", "")})
    for row in _approved(reviewed):
        add(row, "approved")
    if mode != "approved":
        for row in pending:
            add(row, "pending")
    return {"nodes": list(nodes.values()), "edges": edges, "source": "reviewed+pending JSONL"}


def _error(message, status=400):
    return jsonify({"error": message}), status


@app.before_request
def _guard_mutations():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    origin = request.headers.get("Origin", "")
    if origin:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(origin)
            if parsed.netloc != request.host:
                return _error("Origin not allowed", 403)
        except ValueError:
            return _error("Invalid origin", 403)
    expected = os.environ.get("CHEM_KB_API_KEY")
    if expected and request.headers.get("X-API-Key") != expected:
        return _error("API key required", 401)
    return None


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "chemical-knowledge-explorer"})


def _batch_progress():
    path = ROOT / "data/kg/batch_extraction/corpus.sqlite"
    if not path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2) as db:
            counts = dict(db.execute("SELECT status,COUNT(*) FROM chunks GROUP BY status"))
            processed_docs = db.execute("SELECT COUNT(DISTINCT doc_id) FROM chunks WHERE status IN ('done','empty')").fetchone()[0]
            staged, grounded = db.execute("SELECT COUNT(*),COALESCE(SUM(evidence_ok),0) FROM assertions").fetchone()
        return {"chunks": counts, "processed_docs": processed_docs,
                "staged_candidates": staged, "evidence_matched": grounded}
    except sqlite3.Error:
        return None


@app.get("/api/summary")
def summary():
    reviewed, pending = _reviews()
    graph = _graph("approved")
    catalog = current_relations(reviewed, pending)
    source_assertions = [item["assertion"] for item in catalog]
    active_assertions = [item["assertion"] for item in catalog if item["status"] in ("approved", "modified")]
    wiki_count = sum(1 for p in WIKI_ROOT.iterdir() if p.is_dir() and p.name != "review") if WIKI_ROOT.exists() else 0
    metadata = _metadata()
    return jsonify({
        "chunks": len(metadata), "documents": len({str(m.get("doc_id")) for m in metadata if m.get("doc_id")}),
        "nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "pending": len(pending),
        "reviewed": len(active_assertions), "review_events": len(reviewed), "wikis": wiki_count,
        "relation_candidates": len(catalog),
        "relation_source_docs": len({a.get("source_doc_id") for a in source_assertions if a.get("source_doc_id")}),
        "relation_source_chunks": len({a.get("source_chunk_id") for a in source_assertions if a.get("source_chunk_id")}),
        "entity_relations": sum(1 for a in active_assertions if a.get("object_kind", "entity") != "literal"),
        "literal_attributes": sum(1 for a in active_assertions if a.get("object_kind") == "literal"),
        "keyword_index": (ROOT / "data/search/keyword.sqlite").exists(),
        "batch_extraction": _batch_progress(),
    })


@app.get("/api/graph")
def graph():
    mode = request.args.get("mode", "all")
    if mode not in ("all", "approved"):
        return _error("Invalid graph mode")
    as_of = request.args.get("as_of") or None
    try:
        return jsonify(_graph(mode, as_of))
    except ValueError:
        return _error("Invalid date")


@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()[:200]
    if not query:
        return jsonify({"nodes": [], "evidence": []})
    graph = _graph("all")
    matching_nodes = [n for n in graph["nodes"] if query.casefold() in (n["label"] + " " + n["id"]).casefold()][:12]
    evidence = KeywordIndex(ROOT / "data/search/keyword.sqlite").search(query, limit=8)
    return jsonify({"nodes": matching_nodes, "evidence": evidence})


def _get_rag():
    global _rag
    if _rag is None:
        from core.rag import RAGSystem
        _rag = RAGSystem()
    return _rag


@app.post("/api/ask")
def ask():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question") or "").strip()[:2000]
    if not question:
        return _error("Question required")
    try:
        with _model_lock:
            result = _get_rag().answer(question, as_of=data.get("as_of") or None)
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            return _error("GPU memory is exhausted; close other model sessions and retry", 503)
        raise
    return jsonify(result)


@app.get("/api/schema")
def schema():
    return jsonify(SchemaManager().schema)


@app.get("/api/reviews")
def reviews():
    reviewed, pending = _reviews()
    items = current_relations(reviewed, pending)
    status = request.args.get("status", "").strip()
    query = request.args.get("q", "").casefold().strip()
    if status:
        items = [item for item in items if item["status"] == status]
    if query:
        items = [item for item in items if query in " ".join(str(item["assertion"].get(k, ""))
                 for k in ("assertion_id", "subject_label", "predicate", "object_label",
                           "source_doc_id", "source_text_quote")).casefold()]
    return jsonify({"items": items, "total": len(items),
                    "pending": [item["assertion"] for item in items if item["status"] == "pending"],
                    "review_event_count": len(reviewed)})


@app.get("/api/reviews/<assertion_id>/source")
def relation_source(assertion_id):
    reviewed, pending = _reviews()
    item = next((x for x in current_relations(reviewed, pending)
                 if x["assertion_id"] == assertion_id), None)
    if item is None:
        return _error("Relation not found", 404)
    assertion = item["assertion"]
    chunk_id = assertion.get("source_chunk_id", "")
    chunk = next((row for row in _metadata() if row.get("chunk_id") == chunk_id), None)
    related = [x["assertion_id"] for x in current_relations(reviewed, pending)
               if x["assertion"].get("source_chunk_id") == chunk_id]
    return jsonify({"chunk": chunk, "source_chunk_id": chunk_id,
                    "source_quote": assertion.get("source_text_quote", ""),
                    "related_assertion_ids": related})


@app.get("/api/reviews/<assertion_id>/history")
def relation_history(assertion_id):
    reviewed, pending = _reviews()
    history = [row for row in reviewed if str(row.get("assertion_id")) == assertion_id]
    if not history and not any(str(row.get("assertion_id")) == assertion_id for row in pending):
        return _error("Relation not found", 404)
    return jsonify({"assertion_id": assertion_id, "reviews": history})


@app.post("/api/reviews/<assertion_id>")
def review_assertion(assertion_id):
    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    if decision not in ("approved", "rejected", "modified"):
        return _error("Invalid decision")
    if decision in ("rejected", "modified") and not str(data.get("comment") or "").strip():
        return _error("Comment required")
    from core.kg.review_manager import ReviewManager
    from core.kg.case_builder import CaseBuilder
    from core.kg.case_repository import CaseRepository
    manager = ReviewManager()
    reviewed, pending = manager.get_reviewed(), manager.get_pending()
    current = next((item for item in current_relations(reviewed, pending)
                    if item["assertion_id"] == assertion_id), None)
    if current is None:
        return _error("Relation not found", 404)
    if "expected_review_id" in data and data["expected_review_id"] != current["review_id"]:
        return _error("Relation changed since it was loaded; refresh before saving", 409)
    assertion = dict(current["assertion"])
    corrected = None
    if decision == "modified":
        proposed = data.get("corrected")
        if not isinstance(proposed, dict):
            return _error("Corrected assertion required")
        editable = ("subject_id", "subject_type", "subject_label", "predicate",
                    "object_id", "object_type", "object_label", "object_kind",
                    "valid_from", "valid_to")
        corrected = {**assertion, **{key: proposed[key] for key in editable if key in proposed}}
        corrected["assertion_id"] = assertion_id
    if decision != "rejected":
        try:
            validate_assertion(corrected or assertion, SchemaManager())
        except ValueError as exc:
            return _error(str(exc))
    record = {
        "assertion_id": assertion_id, "decision": decision, "original_assertion": assertion,
        "corrected_assertion": corrected, "error_type": data.get("error_type", ""),
        "review_comment": data.get("comment", ""), "reviewed_by": data.get("reviewer") or "adamin",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "source_doc_id": assertion.get("source_doc_id", ""),
        "source_chunk_id": assertion.get("source_chunk_id", ""),
        "schema_version": assertion.get("schema_version", ""), "review_version": "explorer-v2",
        "test_only": False,
    }
    record = manager.submit_review(record)
    case = CaseBuilder().build_from_review(record)
    if case:
        CaseRepository().add_case(case)
    return jsonify({"record": record, "case_created": case is not None})

@app.get("/api/audit")
def audit():
    reviewed, pending = _reviews()
    rows = _approved(reviewed) + pending
    registry = EntityRegistry()
    return jsonify({"conflicts": find_conflicts([registry.apply(a) for a in rows]),
                    "entity_candidates": entity_candidates(rows),
                    "aliases": registry.mapping()})


@app.post("/api/entities/alias")
def alias():
    data = request.get_json(silent=True) or {}
    try:
        result = EntityRegistry().decide(data.get("alias_id", ""), data.get("canonical_id", ""),
                                         data.get("reviewer", ""), data.get("action", "merge"))
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc))


@app.get("/api/export")
def export():
    fmt = request.args.get("format", "jsonld")
    if fmt not in ("jsonld", "turtle", "graphml", "csv"):
        return _error("Invalid format")
    reviewed, _ = _reviews()
    try:
        body = export_graph(reviewed, fmt, request.args.get("as_of") or None)
    except ValueError:
        return _error("Invalid date")
    ext = {"jsonld": "jsonld", "turtle": "ttl", "graphml": "graphml", "csv": "csv"}[fmt]
    mime = {"jsonld": "application/ld+json", "turtle": "text/turtle",
            "graphml": "application/graphml+xml", "csv": "text/csv"}[fmt]
    return Response(body, mimetype=mime,
                    headers={"Content-Disposition": f'attachment; filename="chemical_knowledge.{ext}"'})


@app.get("/api/documents")
def documents():
    metadata = _metadata()
    grouped = {}
    for row in metadata:
        did = str(row.get("doc_id") or "")
        if not did:
            continue
        entry = grouped.setdefault(did, {"doc_id": did, "title": row.get("title") or did,
                                         "code": row.get("code") or "",
                                         "document_type": row.get("document_type") or "",
                                         "chunks": 0})
        entry["chunks"] += 1
    q = request.args.get("q", "").casefold().strip()
    rows = list(grouped.values())
    if q:
        rows = [r for r in rows if q in (r["title"] + " " + r["code"] + " " + r["doc_id"]).casefold()]
    rows.sort(key=lambda x: x["title"])
    page = max(1, int(request.args.get("page", 1)))
    size = min(100, max(1, int(request.args.get("size", 25))))
    return jsonify({"total": len(rows), "page": page, "items": rows[(page-1)*size:page*size]})


@app.post("/api/documents/upload")
def upload():
    file = request.files.get("file")
    if file is None:
        return _error("PDF required")
    name = file.filename or ""
    if name != Path(name).name or "\\" in name or not name.lower().endswith(".pdf"):
        return _error("Invalid PDF filename")
    head = file.stream.read(5)
    if head != b"%PDF-":
        return _error("Not a PDF")
    file.stream.seek(0)
    directory = ROOT / "data/upload"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    if target.exists():
        return _error("File already exists", 409)
    file.save(target)
    return jsonify({"filename": name, "bytes": target.stat().st_size, "status": "saved_for_processing"}), 201


def _safe_entity(value):
    value = str(value or "").strip()
    if not value or len(value) > 100 or "/" in value or "\\" in value or value in (".", ".."):
        raise ValueError("Invalid entity")
    return value


@app.get("/api/wiki")
def wiki_list():
    names = sorted(p.name for p in WIKI_ROOT.iterdir() if p.is_dir() and p.name != "review") if WIKI_ROOT.exists() else []
    return jsonify({"entities": names})


@app.get("/api/wiki/<entity>")
def wiki_detail(entity):
    try:
        entity = _safe_entity(entity)
    except ValueError as exc:
        return _error(str(exc))
    root = WIKI_ROOT / entity
    md = root / "wiki.md"
    if not md.exists():
        return _error("Wiki not found", 404)
    from core.kg.wiki_review_manager import WikiReviewManager
    manager = WikiReviewManager()
    markdown = md.read_text(encoding="utf-8")
    return jsonify({"entity": entity, "markdown": markdown,
                    "sections": manager.get_sections(entity, markdown),
                    "reviews": manager.get_reviews(entity),
                    "evidence": _read_json(root / "evidence.json", [])})


@app.post("/api/wiki/<entity>/generate")
def wiki_generate(entity):
    try:
        entity = _safe_entity(entity)
    except ValueError as exc:
        return _error(str(exc))
    from core.wiki_generator import WikiGenerator
    with _model_lock:
        result = WikiGenerator(_get_rag()).generate(entity)
    return jsonify({"entity": entity, "result": result})


@app.post("/api/wiki/<entity>/review")
def wiki_review(entity):
    try:
        entity = _safe_entity(entity)
    except ValueError as exc:
        return _error(str(exc))
    from core.kg.wiki_review_manager import WikiReviewManager
    from core.kg.wiki_case_builder import WikiCaseBuilder
    from core.kg.case_repository import CaseRepository
    data = request.get_json(silent=True) or {}
    status = data.get("review_status")
    if status not in ("approved", "modified", "rejected"):
        return _error("Invalid review status")
    if status != "approved" and not str(data.get("review_comment") or "").strip():
        return _error("Comment required")
    manager = WikiReviewManager()
    md = WIKI_ROOT / entity / "wiki.md"
    if not md.exists():
        return _error("Wiki not found", 404)
    markdown = md.read_text(encoding="utf-8")
    manager.init_review(entity, markdown)
    section = next((s for s in manager.get_sections(entity, markdown)
                    if s["section"] == data.get("section")), None)
    if section is None:
        return _error("Section not found", 404)
    record = dict(manager.get_reviews(entity).get(section["section"], {}))
    record.update({"section": section["section"], "content": section["content"],
                   "knowledge_source": section["knowledge_source"],
                   "evidence_ids": section["evidence_ids"], "review_status": status,
                   "reviewed_content": data.get("reviewed_content") or (section["content"] if status == "approved" else ""),
                   "error_type": data.get("error_type") or "",
                   "review_comment": data.get("review_comment") or ""})
    manager.submit_review(entity, record)
    case = WikiCaseBuilder().build_from_review(record)
    if case:
        CaseRepository().add_case(case)
    return jsonify({"record": record})


@app.get("/")
def index():
    if not (DIST / "index.html").exists():
        return _error("Frontend bundle not built", 503)
    return send_from_directory(DIST, "index.html")


@app.get("/<path:path>")
def static_or_index(path):
    if (DIST / path).is_file():
        return send_from_directory(DIST, path)
    return index()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8503)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("CHEM_KB_API_KEY"):
        parser.error("Set CHEM_KB_API_KEY before binding to a non-loopback host")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()







