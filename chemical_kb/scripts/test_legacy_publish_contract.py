#!/usr/bin/env python3
"""Synthetic gate checks for publishing audited legacy corpus assertions."""
import json
import sqlite3

from core.kg.schema_manager import SchemaManager
from scripts.legacy_publish_corpus import rows_to_publish

schema = SchemaManager()
relation = next(r for r in schema.schema["relation_types"]
                if r.get("domain") and r.get("range"))
subject_type = schema.as_list(relation["domain"])[0]
object_type = schema.as_list(relation["range"])[0]
quote = "AlphaChem applies to BetaChem"
assertion = {
    "assertion_id": "test", "subject_id": "s", "subject_type": subject_type,
    "subject_label": "AlphaChem", "predicate": relation["id"],
    "object_id": "o", "object_type": object_type, "object_label": "BetaChem",
    "object_kind": "entity", "source_chunk_id": "LEGACY:chunk",
    "source_doc_id": "LEGACY:doc", "source_text_quote": quote,
}
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE assertions(assertion_id,chunk_id,validation_status,evidence_ok,payload)")
db.execute("CREATE TABLE candidate_audits(assertion_id,decision,reason,reviewed_at)")
db.execute("INSERT INTO assertions VALUES (?,?,?,?,?)",
           ("test", "LEGACY:chunk", "passed", 1, json.dumps(assertion)))
db.execute("INSERT INTO candidate_audits VALUES (?,?,?,?)",
           ("test", "valid", "synthetic", "2026-09-29"))
lookup = {"LEGACY:chunk": {"doc_id": "LEGACY:doc", "text": quote}}
accepted, skipped = rows_to_publish(db, lookup, [], schema)
assert len(accepted) == 1 and not any(skipped.values())
accepted, skipped = rows_to_publish(
    db, {"LEGACY:chunk": {"doc_id": "LEGACY:doc", "text": "unrelated"}}, [], schema)
assert not accepted and skipped["source"] == 1
print(json.dumps({"approved_gate": True, "source_gate": True}))
