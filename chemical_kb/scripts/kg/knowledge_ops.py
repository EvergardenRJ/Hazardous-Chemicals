#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build keyword index and audit/export reviewed knowledge."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.config import BASE_DIR, VECTOR_METADATA

LEGACY_METADATA = BASE_DIR / "data/legacy/chunks_metadata.json"
from core.knowledge import KeywordIndex, entity_candidates, find_conflicts, export_graph, _approved
from core.kg.review_manager import ReviewManager
from core.entity_registry import EntityRegistry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build-index", "audit", "export"])
    parser.add_argument("--format", choices=["jsonld", "turtle", "graphml", "csv"], default="jsonld")
    parser.add_argument("--as-of")
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.action == "build-index":
        with open(VECTOR_METADATA, encoding="utf-8") as stream:
            rows = json.load(stream)
        dest = BASE_DIR / "data/search/keyword.sqlite"
        KeywordIndex(dest).build(rows)
        result = {"public_indexed": len(rows), "public_path": str(dest)}
        if LEGACY_METADATA.exists():
            with LEGACY_METADATA.open(encoding="utf-8") as stream:
                legacy_rows = json.load(stream)
            private_dest = BASE_DIR / "data/legacy/keyword.sqlite"
            KeywordIndex(private_dest).build(legacy_rows)
            result.update({"private_indexed": len(legacy_rows),
                           "private_path": str(private_dest)})
        print(json.dumps(result, ensure_ascii=False))
        return
    manager = ReviewManager()
    reviewed = manager.get_reviewed()
    if args.action == "audit":
        assertions = _approved(reviewed) + manager.get_pending()
        data = {"entity_candidates": entity_candidates(assertions),
                "conflicts": find_conflicts([EntityRegistry().apply(a) for a in assertions])}
        dest = Path(args.output or BASE_DIR / "data/kg/knowledge_audit.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"entity_candidates": len(data["entity_candidates"]),
                          "conflicts": len(data["conflicts"]), "path": str(dest)}, ensure_ascii=False))
        return
    body = export_graph(reviewed, args.format, args.as_of)
    ext = {"jsonld": "jsonld", "turtle": "ttl", "graphml": "graphml", "csv": "csv"}[args.format]
    dest = Path(args.output or BASE_DIR / "data/kg/exports" / ("knowledge." + ext))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(json.dumps({"format": args.format, "bytes": len(body.encode("utf-8")),
                      "path": str(dest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

