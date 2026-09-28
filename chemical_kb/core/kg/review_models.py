# -*- coding: utf-8 -*-
"""Human Review 数据模型：ReviewRecord / SchemaExtensionProposal / Error Taxonomy。

对应 v0.2 规格 六 / 七 / 十 / 十五 / 三十二 节。
"""
from dataclasses import dataclass, field, asdict

# 十、Failure Error Taxonomy（12 类 + other）
ERROR_TAXONOMY = [
    "entity_missing",
    "entity_extra",
    "entity_type_error",
    "relation_missing",
    "relation_extra",
    "relation_type_error",
    "relation_direction_error",
    "canonicalization_error",
    "attribute_error",
    "provenance_error",
    "hallucination",
    "schema_violation",
    "other",
]

# 审核决定（skip 不生成 Case）
DECISIONS = ["approved", "rejected", "modified", "skipped"]


@dataclass
class ReviewRecord:
    """一条人工审核记录。original_assertion / corrected_assertion 为 CandidateAssertion dict。"""
    review_id: str = ""
    assertion_id: str = ""
    decision: str = ""                  # approved | rejected | modified | skipped
    original_assertion: dict = field(default_factory=dict)
    corrected_assertion: dict = None    # 只有 modified 时存在
    error_type: str = ""                # reject / modify 必填
    review_comment: str = ""
    reviewed_by: str = "human"
    reviewed_at: str = ""
    review_started_at: str = ""
    review_finished_at: str = ""
    review_duration_seconds: float = 0.0
    source_doc_id: str = ""
    source_chunk_id: str = ""
    schema_version: str = ""
    review_version: str = "v0.2"
    test_only: bool = False

    def to_dict(self):
        return asdict(self)


@dataclass
class SchemaExtensionProposal:
    """Schema v1 可能缺关系的提案（不直接改 schema_v1.json，待统一决定是否升级 v1.1）。"""
    proposal_id: str = ""
    source_assertion_id: str = ""
    source_text: str = ""
    missing_semantic: str = ""
    suggested_entity_or_relation: str = ""
    reason: str = ""
    review_id: str = ""
    status: str = "pending"
    created_at: str = ""

    def to_dict(self):
        return asdict(self)
