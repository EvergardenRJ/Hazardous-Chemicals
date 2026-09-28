# -*- coding: utf-8 -*-
"""Canonicalizer：实体归一化（规则 + 已有简单词典 + LLM 兜底，三层）。

v0.1 不做跨文档实体合并：provisional 实体 id 为 {type}::<normalized>::<doc_id>，
仅在本文档范围内稳定；化学/企业命中词典或全称规则时标记 resolved（canonical_id 不带 doc_id）。
"""
import re
from dataclasses import dataclass, asdict

from core.kg.schema_manager import SchemaManager

# 化学品词典：归一化 surface -> (canonical_name, physical_state)
CHEMICAL_DICT = {
    "液氯": ("氯", "liquid"),
    "氯气": ("氯", "gas"),
    "氯": ("氯", None),
    "液氨": ("氨", "liquid"),
    "氨气": ("氨", "gas"),
    "氨": ("氨", "gas"),
    "硫化氢": ("硫化氢", "gas"),
    "一氧化碳": ("一氧化碳", "gas"),
    "二氧化碳": ("二氧化碳", "gas"),
    "苯": ("苯", "liquid"),
    "甲醇": ("甲醇", "liquid"),
    "乙醇": ("乙醇", "liquid"),
    "甲苯": ("甲苯", "liquid"),
    "二甲苯": ("二甲苯", "liquid"),
    "硫酸": ("硫酸", "liquid"),
    "硝酸": ("硝酸", "liquid"),
    "盐酸": ("盐酸", "liquid"),
    "烧碱": ("氢氧化钠", "solid"),
    "氢氧化钠": ("氢氧化钠", "solid"),
    "保险粉": ("连二亚硫酸钠", "solid"),
    "连二亚硫酸钠": ("连二亚硫酸钠", "solid"),
    "水银": ("汞", "liquid"),
    "汞": ("汞", "liquid"),
    "煤气": ("煤气", "gas"),
    "液化石油气": ("液化石油气", "gas"),
    "天然气": ("天然气", "gas"),
    "次氯酸钠": ("次氯酸钠", "liquid"),
    "甲醛": ("甲醛", "liquid"),
    "乙炔": ("乙炔", "gas"),
    "氢气": ("氢气", "gas"),
    "氧气": ("氧气", "gas"),
    "氮气": ("氮气", "gas"),
    "氟化氢": ("氟化氢", "gas"),
    "氯化氢": ("氯化氢", "gas"),
    "氰化氢": ("氰化氢", "gas"),
    "氰化钠": ("氰化钠", "solid"),
    "硝基苯": ("硝基苯", "liquid"),
    "苯胺": ("苯胺", "liquid"),
    "四氟乙烯": ("四氟乙烯", "gas"),
}

# 标准代号（从 surface 提取 code）
RE_STD_CODE = re.compile(
    r"(?:GB|AQ|DB|HG|TSG|SY|JT|NB|SN|YS|JB|JGJ|CJJ|GA|WS)\s*[/T]?\s*\d+(?:[.\-—–]\d+)*(?:[-—–]\d{2,4})?"
)


@dataclass
class CanonicalResult:
    mention_id: str = ""
    surface: str = ""
    type_hint: str = ""
    entity_type: str = ""            # 归一化后的 schema 实体 id
    canonical_name: str = ""
    canonical_id: str = ""
    physical_state: str = None       # chemical 专用：liquid/gas/solid/None
    canonical_status: str = "provisional"  # resolved | provisional
    match_level: str = "provisional"  # dictionary | rule | provisional
    confidence: float = 0.5

    def to_dict(self):
        return asdict(self)


