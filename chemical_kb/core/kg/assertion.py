# -*- coding: utf-8 -*-
"""Assertion Builder：把抽取/定义/归一化的结果组装成 CandidateAssertion 三元组。

方向确定性保证：每个关系三元组的方向都经 schema domain/range 二次校验，
subject/object 若反了则交换（section 十六：不能方向错误）。
文档锚点实体（Accident/Standard/Regulation）不作为独立断言，而是作为三元组的
subject/object 引用隐含表达。
"""
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime

from core.kg.schema_manager import SchemaManager

# 事故 chunk 中，实体类型 -> 从 Accident 出发的确定性结构关系
ACCIDENT_STRUCTURAL = {
    "chemical": "involves_chemical",
    "equipment": "involves_equipment",
    "process": "involves_process",
    "enterprise": "occurred_in",
    "site": "occurred_at",
    "measure": "has_measure",
    # causal_factor 单独处理（direct_cause / indirect_cause，取决于 section）
}

# applies_to 允许的客体类型（与 schema_v1.json 一致）
APPLIES_TO_RANGE = {"chemical", "equipment", "process", "site",
                    "major_hazard_source", "enterprise"}

# 事故计数类属性（Accident 的合法属性，挂 literal 断言）
ACCIDENT_COUNT_ATTRS = ("death_count", "severe_injury_count", "minor_injury_count",
                        "missing_count", "injury_count")


@dataclass
class CandidateAssertion:
    assertion_id: str = ""
    subject_id: str = ""
    subject_type: str = ""
    subject_label: str = ""
    predicate: str = ""
    object_id: str = ""
    object_type: str = ""
    object_label: str = ""
    object_kind: str = "entity"        # entity | literal
    source_doc_id: str = ""
    source_chunk_id: str = ""
    source_text_quote: str = ""
    source_type: str = ""
    page_start: str = ""
    page_end: str = ""
    section: str = ""
    schema_version: str = ""
    extraction_method: str = "llm"
    assertion_type: str = "explicit"
    confidence: float = 0.5
    review_status: str = "pending"
    validation_status: str = ""        # "" | passed | failed（validator 回填）
    validation_errors: list = field(default_factory=list)
    created_at: str = ""
    valid_from: str = ""
    valid_to: str = ""
    recorded_at: str = ""
    superseded_at: str = ""

    def to_dict(self):
        return asdict(self)


