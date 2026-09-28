# -*- coding: utf-8 -*-
"""Wiki Case Builder：把 Wiki section 审核结果转成 Success/Failure Case。

与 KG extraction case 区分（v0.4 规格 4）：task_type = wiki_generation。
- approved  -> Success Case
- modified  -> Failure Case（original_content + reviewed_content + error_type）
- rejected  -> Failure Case（reviewed_content 可空）

复用 CaseRepository 存储；CaseRetriever 按 task_type 硬过滤，不会和 KG extraction 混。
case_id 稳定：hash(wiki_id + section + decision + review_id)，同 section 同 decision 幂等。
"""
import hashlib
from datetime import datetime


def make_wiki_case_id(wiki_id, section, decision, review_id):
    key = f"{wiki_id}|{section}|{decision}|{review_id}"
    return "W_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def build_wiki_embedding_text(case):
    seg = [case.get("entity", ""), case.get("section", ""), case.get("task_type", "")]
    if case.get("case_type") == "failure":
        seg += [
            case.get("error_type", ""),
            case.get("source_text", ""),       # original content
            case.get("reviewed_content", ""),  # corrected
            case.get("review_comment", ""),
        ]
    else:
        seg += [case.get("reviewed_content", "") or case.get("source_text", "")]
    return "。".join(s for s in seg if s)


class WikiCaseBuilder:
    def build_from_review(self, review_record, test_only=False):
        rec = review_record if isinstance(review_record, dict) else review_record.to_dict()
        decision = rec.get("review_status", "")
        if decision not in ("approved", "modified", "rejected"):
            return None
        case_type = "success" if decision == "approved" else "failure"
        case = {
            "case_id": make_wiki_case_id(rec.get("wiki_id", ""), rec.get("section", ""),
                                         decision, rec.get("review_id", "")),
            "case_type": case_type,
            "task_type": "wiki_generation",
            "entity": rec.get("entity", ""),
            "section": rec.get("section", ""),
            "source_doc_id": rec.get("wiki_id", ""),
            "source_chunk_id": "",
            "source_type": "wiki",
            "source_text": rec.get("content", ""),
            "original_content": rec.get("content", ""),
            "reviewed_content": rec.get("reviewed_content", ""),
            "knowledge_source": rec.get("knowledge_source", ""),
            "human_verified_model_knowledge": (
                decision == "approved" and rec.get("knowledge_source") == "model_prior"
            ),
            "error_type": rec.get("error_type", ""),
            "review_comment": rec.get("review_comment", ""),
            "review_id": rec.get("review_id", ""),
            "schema_version": "",
            "case_status": "test" if test_only else "verified",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        case["embedding_text"] = build_wiki_embedding_text(case)
        return case
