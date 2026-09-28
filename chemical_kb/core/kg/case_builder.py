# -*- coding: utf-8 -*-
"""Case Builder：把 ReviewRecord 转成 Success / Failure Case（不重构 v0.1）。

规则（二十四）：
- approved  -> Success Case（reviewed_assertion == original）
- rejected  -> Failure Case（incorrect=original，corrected 可 null）
- modified  -> Failure Case（incorrect=original，corrected=corrected_assertion）
- skipped   -> 不生成 Case

case_id 稳定（三十四）：hash(review_id + assertion_id + decision)。
test_only（二十八）：test_only 的 review -> case_status="test"，不进入 verified index。
"""
import hashlib
from datetime import datetime

from core.kg.schema_manager import SchemaManager

SOURCE_TO_TASK = {"事故": "accident", "标准": "standard", "法规": "regulation"}


def task_type_from_source(source_type):
    return SOURCE_TO_TASK.get(source_type, "unknown")


def make_case_id(review_id, assertion_id, decision):
    key = f"{review_id}|{assertion_id}|{decision}"
    return "C_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def assertion_to_str(a):
    """把 CandidateAssertion dict 转成一行可读文本（用于 embedding / prompt）。"""
    if not a:
        return ""
    return (f"{a.get('subject_type','')}:{a.get('subject_label','')} "
            f"-{a.get('predicate','')}-> {a.get('object_type','')}:{a.get('object_label','')}")


def build_rule_learned(error_type, original, corrected, schema_manager=None):
    """十四、由 decision + error_type + original/corrected 生成结构化描述（不用 LLM 无约束生成）。"""
    orig = original or {}
    corr = corrected or {}
    parts = [f"[{error_type or 'unspecified'}]"]
    parts.append(f"不要把「{orig.get('subject_label','')}」-{orig.get('predicate','')}->"
                 f"「{orig.get('object_label','')}」视为正确。")
    if corr:
        pred = corr.get("predicate", "")
        # 只有 corrected 的 relation 在 schema 中才作为正向目标教给模型（十四）
        ok = schema_manager is None or schema_manager.validate_relation(pred)
        if ok:
            parts.append(f"应抽取为「{corr.get('subject_label','')}」-{pred}->"
                         f"「{corr.get('object_label','')}」。")
        else:
            parts.append("当前 Schema 无合适关系，应保留 unresolved 或提交 schema extension proposal。")
    return "".join(parts)


def build_embedding_text(case):
    """十七、Case 检索用的 embedding 文本（Success / Failure 不同）。"""
    if case.get("case_type") == "failure":
        seg = [
            case.get("source_text", ""),
            case.get("error_type", ""),
            assertion_to_str(case.get("incorrect_output")),
            assertion_to_str(case.get("corrected_output")),
            case.get("rule_learned", ""),
        ]
    else:
        a = case.get("reviewed_assertion") or case.get("original_assertion") or {}
        seg = [
            case.get("source_text", ""),
            case.get("task_type", ""),
            assertion_to_str(a),
            " ".join(case.get("entity_types", [])),
            case.get("relation", ""),
        ]
    return "。".join(s for s in seg if s)


class CaseBuilder:
    def __init__(self, schema_manager=None):
        self.sm = schema_manager or SchemaManager()

    def build_from_review(self, review_record):
        rec = review_record if isinstance(review_record, dict) else review_record.to_dict()
        decision = rec.get("decision", "")
        if decision == "skipped":
            return None
        if decision == "approved":
            return self._build_success(rec)
        if decision in ("rejected", "modified"):
            return self._build_failure(rec)
        return None

    # ------------------------------------------------------------------ #
    def _build_success(self, rec):
        original = rec.get("original_assertion") or {}
        case = {
            "case_id": make_case_id(rec.get("review_id", ""), rec.get("assertion_id", ""), "approved"),
            "case_type": "success",
            "task_type": task_type_from_source(original.get("source_type", "")),
            "source_doc_id": original.get("source_doc_id", ""),
            "source_chunk_id": original.get("source_chunk_id", ""),
            "source_type": original.get("source_type", ""),
            "source_text": original.get("source_text_quote", ""),
            "original_assertion": original,
            "reviewed_assertion": dict(original),
            "schema_version": original.get("schema_version", ""),
            "schema_context": self._schema_context(original),
            "entity_types": [original.get("subject_type", ""), original.get("object_type", "")],
            "relation": original.get("predicate", ""),
            "case_status": "test" if rec.get("test_only") else "verified",
            "quality_score": original.get("confidence", 0.5),
            "review_id": rec.get("review_id", ""),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        case["embedding_text"] = build_embedding_text(case)
        return case

    def _build_failure(self, rec):
        original = rec.get("original_assertion") or {}
        corrected = rec.get("corrected_assertion")  # rejected 时可 None
        case = {
            "case_id": make_case_id(rec.get("review_id", ""), rec.get("assertion_id", ""),
                                    rec.get("decision", "")),
            "case_type": "failure",
            "task_type": task_type_from_source(original.get("source_type", "")),
            "source_doc_id": original.get("source_doc_id", ""),
            "source_chunk_id": original.get("source_chunk_id", ""),
            "source_type": original.get("source_type", ""),
            "source_text": original.get("source_text_quote", ""),
            "incorrect_output": original,
            "corrected_output": corrected,
            "error_type": rec.get("error_type", ""),
            "error_reason": rec.get("review_comment", ""),
            "schema_element": self._schema_element(original, corrected),
            "review_comment": rec.get("review_comment", ""),
            "rule_learned": build_rule_learned(rec.get("error_type", ""), original, corrected, self.sm),
            "review_id": rec.get("review_id", ""),
            "schema_version": original.get("schema_version", ""),
            "case_status": "test" if rec.get("test_only") else "verified",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        case["embedding_text"] = build_embedding_text(case)
        return case

    # ------------------------------------------------------------------ #
    def _schema_context(self, a):
        return {"subject_type": a.get("subject_type", ""),
                "object_type": a.get("object_type", ""),
                "predicate": a.get("predicate", "")}

    def _schema_element(self, original, corrected):
        a = corrected or original
        return {"subject_type": a.get("subject_type", ""),
                "predicate": a.get("predicate", ""),
                "object_type": a.get("object_type", "")}