class AssertionBuilder:
    def __init__(self, schema_manager=None):
        self.sm = schema_manager or SchemaManager()

    # ------------------------------------------------------------------ #
    def build(self, extraction_draft, define_results, canonical_results,
              chunk_meta, doc_type="unknown", rule_annotations=None):
        """返回 (assertions, unresolved_relations)。"""
        meta = chunk_meta or {}
        doc_id = str(meta.get("doc_id", "") or "")
        chunk_id = str(meta.get("chunk_id", "") or "")
        title = str(meta.get("title", "") or "")
        code = str(meta.get("code", "") or "")
        source_type = self._source_type(doc_type)
        page_start = self._page(meta, "page_start", "page")
        page_end = self._page(meta, "page_end")
        section = str(meta.get("section", "") or "")
        schema_version = self.sm.version

        mention_map = {c.mention_id: c for c in canonical_results if c.mention_id}
        define_map = {d.relation_id: d for d in define_results if d.relation_id}

        self._counter = 0
        self._seen = set()
        self._assertions = []

        base = dict(
            source_doc_id=doc_id, source_chunk_id=chunk_id, source_type=source_type,
            page_start=page_start, page_end=page_end, section=section,
            schema_version=schema_version, created_at=datetime.now().isoformat(timespec="seconds"),
            recorded_at=datetime.now().isoformat(timespec="seconds"),
            valid_from=str(meta.get("valid_from", "") or ""),
            valid_to=str(meta.get("valid_to", "") or ""),
        )

        unresolved = []
        if doc_type == "accident":
            self._build_accident(extraction_draft, mention_map, define_map, base,
                                 unresolved, title, doc_id, section, rule_annotations)
        else:
            self._build_standard(extraction_draft, mention_map, define_map, base,
                                 unresolved, doc_id, code, title)

        return self._assertions, unresolved

    # ------------------------------------------------------------------ #
    # 事故文档
    # ------------------------------------------------------------------ #
    def _build_accident(self, draft, mention_map, define_map, base, unresolved,
                        title, doc_id, section, rule_annotations):
        accident_id = f"accident::{doc_id}"
        indirect = "间接" in section

        # 结构性关系：Accident -> 实体
        for m in draft.entity_mentions or []:
            c = mention_map.get(str(m.get("mention_id", "")))
            if c is None or not c.canonical_id or c.entity_type == "accident":
                continue
            if c.entity_type == "causal_factor":
                pred = "indirect_cause" if indirect else "direct_cause"
                self._add(base, accident_id, "accident", title,
                          pred, c.canonical_id, c.entity_type, c.canonical_name, "entity",
                          quote=m.get("context", "") or c.surface)
            elif c.entity_type in ACCIDENT_STRUCTURAL:
                self._add(base, accident_id, "accident", title,
                          ACCIDENT_STRUCTURAL[c.entity_type],
                          c.canonical_id, c.entity_type, c.canonical_name, "entity",
                          quote=m.get("context", "") or c.surface)

        # 事故计数属性（优先规则标注，高置信）
        self._build_accident_attributes(base, accident_id, title, draft, rule_annotations)

        # 开放关系短语 -> 确定性方向三元组
        self._build_open_relations(draft, mention_map, define_map, base, unresolved)

    def _build_accident_attributes(self, base, accident_id, title, draft, rule_annotations):
        # 规则标注的计数（确定性、高置信）
        if rule_annotations is not None:
            rd = rule_annotations.to_dict()
            for prop in ACCIDENT_COUNT_ATTRS:
                val = rd.get(prop)
                if val is not None and str(val).strip() != "":
                    self._add(base, accident_id, "accident", title,
                              prop, str(val), "literal", str(val), "literal",
                              quote=f"{prop}={val}", extraction_method="rule")
        # LLM attribute_mentions（若规则未覆盖）
        for am in draft.attribute_mentions or []:
            if not isinstance(am, dict):
                continue
            prop = str(am.get("property", "") or "").strip()
            val = am.get("value")
            if prop in ACCIDENT_COUNT_ATTRS and val is not None:
                self._add(base, accident_id, "accident", title,
                          prop, str(val), "literal", str(val), "literal",
                          quote=am.get("evidence_quote", "") or str(val),
                          extraction_method="llm")

    # ------------------------------------------------------------------ #
    # 标准 / 法规文档
    # ------------------------------------------------------------------ #
    def _build_standard(self, draft, mention_map, define_map, base, unresolved,
                        doc_id, code, title):
        anchor_type = "standard" if code else "regulation"
        anchor_id = f"{anchor_type}::{self._norm_code(code)}" if code else f"{anchor_type}::{doc_id}"
        anchor_label = code or title or doc_id

        clause_map = {}  # clause_id(str) -> (clause_canonical_id, clause_number, clause_text)
        for cm in draft.clause_mentions or []:
            if not isinstance(cm, dict):
                continue
            cid = str(cm.get("clause_id", "") or "")
            cnum = str(cm.get("clause_number", "") or "").strip()
            ctext = str(cm.get("text", "") or "").strip()
            clause_entity_id = f"clause::{doc_id}::{cnum}" if cnum else f"clause::{doc_id}::{cid}"
            clause_map[cid] = (clause_entity_id, cnum, ctext)
            # Standard/Regulation -[HAS_CLAUSE]-> Clause
            self._add(base, anchor_id, anchor_type, anchor_label,
                      "has_clause", clause_entity_id, "clause", cnum or ctext,
                      "entity", quote=ctext or cnum, extraction_method="llm")
            # Clause 属性
            if cnum:
                self._add(base, clause_entity_id, "clause", cnum,
                          "clause_number", cnum, "literal", cnum, "literal",
                          quote=ctext or cnum, extraction_method="llm")
            if ctext:
                self._add(base, clause_entity_id, "clause", cnum or ctext,
                          "text", ctext, "literal", ctext, "literal",
                          quote=ctext, extraction_method="llm")

        # Requirement 候选
        req_index = 0
        for rc in draft.requirement_candidates or []:
            if not isinstance(rc, dict):
                continue
            req_index += 1
            clause_id = str(rc.get("clause_id", "") or "")
            cnum = str(rc.get("clause_number", "") or "")
            if not cnum and clause_id in clause_map:
                cnum = clause_map[clause_id][1]
            requirement_id = self._requirement_id(code or doc_id, cnum, req_index)
            req_entity_id = f"requirement::{requirement_id}"
            req_text = str(rc.get("evidence_quote", "") or "").strip()
            req_label = req_text[:40] or requirement_id

            # Requirement -[DERIVED_FROM]-> Clause
            if clause_id in clause_map:
                self._add(base, req_entity_id, "requirement", req_label,
                          "derived_from", clause_map[clause_id][0], "clause",
                          clause_map[clause_id][1], "entity",
                          quote=req_text, extraction_method="llm")

            # Requirement 属性断言（literal）
            self._add(base, req_entity_id, "requirement", req_label,
                      "requirement_id", requirement_id, "literal", requirement_id, "literal",
                      quote=req_text, extraction_method="rule")
            for prop in ("modality", "quantitative_constraint", "action", "subject",
                         "object", "condition", "text"):
                val = rc.get(prop)
                if val is None or str(val).strip() == "":
                    continue
                self._add(base, req_entity_id, "requirement", req_label,
                          prop, str(val).strip(), "literal", str(val).strip(), "literal",
                          quote=req_text or str(val), extraction_method="llm")

            # Requirement -[APPLIES_TO]-> subject/object 实体
            for mid_key, text_key in (("subject_mention_id", "subject"),
                                      ("object_mention_id", "object")):
                ent = self._resolve_apply_entity(rc, mid_key, text_key, mention_map)
                if ent is not None:
                    self._add(base, req_entity_id, "requirement", req_label,
                              "applies_to", ent.canonical_id, ent.entity_type,
                              ent.canonical_name, "entity",
                              quote=req_text, extraction_method="llm")

        # 开放关系短语
        self._build_open_relations(draft, mention_map, define_map, base, unresolved)

    # ------------------------------------------------------------------ #
    # 开放关系短语（事故/标准共用）
    # ------------------------------------------------------------------ #
    def _build_open_relations(self, draft, mention_map, define_map, base, unresolved):
        for rp in draft.relation_phrases or []:
            if not isinstance(rp, dict):
                continue
            d = define_map.get(str(rp.get("relation_id", "")))
            if d is None or d.status != "mapped" or not d.schema_relation:
                self._record_unresolved(unresolved, rp, mention_map)
                continue
            sub = mention_map.get(str(d.subject_mention_id or ""))
            obj = mention_map.get(str(d.object_mention_id or ""))
            if sub is None or obj is None or not sub.canonical_id or not obj.canonical_id:
                self._record_unresolved(unresolved, rp, mention_map)
                continue
            s, p, o = self._orient(sub, d.schema_relation, obj)
            self._add(base, s.canonical_id, s.entity_type, s.canonical_name,
                      p, o.canonical_id, o.entity_type, o.canonical_name, "entity",
                      quote=rp.get("evidence_quote", "") or rp.get("predicate_surface", ""),
                      extraction_method="llm+rule")

    def _resolve_apply_entity(self, rc, mid_key, text_key, mention_map):
        mid = str(rc.get(mid_key, "") or "")
        ent = mention_map.get(mid)
        if ent is not None and ent.entity_type in APPLIES_TO_RANGE:
            return ent
        text = self._normalize(str(rc.get(text_key, "") or ""))
        if not text:
            return None
        for c in mention_map.values():
            if c.entity_type in APPLIES_TO_RANGE and self._normalize(c.surface) == text:
                return c
        return None

    # ------------------------------------------------------------------ #
    # 方向确定性 + 去重 + 落盘到列表
    # ------------------------------------------------------------------ #
    def _orient(self, sub, pred, obj):
        rel = self.sm.get_relation(pred)
        if rel is None:
            return sub, pred, obj
        domain = self.sm.as_list(rel.get("domain"))
        rng = self.sm.as_list(rel.get("range"))
        s = self.sm.normalize_entity_type(sub.entity_type)
        o = self.sm.normalize_entity_type(obj.entity_type)
        if s in domain and o in rng:
            return sub, pred, obj
        if o in domain and s in rng:
            return obj, pred, sub
        return sub, pred, obj

    def _add(self, base, subject_id, subject_type, subject_label, predicate,
             object_id, object_type, object_label, object_kind,
             quote="", extraction_method="llm"):
        if object_kind == "entity" and not object_id:
            return
        key = (subject_id, predicate, object_id)
        if key in self._seen:
            return
        self._seen.add(key)
        self._counter += 1
        self._assertions.append(CandidateAssertion(
            assertion_id=f"{base['source_chunk_id']}_A{self._counter:03d}",
            subject_id=subject_id,
            subject_type=subject_type,
            subject_label=subject_label,
            predicate=predicate,
            object_id=object_id,
            object_type=object_type,
            object_label=object_label,
            object_kind=object_kind,
            source_doc_id=base["source_doc_id"],
            source_chunk_id=base["source_chunk_id"],
            source_text_quote=quote,
            source_type=base["source_type"],
            page_start=base["page_start"],
            page_end=base["page_end"],
            section=base["section"],
            schema_version=base["schema_version"],
            extraction_method=extraction_method,
            confidence=0.5,
            created_at=base["created_at"],
        ))

    def _record_unresolved(self, unresolved, rp, mention_map):
        sub = mention_map.get(str(rp.get("subject_mention_id", "")))
        obj = mention_map.get(str(rp.get("object_mention_id", "")))
        unresolved.append({
            "relation_id": rp.get("relation_id", ""),
            "predicate_surface": rp.get("predicate_surface", ""),
            "subject_surface": sub.surface if sub else str(rp.get("subject_mention_id", "")),
            "subject_type": sub.entity_type if sub else "",
            "object_surface": obj.surface if obj else str(rp.get("object_mention_id", "")),
            "object_type": obj.entity_type if obj else "",
            "evidence_quote": rp.get("evidence_quote", ""),
        })

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _source_type(doc_type):
        return {"accident": "事故", "standard": "标准", "regulation": "法规"}.get(doc_type, doc_type)

    @staticmethod
    def _page(meta, key, alt=None):
        v = meta.get(key)
        if v is None and alt:
            v = meta.get(alt)
        return str(v) if v is not None else ""

    @staticmethod
    def _norm_code(code):
        return re.sub(r"[\s/]+", "", str(code or "")).strip()

    @staticmethod
    def _requirement_id(doc_ref, clause_number, index):
        doc_part = re.sub(r"[\s/]+", "", str(doc_ref or ""))
        clause_part = str(clause_number or "").strip() or "NA"
        return f"{doc_part}_{clause_part}_R{index:02d}"

    @staticmethod
    def _normalize(s):
        return re.sub(r"\s+", "", str(s or "")).strip()
