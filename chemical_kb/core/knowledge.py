# -*- coding: utf-8 -*-
"""Temporal facts, retrieval fusion, deduplication, conflict review and exports.

Intervals are half-open [valid_from, valid_to). Unknown bounds are open.
No automatic merge or conflict resolution is performed.
"""
from __future__ import annotations
import csv
import io
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from xml.etree.ElementTree import Element, SubElement, tostring


def _instant(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw[:10] if len(raw) == 10 else raw)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _bounds(row):
    start = _instant(row.get("valid_from"))
    end = _instant(row.get("valid_to"))
    if start and end and end <= start:
        raise ValueError("valid_to must be after valid_from")
    return start, end


def active_at(row, at):
    """Rows without validity dates remain visible; recorded_at is audit time."""
    if not at:
        return True
    point = _instant(at)
    try:
        start, end = _bounds(row)
    except (ValueError, TypeError):
        return False
    return (start is None or start <= point) and (end is None or point < end)


def overlap(a, b):
    try:
        a0, a1 = _bounds(a)
        b0, b1 = _bounds(b)
    except (ValueError, TypeError):
        return False
    return (a1 is None or b0 is None or b0 < a1) and (b1 is None or a0 is None or a0 < b1)


def _terms(text):
    normalized = unicodedata.normalize("NFKC", str(text)).lower()
    latin = re.findall(r"[a-z0-9]+", normalized)
    han = re.findall(r"[\u4e00-\u9fff]+", normalized)
    grams = []
    for run in han:
        grams.extend(run[i:i + 2] for i in range(max(0, len(run) - 1)))
        if len(run) == 1:
            grams.append(run)
    return list(dict.fromkeys(latin + grams))


def _key(item):
    meta = item.get("metadata", item)
    return str(meta.get("chunk_id") or (str(meta.get("doc_id", "")) + ":" + str(meta.get("page_start", "")) + ":" + str(meta.get("text", ""))[:80]))


class KeywordIndex:
    """SQLite FTS5 BM25 index over the existing vector metadata."""
    def __init__(self, path):
        self.path = Path(path)

    def build(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".building")
        if tmp.exists():
            tmp.unlink()
        db = sqlite3.connect(tmp)
        try:
            db.execute("CREATE VIRTUAL TABLE docs USING fts5(chunk_id UNINDEXED, tokens, metadata UNINDEXED)")
            db.executemany(
                "INSERT INTO docs(chunk_id,tokens,metadata) VALUES (?,?,?)",
                ((str(row.get("chunk_id") or i),
                  " ".join(_terms(" ".join(str(row.get(k, "")) for k in ("title", "code", "text")))),
                  json.dumps(row, ensure_ascii=False)) for i, row in enumerate(records))
            )
            db.commit()
        finally:
            db.close()
        tmp.replace(self.path)

    def search(self, query, limit=50):
        terms = _terms(query)[:24]
        if not terms or not self.path.exists():
            return []
        expr = " OR ".join('"' + term + '"' for term in terms)
        db = sqlite3.connect(self.path)
        try:
            rows = db.execute(
                "SELECT metadata, bm25(docs) FROM docs WHERE docs MATCH ? ORDER BY bm25(docs) LIMIT ?",
                (expr, max(1, int(limit))),
            ).fetchall()
        finally:
            db.close()
        return [{"score": float(-score), "metadata": json.loads(meta)} for meta, score in rows]


def fuse_rrf(routes, weights=None, k=60, at=None, limit=50):
    weights = weights or {"vector": 1.0, "keyword": 1.0, "graph": 0.8}
    merged = {}
    for route, items in routes.items():
        seen = set()
        for rank, item in enumerate(items, 1):
            metadata = item.get("metadata", {})
            if not active_at(metadata, at):
                continue
            key = _key(item)
            if key in seen:
                continue
            seen.add(key)
            if key not in merged:
                merged[key] = {"metadata": metadata, "score": item.get("score", 0),
                               "rrf_score": 0.0, "routes": [], "route_ranks": {}}
            out = merged[key]
            out["rrf_score"] += float(weights.get(route, 1.0)) / (k + rank)
            out["routes"].append(route)
            out["route_ranks"][route] = rank
            if route == "vector":
                out["score"] = item.get("score", 0)
    return sorted(merged.values(), key=lambda row: (-row["rrf_score"], _key(row)))[:limit]


def _canon_type(row, prefix):
    return str(row.get(prefix + "_type") or "").strip().lower()


def _canon_label(value):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", str(value)).casefold())


def entity_candidates(assertions):
    """Conservative global candidates: same type and normalized label across sources."""
    groups = {}
    for row in assertions:
        for side in ("subject", "object"):
            if side == "object" and row.get("object_kind") == "literal":
                continue
            cid = str(row.get(side + "_id") or "")
            label = str(row.get(side + "_label") or "")
            key = (_canon_type(row, side), _canon_label(label))
            if cid and key[0] and key[1]:
                groups.setdefault(key, {}).setdefault(cid, set()).add(str(row.get("source_doc_id") or ""))
    return [{"entity_type": typ, "normalized_label": label, "canonical_ids": sorted(ids),
             "source_doc_ids": sorted(set().union(*ids.values()))}
            for (typ, label), ids in sorted(groups.items()) if len(ids) > 1]


