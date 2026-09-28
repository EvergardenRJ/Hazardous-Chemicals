# -*- coding: utf-8 -*-
"""Versioned relation projection for the Explorer and retrieval layer.

Reviewed JSONL is append-only: the last review for an assertion id is current.
Pending rows are included only while they have no reviewed revision.
"""
from __future__ import annotations


def current_relations(reviewed, pending=()):
    latest = {}
    counts = {}
    order = []
    for record in reviewed:
        if not isinstance(record, dict):
            continue
        aid = str(record.get("assertion_id") or (record.get("corrected_assertion") or record.get("original_assertion") or {}).get("assertion_id") or "")
        if not aid:
            continue
        if aid not in latest:
            order.append(aid)
        counts[aid] = counts.get(aid, 0) + 1
        decision = record.get("decision") or record.get("review_status") or ""
        if decision == "modified":
            assertion = record.get("corrected_assertion") or record.get("original_assertion")
        else:
            assertion = record.get("original_assertion") or record
        if not isinstance(assertion, dict):
            continue
        latest[aid] = {
            "assertion_id": aid, "status": decision, "assertion": dict(assertion),
            "review_id": record.get("review_id", ""),
            "reviewed_by": record.get("reviewed_by", ""),
            "reviewed_at": record.get("reviewed_at", ""),
            "review_comment": record.get("review_comment", ""),
        }
    for assertion in pending:
        if not isinstance(assertion, dict):
            continue
        aid = str(assertion.get("assertion_id") or "")
        if aid and aid not in latest:
            order.append(aid)
            latest[aid] = {
                "assertion_id": aid, "status": "pending", "assertion": dict(assertion),
                "review_id": "", "reviewed_by": "", "reviewed_at": "", "review_comment": "",
            }
            counts[aid] = 0
    return [{**latest[aid], "revision_count": counts[aid]} for aid in order if aid in latest]


def approved_assertions(reviewed):
    result = []
    for item in current_relations(reviewed):
        if item["status"] in ("approved", "modified"):
            assertion = dict(item["assertion"])
            assertion["review_id"] = item["review_id"]
            assertion["reviewed_by"] = item["reviewed_by"] or "human"
            assertion["reviewed_at"] = item["reviewed_at"]
            result.append(assertion)
    return result


def validate_assertion(assertion, schema):
    """Validate editable triple fields without changing source provenance."""
    for key in ("assertion_id", "subject_id", "subject_type", "subject_label",
                "predicate", "object_id", "object_type", "object_label"):
        if not str(assertion.get(key) or "").strip():
            raise ValueError(f"{key} is required")
    kind = assertion.get("object_kind") or ("literal" if assertion["object_type"] == "literal" else "entity")
    if kind == "literal":
        if assertion["object_type"] != "literal":
            raise ValueError("Literal object must use object_type=literal")
        attrs = schema.get_entity_attributes(assertion["subject_type"]) or []
        if assertion["predicate"] not in {a.get("name") for a in attrs}:
            raise ValueError("Literal predicate is not an attribute of the subject type")
    elif kind == "entity":
        if not schema.validate_relation_domain(
            assertion["subject_type"], assertion["predicate"], assertion["object_type"]
        ):
            raise ValueError("Relation domain/range does not match schema")
    else:
        raise ValueError("Invalid object_kind")
    start, end = assertion.get("valid_from") or "", assertion.get("valid_to") or ""
    if start and end and str(start) >= str(end):
        raise ValueError("valid_from must precede valid_to")
    return True


