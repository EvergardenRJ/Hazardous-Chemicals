# -*- coding: utf-8 -*-
"""Rule Preprocessor：纯规则抽取高置信度信息（不调 LLM）。

只负责“能可靠判断”的字段：section、死/伤/失踪人数、标准代号、CAS 号、日期、
条款编号、模态词、量值约束。避免复杂 NLP，规则只覆盖高置信度模式。
"""
import re
from dataclasses import dataclass, field, asdict


@dataclass
class RuleAnnotations:
    section: str = ""
    death_count: int = None
    injury_count: int = None
    severe_injury_count: int = None
    minor_injury_count: int = None
    missing_count: int = None
    standard_codes: list = field(default_factory=list)
    cas_numbers: list = field(default_factory=list)
    dates: list = field(default_factory=list)
    clause_numbers: list = field(default_factory=list)
    modalities: list = field(default_factory=list)
    quantitative_expressions: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class RuleExtractor:
    # ---- 死亡 / 受伤 / 失踪 ----
    RE_DEATH = re.compile(r"(\d+)\s*人\s*死亡|死亡\s*(\d+)\s*人|(\d+)\s*人\s*遇难")
    RE_SEVERE = re.compile(r"(\d+)\s*人\s*重伤|重伤\s*(\d+)\s*人")
    RE_MINOR = re.compile(r"(\d+)\s*人\s*轻伤|轻伤\s*(\d+)\s*人")
    RE_INJURY = re.compile(r"(\d+)\s*人\s*受伤|受伤\s*(\d+)\s*人")
    RE_MISSING = re.compile(r"(\d+)\s*人\s*失踪|失踪\s*(\d+)\s*人")

    # ---- 标准代号（GB/AQ/DB/HG/TSG 等 + 编号 + 可选年份）----
    RE_STD_CODE = re.compile(
        r"(?:GB|AQ|DB|HG|TSG|SY|JT|NB|SN|YS|JB|JGJ|CJJ|GA|WS)\s*[/T]?\s*\d+(?:[.\-—–]\d+)*(?:[-—–]\d{2,4})?"
    )

    # ---- CAS 号 ----
    RE_CAS = re.compile(r"(?:CAS|Cas|cas)\s*[号:：]?\s*(\d{2,7}[-]\d{2}[-]\d)")

    # ---- 日期 ----
    RE_DATE_CN = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
    RE_DATE_NUM = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")

    # ---- 条款编号：第X条 / 多级编号 6.3.1 / 二级编号 5.2（后接中文）----
    RE_CLAUSE_CN = re.compile(r"第\s*[一二三四五六七八九十百零〇两\d]+\s*条")
    RE_CLAUSE_MULTI = re.compile(r"(?<!\d)((?:\d+\.){2,}\d+)(?!\.?\d)")
    RE_CLAUSE_TWO = re.compile(r"(?<![\d.])(\d+\.\d+)(?=\s*[一-鿿])")

    # ---- 模态词 ----
    MODALITY_WORDS = ["应当", "必须", "不得", "禁止", "不应", "不宜", "宜", "可以", "应"]

    # ---- 量值约束：比较词 + 数值 + 单位 ----
    RE_QUANT = re.compile(
        r"(?:不应?|不得|禁止|必须|宜|应|应当)?\s*"
        r"(?:大于|小于|不超过|不低于|不大于|不小于|超过|等于)?\s*"
        r"\d+(?:\.\d+)?\s*"
        r"(?:[%％]|[a-zA-Z]+(?:/[a-zA-Z0-9]+)?)"
    )

    def extract(self, text, metadata=None, doc_type="unknown"):
        metadata = metadata or {}
        ann = RuleAnnotations(section=str(metadata.get("section", "") or ""))

        ann.death_count = self._first_int(self.RE_DEATH, text)
        ann.severe_injury_count = self._first_int(self.RE_SEVERE, text)
        ann.minor_injury_count = self._first_int(self.RE_MINOR, text)
        ann.injury_count = self._first_int(self.RE_INJURY, text)
        ann.missing_count = self._first_int(self.RE_MISSING, text)

        ann.standard_codes = self._dedupe(self.RE_STD_CODE.findall(text))
        ann.cas_numbers = self._dedupe(m.group(1) for m in self.RE_CAS.finditer(text))

        dates = []
        for m in self.RE_DATE_CN.finditer(text):
            dates.append(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
        for m in self.RE_DATE_NUM.finditer(text):
            dates.append(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
        ann.dates = self._dedupe(dates)

        clauses = self.RE_CLAUSE_CN.findall(text)
        clauses += self.RE_CLAUSE_MULTI.findall(text)
        clauses += self.RE_CLAUSE_TWO.findall(text)
        ann.clause_numbers = self._dedupe(c.strip() for c in clauses if c and c.strip())

        # 模态词：保留出现顺序去重
        seen = set()
        modalities = []
        for w in self.MODALITY_WORDS:
            if w in text and w not in seen:
                seen.add(w)
                modalities.append(w)
        ann.modalities = modalities

        ann.quantitative_expressions = self._dedupe(self.RE_QUANT.findall(text))
        return ann

    # ------------------------------------------------------------------ #
    @staticmethod
    def _first_int(regex, text):
        """取正则里第一个非空分组作为 int；无匹配返回 None。"""
        m = regex.search(text)
        if not m:
            return None
        for g in m.groups():
            if g is not None:
                return int(g)
        return None

    @staticmethod
    def _dedupe(items):
        out = []
        seen = set()
        for it in items:
            it = str(it).strip()
            if it and it not in seen:
                seen.add(it)
                out.append(it)
        return out