def find_conflicts(assertions):
    """Find functional-value clashes across documents with overlapping validity.

    Different objects are review candidates, not automatically adjudicated contradictions.
    """
    groups = {}
    for row in assertions:
        key = (row.get("subject_id"), row.get("predicate"))
        if all(key) and row.get("object_id"):
            groups.setdefault(key, []).append(row)
    conflicts = []
    for key, rows in groups.items():
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if (a.get("object_id") != b.get("object_id")
                        and a.get("source_doc_id") != b.get("source_doc_id")
                        and overlap(a, b)):
                    conflicts.append({
                        "subject_id": key[0], "predicate": key[1],
                        "assertion_ids": [a.get("assertion_id"), b.get("assertion_id")],
                        "source_doc_ids": [a.get("source_doc_id"), b.get("source_doc_id")],
                        "object_ids": [a.get("object_id"), b.get("object_id")],
                        "status": "needs_review",
                    })
    return conflicts


def _approved(rows):
    from core.kg.relation_catalog import approved_assertions
    return approved_assertions(rows)


def export_graph(rows, fmt="jsonld", at=None):
    """Export approved assertions only. Formats: jsonld, turtle, graphml, csv."""
    assertions = [a for a in _approved(rows) if active_at(a, at)]
    if fmt == "csv":
        output = io.StringIO()
        fields = ("assertion_id", "subject_id", "predicate", "object_id", "source_doc_id",
                  "source_chunk_id", "valid_from", "valid_to", "review_id")
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: a.get(k, "") for k in fields} for a in assertions)
        return output.getvalue()
    if fmt == "graphml":
        root = Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
        for key in ("label", "type", "source_doc_id", "valid_from", "valid_to"):
            SubElement(root, "key", id=key, attrib={"for": "all", "attr.name": key, "attr.type": "string"})
        graph = SubElement(root, "graph", edgedefault="directed")
        nodes = {}
        for a in assertions:
            for side in ("subject", "object"):
                cid = a.get(side + "_id")
                if cid and (side == "subject" or a.get("object_kind") != "literal"):
                    nodes[str(cid)] = (a.get(side + "_label", ""), a.get(side + "_type", ""))
        for cid, (label, typ) in nodes.items():
            node = SubElement(graph, "node", id=cid)
            for k, value in (("label", label), ("type", typ)):
                SubElement(node, "data", key=k).text = str(value)
        for a in assertions:
            if a.get("subject_id") and a.get("object_id") and a.get("object_kind") != "literal":
                edge = SubElement(graph, "edge", id=str(a.get("assertion_id")),
                                  source=str(a["subject_id"]), target=str(a["object_id"]))
                for k, value in (("label", a.get("predicate")), ("source_doc_id", a.get("source_doc_id")),
                                 ("valid_from", a.get("valid_from")), ("valid_to", a.get("valid_to"))):
                    SubElement(edge, "data", key=k).text = str(value or "")
        return tostring(root, encoding="unicode", xml_declaration=True)
    base = "urn:chemical-kb:"
    def uri(kind, value):
        return base + kind + "/" + quote(str(value or "unknown"), safe="")
    entities = []
    for a in assertions:
        aid = a.get("assertion_id")
        if not aid:
            continue
        doc = uri("document", a.get("source_doc_id"))
        chunk = uri("chunk", a.get("source_chunk_id"))
        assertion = uri("assertion", aid)
        activity = uri("extraction", aid)
        reviewer = uri("agent", a.get("reviewed_by") or "review-process")
        entities += [
            {"@id": doc, "@type": "prov:Entity"},
            {"@id": chunk, "@type": "prov:Entity", "prov:wasDerivedFrom": {"@id": doc}},
            {"@id": activity, "@type": "prov:Activity", "prov:used": {"@id": chunk},
             "prov:wasAssociatedWith": {"@id": reviewer}},
            {"@id": reviewer, "@type": "prov:Agent"},
            {"@id": assertion, "@type": "prov:Entity",
             "prov:wasGeneratedBy": {"@id": activity},
             "prov:wasDerivedFrom": {"@id": chunk},
             "kb:subject": {"@id": uri("entity", a.get("subject_id"))},
             "kb:predicate": a.get("predicate", ""),
             "kb:object": {"@id": uri("entity", a.get("object_id"))} if a.get("object_id") else a.get("object_label", ""),
             "kb:validFrom": a.get("valid_from", ""),
             "kb:validTo": a.get("valid_to", "")},
        ]
    context = {"prov": "http://www.w3.org/ns/prov#", "kb": base + "vocab#"}
    if fmt == "jsonld":
        return json.dumps({"@context": context, "@graph": entities}, ensure_ascii=False, indent=2)
    if fmt == "turtle":
        def term(value):
            return "<" + value + ">"
        triples = ["@prefix prov: <http://www.w3.org/ns/prov#> .", f"@prefix kb: <{base}vocab#> ."]
        for entity in entities:
            subject = term(entity["@id"])
            triples.append(subject + " a " + entity["@type"] + " .")
            for pred, val in entity.items():
                if pred.startswith("@") or not val:
                    continue
                obj = term(val["@id"]) if isinstance(val, dict) else json.dumps(str(val), ensure_ascii=False)
                triples.append(subject + " " + pred + " " + obj + " .")
        return "\n".join(triples) + "\n"
    raise ValueError(f"Unsupported export format: {fmt}")


