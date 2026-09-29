#!/usr/bin/env python3
"""Synthetic contract checks for private legacy semantic review."""
import json

from core.kg.schema_manager import SchemaManager
from scripts.legacy_semantic_review import assess, exact_quote, relation_options


class FakeModel:
    def __init__(self, answers):
        self.answers = iter(answers)

    def generate(self, *args, **kwargs):
        return json.dumps(next(self.answers))


schema = SchemaManager()
relation = next(r for r in schema.schema["relation_types"]
                if r.get("domain") and r.get("range"))
subject_type = schema.as_list(relation["domain"])[0]
object_type = schema.as_list(relation["range"])[0]
quote = "AlphaChem applies to BetaChem"
row = ("example", "AlphaChem", "legacy_relation", "BetaChem",
       "chunk", quote, "doc", quote)
answer = {"decision": "valid", "predicate": relation["id"],
          "subject_type": subject_type, "object_type": object_type,
          "quote": quote, "reason": "synthetic"}
status, _, assertion = assess(FakeModel([answer, {"decision": "valid"}]),
                              schema, relation_options(schema), row)
assert status == "approved"
assert assertion["source_chunk_id"] == "LEGACY:chunk"
assert exact_quote("AlphaChem", "AlphaChem", "BetaChem", quote) is False
bad = {**answer, "quote": "AlphaChem missing BetaChem from source"}
status, _, _ = assess(FakeModel([bad]), schema, relation_options(schema), row)
assert status == "needs_review"
status, _, _ = assess(FakeModel([answer, {"decision": "reject"}]),
                      schema, relation_options(schema), row)
assert status == "rejected"
print(json.dumps({"schema_mapping": True, "quote_gate": True,
                  "second_review_gate": True}))
