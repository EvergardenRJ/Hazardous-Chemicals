# -*- coding: utf-8 -*-
"""Definer：把开放谓词 surface 映射到 schema 关系（rule 词典 + 类型消歧 + LLM 兜底）。

方向(direction)在这里确定性推导：若 subject/object 类型落在关系 domain/range 则为
TEXT_AS_IS；若反了则为 SCHEMA_INVERTED。AssertionBuilder 会再次用 domain/range 校验，
保证最终三元组方向正确（section 十六 要求）。
"""
from dataclasses import dataclass, asdict

from core.kg.schema_manager import SchemaManager

# 谓词 -> 候选关系 id 列表（含歧义候选，稍后按 subject/object 类型消歧）
PREDICATE_MAP = {
    # 因果
    "导致": ["direct_cause", "indirect_cause", "leads_to"],
    "引发": ["direct_cause", "indirect_cause", "leads_to"],
    "造成": ["direct_cause", "indirect_cause", "leads_to"],
    "引起": ["direct_cause", "indirect_cause", "leads_to"],
    "直接原因": ["direct_cause"],
    "间接原因": ["indirect_cause"],
    # 涉及 / 发生
    "涉及": ["involves_chemical", "involves_equipment", "involves_process"],
    "发生于": ["occurred_in", "occurred_at"],
    "发生在": ["occurred_in", "occurred_at"],
    # 违规
    "违反": ["violates"],
    "未执行": ["violates"],
    "未落实": ["violates"],
    "未制定": ["violates"],
    "未设置": ["violates"],
    "不符合": ["violates"],
    "违章": ["violates"],
    # 存储 / 使用 / 位置
    "储存": ["contains"],
    "盛装": ["contains"],
    "输送": ["contains"],
    "使用": ["used_in", "handles"],
    "用于": ["used_in"],
    "位于": ["located_at"],
    "拥有": ["has_equipment"],
    "设有": ["has_equipment"],
    "属于": ["belongs_to_class"],
    # 权威 / 引用
    "发布": ["issued_by"],
    "制定": ["issued_by"],
    "监管": ["regulates"],
    "规范": ["governs"],
    "适用于": ["applies_to"],
    "依据": ["based_on"],
    "出自": ["derived_from"],
    "来源于": ["derived_from"],
    "引用": ["references"],
    "代替": ["replaces"],
    "定义": ["defines"],
    "包含": ["has_clause", "contains"],
    # 措施 / 责任
    "采取": ["has_measure"],
    "负责": ["liability_of"],
    "承担责任": ["liability_of"],
    "负有责任": ["liability_of"],
}


@dataclass
class DefineResult:
    relation_id: str = ""              # 开放关系短语自身的 id（来自 relation_phrases）
    predicate_surface: str = ""
    definition: str = ""
    schema_relation: str = ""          # 映射到的 schema 关系 id；未命中为 ""
    direction: str = "TEXT_AS_IS"      # TEXT_AS_IS | SCHEMA_INVERTED
    confidence: float = 0.0
    status: str = "unresolved"         # mapped | unresolved
    subject_mention_id: str = ""
    object_mention_id: str = ""

    def to_dict(self):
        return asdict(self)