class Canonicalizer:
    def __init__(self, schema_manager=None, use_llm=False):
        self.sm = schema_manager or SchemaManager()
        self.use_llm = use_llm

    # ------------------------------------------------------------------ #
    def canonicalize(self, extraction_draft, chunk_meta=None, doc_type="unknown"):
        """对 entity_mentions 逐条归一化，返回 CanonicalResult 列表。"""
        chunk_meta = chunk_meta or {}
        doc_id = str(chunk_meta.get("doc_id", "") or "")
        results = []
        for m in extraction_draft.entity_mentions or []:
            if not isinstance(m, dict):
                continue
            results.append(self._canonicalize_one(m, doc_id))
        return results

    # ------------------------------------------------------------------ #
    def _canonicalize_one(self, mention, doc_id):
        mid = str(mention.get("mention_id", "") or "")
        surface = self._normalize(str(mention.get("surface", "") or ""))
        hint = str(mention.get("type_hint", "") or "")
        etype = self.sm.normalize_entity_type(hint) or hint
        physical_state = mention.get("physical_state")

        result = CanonicalResult(
            mention_id=mid, surface=surface, type_hint=hint, entity_type=etype,
            canonical_name=surface, canonical_id="", physical_state=physical_state,
        )

        if etype == "chemical":
            self._canonicalize_chemical(result, surface, physical_state)
        elif etype == "enterprise":
            self._canonicalize_enterprise(result, surface, doc_id)
        elif etype == "standard":
            self._canonicalize_standard(result, surface, doc_id)
        elif etype in ("regulation", "regulator"):
            self._canonicalize_org(result, surface, doc_id)
        else:
            # equipment / process / site / causal_factor / measure / accident /
            # hazard_class / major_hazard_source / clause / requirement 等：provisional
            result.canonical_name = surface
            result.canonical_id = f"{etype}::{surface}::{doc_id}" if surface else ""
            result.match_level = "provisional"
            result.confidence = 0.6

        # LLM 兜底（仅当开启且仍 provisional）
        if result.canonical_status == "provisional" and self.use_llm:
            self._llm_fallback(result, surface, etype)

        return result

    # ------------------------------------------------------------------ #
    def _canonicalize_chemical(self, result, surface, physical_state):
        hit = CHEMICAL_DICT.get(surface)
        if hit:
            canonical_name, state = hit
            result.canonical_name = canonical_name
            result.canonical_id = f"chemical::{canonical_name}"
            result.physical_state = physical_state or state
            result.canonical_status = "resolved"
            result.match_level = "dictionary"
            result.confidence = 0.95
        else:
            state = physical_state or self._infer_state(surface)
            result.canonical_name = surface
            result.canonical_id = f"chemical::{surface}"
            result.physical_state = state
            result.canonical_status = "provisional"
            result.match_level = "provisional"
            result.confidence = 0.5

    def _canonicalize_enterprise(self, result, surface, doc_id):
        # 全称（含 公司/集团/厂/有限公司）视为 resolved；否则 provisional
        if re.search(r"(公司|集团|厂|有限|股份|合作社|中心)", surface):
            result.canonical_name = surface
            result.canonical_id = f"enterprise::{surface}"
            result.canonical_status = "resolved"
            result.match_level = "rule"
            result.confidence = 0.9
        else:
            result.canonical_name = surface
            result.canonical_id = f"enterprise::{surface}::{doc_id}"
            result.canonical_status = "provisional"
            result.match_level = "provisional"
            result.confidence = 0.5

    def _canonicalize_standard(self, result, surface, doc_id):
        code = RE_STD_CODE.search(surface)
        if code:
            result.canonical_name = code.group(0)
            result.canonical_id = f"standard::{code.group(0)}"
            result.canonical_status = "resolved"
            result.match_level = "rule"
            result.confidence = 0.9
        else:
            result.canonical_name = surface
            result.canonical_id = f"standard::{surface}::{doc_id}"
            result.canonical_status = "provisional"
            result.match_level = "provisional"
            result.confidence = 0.5

    def _canonicalize_org(self, result, surface, doc_id):
        # 法规/监管机构：有机构后缀视为 resolved
        if re.search(r"(委员会|管理局|人民政府|厅|局|部|院)", surface):
            result.canonical_name = surface
            result.canonical_id = f"{result.entity_type}::{surface}"
            result.canonical_status = "resolved"
            result.match_level = "rule"
            result.confidence = 0.9
        else:
            result.canonical_name = surface
            result.canonical_id = f"{result.entity_type}::{surface}::{doc_id}"
            result.canonical_status = "provisional"
            result.match_level = "provisional"
            result.confidence = 0.5

    # ------------------------------------------------------------------ #
    @staticmethod
    def _infer_state(surface):
        if "液" in surface:
            return "liquid"
        if "气" in surface or "煤气" in surface or "天然气" in surface:
            return "gas"
        return None

    @staticmethod
    def _normalize(surface):
        s = str(surface or "").strip()
        s = s.replace("（", "(").replace("）", ")").replace("，", ",").replace("．", ".")
        s = re.sub(r"\s+", "", s)
        return s

    # ------------------------------------------------------------------ #
    def _llm_fallback(self, result, surface, etype):
        """LLM 兜底（未开启 use_llm 时不会被调用）。占位实现：尝试补全化学 canonical name。"""
        if etype != "chemical":
            return
        try:
            from core.llm import QwenLLM
            llm = QwenLLM()
            prompt = (
                f"给出化学品「{surface}」的规范中文名称（只输出名称，无把握则原样输出）。"
            )
            name = llm.generate(prompt, max_new_tokens=32, temperature=0.0).strip()
        except Exception:
            return
        if name and name != surface:
            result.canonical_name = name
            result.canonical_id = f"chemical::{name}"
            result.match_level = "rule"  # LLM 归一
