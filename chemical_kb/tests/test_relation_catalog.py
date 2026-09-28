import unittest

from core.kg.relation_catalog import approved_assertions, current_relations, validate_assertion


class RelationCatalogTests(unittest.TestCase):
    def test_latest_review_replaces_or_removes_old_edge(self):
        a = {"assertion_id": "A1", "subject_id": "s", "subject_type": "accident",
             "subject_label": "事故", "predicate": "direct_cause", "object_id": "o",
             "object_type": "causal_factor", "object_label": "压力", "object_kind": "entity"}
        reviewed = [
            {"assertion_id": "A1", "decision": "approved", "original_assertion": a,
             "review_id": "r1"},
            {"assertion_id": "A1", "decision": "modified", "original_assertion": a,
             "corrected_assertion": {**a, "object_label": "超压"}, "review_id": "r2"},
        ]
        self.assertEqual([x["object_label"] for x in approved_assertions(reviewed)], ["超压"])
        self.assertEqual(current_relations(reviewed)[0]["revision_count"], 2)
        reviewed.append({"assertion_id": "A1", "decision": "rejected",
                         "original_assertion": reviewed[-1]["corrected_assertion"],
                         "review_id": "r3"})
        self.assertEqual(approved_assertions(reviewed), [])
        self.assertEqual(current_relations(reviewed)[0]["status"], "rejected")

    def test_schema_rejects_invalid_literal_relation(self):
        class Schema:
            def get_entity_attributes(self, entity):
                return [{"name": "requirement_id"}]
            def validate_relation_domain(self, subject, predicate, obj):
                return predicate == "derived_from" and subject == "requirement" and obj == "clause"
        a = {"assertion_id": "A2", "subject_id": "r", "subject_type": "requirement",
             "subject_label": "规则", "predicate": "has_clause", "object_id": "R02",
             "object_type": "literal", "object_label": "R02", "object_kind": "literal"}
        with self.assertRaises(ValueError):
            validate_assertion(a, Schema())
        self.assertTrue(validate_assertion({**a, "predicate": "requirement_id"}, Schema()))


if __name__ == "__main__":
    unittest.main()