class Definer:
    def __init__(self, schema_manager=None, use_llm=False, llm=None):
        self.sm = schema_manager or SchemaManager()
        self.use_llm = use_llm
        self.llm = llm  # 惰性加载，避免无谓占用显存

    # ------------------------------------------------------------------ #
    def define(self, relation_phrases, schema_context=None, entity_mentions=None, section=""):
        """对每条开放关系短语返回 DefineResult。entity_mentions 用于类型消歧。"""
        type_map = self._build_type_map(entity_mentions)
        results = []
        for rp in relation_phrases or []:
            if not isinstance(rp, dict):
                continue
            phrase_id = str(rp.get("relation_id", "") or "")
            surface = str(rp.get("predicate_surface", "") or "").strip()
            sub_mid = rp.get("subject_mention_id", "")
            obj_mid = rp.get("object_mention_id", "")
            sub_type = type_map.get(sub_mid, "")
            obj_type = type_map.get(obj_mid, "")
            results.append(self._define_one(phrase_id, surface, sub_type, obj_type,
                                            sub_mid, obj_mid, section))
        return results

    # ------------------------------------------------------------------ #
    def _build_type_map(self, entity_mentions):
        type_map = {}
        for m in entity_mentions or []:
            if not isinstance(m, dict):
                continue
            mid = m.get("mention_id")
            hint = m.get("type_hint", "")
            norm = self.sm.normalize_entity_type(hint)
            if mid:
                type_map[str(mid)] = norm or str(hint or "").strip()
        return type_map

    def _define_one(self, phrase_id, surface, sub_type, obj_type, sub_mid, obj_mid, section):
        norm = surface.strip()
        candidates = PREDICATE_MAP.get(norm)
        resolved = None
        definition = ""

        if candidates:
            resolved = self._disambiguate(candidates, sub_type, obj_type, section)
            if resolved:
                definition = f"谓词「{norm}」按类型消歧映射到 {resolved}"

        # LLM 兜底（仅当开启且规则未命中）
        if resolved is None and self.use_llm:
            resolved = self._llm_map(norm, sub_type, obj_type)
            if resolved:
                definition = f"谓词「{norm}」经 LLM 映射到 {resolved}"

        if resolved is None:
            return DefineResult(
                relation_id=phrase_id,
                predicate_surface=norm,
                schema_relation="",
                direction="TEXT_AS_IS",
                confidence=0.0,
                status="unresolved",
                subject_mention_id=sub_mid,
                object_mention_id=obj_mid,
            )

        direction = self._resolve_direction(resolved, sub_type, obj_type)
        return DefineResult(
            relation_id=phrase_id,
            predicate_surface=norm,
            definition=definition,
            schema_relation=resolved,
            direction=direction,
            confidence=0.85,
            status="mapped",
            subject_mention_id=sub_mid,
            object_mention_id=obj_mid,
        )

    # ------------------------------------------------------------------ #
    def _disambiguate(self, candidates, sub_type, obj_type, section):
        if len(candidates) == 1:
            return candidates[0]

        # involves_* 按 object 类型
        if "involves_chemical" in candidates:
            if obj_type == "chemical":
                return "involves_chemical"
            if obj_type == "equipment":
                return "involves_equipment"
            if obj_type == "process":
                return "involves_process"
            return None

        # occurred_* 按 object 类型
        if "occurred_in" in candidates:
            if obj_type == "enterprise":
                return "occurred_in"
            if obj_type == "site":
                return "occurred_at"
            return None

        # 因果：direct/indirect/leads_to
        if "direct_cause" in candidates:
            if section and "间接" in section:
                return "indirect_cause"
            if sub_type == "causal_factor" and obj_type == "causal_factor":
                return "leads_to"
            return "direct_cause"

        # contains vs has_clause
        if "has_clause" in candidates:
            return "has_clause" if obj_type in ("clause", "requirement") else "contains"

        # used_in vs handles
        if "used_in" in candidates:
            return "handles" if obj_type == "chemical" else "used_in"

        # 其余：取第一个
        return candidates[0]

    def _resolve_direction(self, schema_relation, sub_type, obj_type):
        """确定性推导方向：TEXT_AS_IS / SCHEMA_INVERTED。"""
        rel = self.sm.get_relation(schema_relation)
        if rel is None:
            return "TEXT_AS_IS"
        domain = self.sm.as_list(rel.get("domain"))
        rng = self.sm.as_list(rel.get("range"))
        s = self.sm.normalize_entity_type(sub_type)
        o = self.sm.normalize_entity_type(obj_type)
        if s and o:
            if s in domain and o in rng:
                return "TEXT_AS_IS"
            if o in domain and s in rng:
                return "SCHEMA_INVERTED"
        return "TEXT_AS_IS"

    # ------------------------------------------------------------------ #
    def _llm_map(self, surface, sub_type, obj_type):
        """LLM 兜底映射（未开启 use_llm 时不会被调用）。"""
        if self.llm is None:
            try:
                from core.llm import QwenLLM
                self.llm = QwenLLM()
            except Exception:
                return None
        rels = ", ".join(self.sm.get_relation_types())
        prompt = (
            f"请把中文谓词「{surface}」映射到下列 schema 关系之一（主体类型 {sub_type}，"
            f"客体类型 {obj_type}）。只输出关系 id；若无合适关系，只输出 NONE。\n"
            f"候选关系: {rels}\n"
        )
        try:
            answer = self.llm.generate(prompt, max_new_tokens=32, temperature=0.0).strip()
        except Exception:
            return None
        if answer and answer.upper() != "NONE" and self.sm.validate_relation(answer):
            return answer
        return None
