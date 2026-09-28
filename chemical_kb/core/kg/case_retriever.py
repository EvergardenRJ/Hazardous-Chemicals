# -*- coding: utf-8 -*-
"""Case Retriever：Success / Failure 分开检索 + 硬过滤 + 简单 metadata boost + prompt formatter。

十九/二十：Success 与 Failure 必须分开检索，不能混排。
二十：v0.2 不引入复杂学习权重——先硬过滤（verified + task_type match），
     再语义相似度，再加简单 metadata boost（source_type 优先），记录
     raw_similarity / final_score / ranking_reasons 方便后续实验。
"""
import json
from pathlib import Path

import faiss
import numpy as np

from core.embedding import EmbeddingModel
from core.kg.case_repository import CaseRepository
from core.kg.case_builder import assertion_to_str

BOOST_SOURCE_TYPE = 0.05
BOOST_TASK_TYPE = 0.0  # task_type 已作为硬过滤，此处仅记录原因，不额外加权


class CaseRetriever:
    def __init__(self, repository=None, embedding_model=None):
        self.repo = repository or CaseRepository()
        self._embedding_model = embedding_model  # 惰性
        self.success_dir = self.repo.success_dir
        self.failure_dir = self.repo.failure_dir

    def _embedding(self):
        if self._embedding_model is None:
            self._embedding_model = EmbeddingModel()
        return self._embedding_model

    # ------------------------------------------------------------------ #
    def retrieve(self, text, task_type, source_type, top_k_success=3, top_k_failure=3):
        """返回 {"success_cases": [...], "failure_cases": [...]}，两者分开、不混排。"""
        success = self._retrieve_side(self.success_dir, text, task_type, source_type,
                                      top_k_success, case_type="success")
        failure = self._retrieve_side(self.failure_dir, text, task_type, source_type,
                                      top_k_failure, case_type="failure")
        return {"success_cases": success, "failure_cases": failure}

    def _retrieve_side(self, index_dir, text, task_type, source_type, top_k, case_type):
        index_path = index_dir / "faiss.index"
        meta_path = index_dir / "metadata.json"
        if not index_path.exists() or not meta_path.exists():
            return []
        with open(meta_path, encoding="utf-8") as f:
            metadata = json.load(f)
        if not metadata:
            return []
        idx = faiss.read_index(str(index_path))
        emb = self._embedding()
        vec = np.asarray(emb.encode(text), dtype="float32")
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        k = min(idx.ntotal, max(top_k * 10, top_k))
        scores, idxs = idx.search(vec, k)

        ranked = []
        for score, pos in zip(scores[0], idxs[0]):
            if pos < 0 or int(pos) >= len(metadata):
                continue
            case = metadata[int(pos)]
            # 硬过滤：verified + task_type match
            if case.get("case_status") != "verified":
                continue
            if task_type and case.get("task_type") and case.get("task_type") != task_type:
                continue
            boost, reasons = self._metadata_boost(case, task_type, source_type)
            final = float(score) + boost
            ranked.append({
                **case,
                "raw_similarity": float(score),
                "final_score": final,
                "ranking_reasons": reasons,
            })
        ranked.sort(key=lambda x: -x["final_score"])
        return ranked[:top_k]

    @staticmethod
    def _metadata_boost(case, task_type, source_type):
        boost = 0.0
        reasons = []
        if source_type and case.get("source_type") == source_type:
            boost += BOOST_SOURCE_TYPE
            reasons.append("source_type_match")
        if task_type and case.get("task_type") == task_type:
            reasons.append("task_type_match")  # 已硬过滤，此处仅记录
        return boost, reasons


# --------------------------------------------------------------------------- #
# 二十一、Prompt Formatter（Success / Failure 结构分离，失败明确标识为负例）
# --------------------------------------------------------------------------- #
def format_success_cases(cases):
    if not cases:
        return ""
    blocks = ["Previous Verified Success:"]
    for c in cases:
        a = c.get("reviewed_assertion") or c.get("original_assertion") or {}
        blocks.append(
            "Input: " + str(c.get("source_text", "")) + "\n"
            "Correct Output: " + assertion_to_str(a) + "\n"
            "Schema Relation: " + str(c.get("relation", "")) + "\n"
            "Why This Is Correct: human approved"
        )
    return "\n".join(blocks)


def format_failure_cases(cases):
    if not cases:
        return ""
    blocks = ["Previous Verified Failure:"]
    for c in cases:
        inc = c.get("incorrect_output") or {}
        corr = c.get("corrected_output")
        why = (str(c.get("error_type", "")) + " - " + str(c.get("review_comment", ""))).strip(" -")
        corrected_line = ("Corrected Output: " + assertion_to_str(corr)) if corr \
            else "Corrected Output: (无，建议 unresolved 或提交 schema extension proposal)"
        blocks.append(
            "Input: " + str(c.get("source_text", "")) + "\n"
            "Incorrect Output: " + assertion_to_str(inc) + "\n"
            "Why Incorrect: " + why + "\n"
            + corrected_line + "\n"
            "Rule Learned: " + str(c.get("rule_learned", ""))
        )
    blocks.append("IMPORTANT: The incorrect output above is a negative example. Do NOT copy it.")
    return "\n".join(blocks)
