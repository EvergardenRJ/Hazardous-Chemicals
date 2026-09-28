# -*- coding: utf-8 -*-
"""Extractor：调用 QwenLLM 做半开放抽取，输出 ExtractionDraft。

含稳健 JSON 解析器 parse_llm_json（json.loads -> 去代码围栏 -> 括号扫描取首个完整对象）。

v0.2：case_context 非空时，把历史成功/失败案例上下文注入 prompt（二十二）；空时与 v0.1 完全一致。
"""
import json
import re
from dataclasses import dataclass, field, asdict

from core.llm import QwenLLM
from core.kg.schema_manager import SchemaManager
from core.kg.case_retriever import format_success_cases, format_failure_cases

EXTRACTION_SYSTEM_PROMPT = (
    "你是一名化工安全知识图谱抽取器。你只输出一个合法的 JSON 对象，"
    "不输出任何解释性文字、不输出 Markdown 代码围栏以外的内容，"
    "绝不编造文本中不存在的信息、实体、条款或数值。"
)


# --------------------------------------------------------------------------- #
# JSON 稳健解析
# --------------------------------------------------------------------------- #
def _extract_json_object(text):
    """括号配对扫描，返回第一个完整 JSON 对象；失败返回 None。"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    return None
    return None


def parse_llm_json(raw):
    """返回 (obj, method)，method ∈ {json.loads, code_fence, object_scan, failed}。"""
    if raw is None:
        return None, "failed"
    raw = raw.strip()

    try:
        return json.loads(raw), "json.loads"
    except Exception:
        pass

    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        inner = fence.group(1).strip()
        try:
            return json.loads(inner), "code_fence"
        except Exception:
            pass
        obj = _extract_json_object(inner)
        if obj is not None:
            return obj, "object_scan"

    obj = _extract_json_object(raw)
    if obj is not None:
        return obj, "object_scan"

    return None, "failed"


# --------------------------------------------------------------------------- #
# ExtractionDraft
# --------------------------------------------------------------------------- #
@dataclass
class ExtractionDraft:
    status: str = "ok"  # ok | extraction_failed
    entity_mentions: list = field(default_factory=list)
    relation_phrases: list = field(default_factory=list)
    attribute_mentions: list = field(default_factory=list)
    requirement_candidates: list = field(default_factory=list)
    clause_mentions: list = field(default_factory=list)
    raw: str = ""
    parse_method: str = ""
    retry_used: bool = False

    def to_dict(self):
        return asdict(self)


# --------------------------------------------------------------------------- #
# Extractor
# --------------------------------------------------------------------------- #
class Extractor:
    def __init__(self, llm=None, schema_manager=None):
        self.llm = llm or QwenLLM()
        self.sm = schema_manager or SchemaManager()

    # ------------------------------------------------------------------ #
    def extract(self, text, doc_type="unknown", rule_annotations=None,
                schema_context=None, case_context=None):
        """返回 ExtractionDraft。失败时 retry 一次，仍失败则 status=extraction_failed。"""
        prompt = self._build_prompt(text, doc_type, rule_annotations, schema_context, case_context)
        raw = self.llm.generate(
            prompt, system_prompt=EXTRACTION_SYSTEM_PROMPT,
            max_new_tokens=2048, temperature=0.2,
        )
        obj, method = parse_llm_json(raw)

        retry_used = False
        if obj is None:
            retry_used = True
            raw = self.llm.generate(
                prompt, system_prompt=EXTRACTION_SYSTEM_PROMPT,
                max_new_tokens=2048, temperature=0.2,
            )
            obj, method = parse_llm_json(raw)

        if obj is None:
            return ExtractionDraft(status="extraction_failed", raw=raw,
                                   parse_method="failed", retry_used=retry_used)

        return ExtractionDraft(
            status="ok",
            entity_mentions=obj.get("entity_mentions", []) or [],
            relation_phrases=obj.get("relation_phrases", []) or [],
            attribute_mentions=obj.get("attribute_mentions", []) or [],
            requirement_candidates=obj.get("requirement_candidates", []) or [],
            clause_mentions=obj.get("clause_mentions", []) or [],
            raw=raw,
            parse_method=method,
            retry_used=retry_used,
        )

    # ------------------------------------------------------------------ #
    def _entity_type_hints(self):
        lines = []
        for eid in self.sm.get_entity_types():
            e = self.sm.get_entity(eid)
            lines.append(f"- {eid} ({e.get('name', '')}): {e.get('description', '')}")
        return "\n".join(lines)

    def _relation_type_hints(self):
        lines = []
        for rid in self.sm.get_relation_types():
            r = self.sm.get_relation(rid)
            domain = "/".join(self.sm.as_list(r.get("domain")))
            rng = "/".join(self.sm.as_list(r.get("range")))
            lines.append(f"- {rid} ({r.get('name', '')}) [{domain} -> {rng}]: {r.get('description', '')}")
        return "\n".join(lines)

    def _schema_context_str(self, schema_context):
        if not schema_context:
            return "（无）"
        ents = [f"{e['name']}({e.get('name_zh','')})" for e in schema_context.get("entities", [])]
        rels = [f"{r['name']}({r.get('name_zh','')})" for r in schema_context.get("relations", [])]
        return "实体候选: " + ", ".join(ents) + "\n关系候选: " + ", ".join(rels)

    def _rule_annotations_str(self, rule_annotations):
        if rule_annotations is None:
            return "（无）"
        return json.dumps(rule_annotations.to_dict(), ensure_ascii=False)

    def _case_context_str(self, case_context):
        """把检索到的历史案例格式化为 prompt 文本；空则返回空串（与 v0.1 一致）。"""
        if not case_context:
            return ""
        success = case_context.get("success_cases") or []
        failure = case_context.get("failure_cases") or []
        if not success and not failure:
            return ""
        parts = []
        if success:
            parts.append(format_success_cases(success))
        if failure:
            parts.append(format_failure_cases(failure))
        return "\n\n".join(parts)

    def _build_prompt(self, text, doc_type, rule_annotations, schema_context, case_context=None):
        entity_hints = self._entity_type_hints()
        relation_hints = self._relation_type_hints()
        schema_str = self._schema_context_str(schema_context)
        rule_str = self._rule_annotations_str(rule_annotations)
        case_str = self._case_context_str(case_context)

        if doc_type == "accident":
            task = self._ACCIDENT_TASK
        else:
            task = self._STANDARD_TASK

        case_block = ""
        if case_str:
            case_block = ("\n【历史案例上下文】（人工审核过的成功/失败经验；失败为负例，不要照抄）\n"
                          + case_str + "\n")

        return f"""{task}

【可选实体类型】(type_hint 只从下列 id 取，仅作类型提示)
{entity_hints}

【Schema 关系参考】(仅语义参考，不要强行映射，predicate_surface 保留原文谓词)
{relation_hints}

【检索到的 Schema 上下文】
{schema_str}

【规则标注】(高置信度信息，可直接采信)
{rule_str}
{case_block}
【输入文本】
{text}

【输出】只输出一个严格 JSON 对象（无内容时用空数组），不要输出任何解释。"""

    _ACCIDENT_TASK = """【任务】从事故报告文本片段做半开放抽取：识别实体提及与开放关系短语。
【约束】
- 只依据给定文本，不要编造。
- 不要做实体归一化(canonicalization)，不要生成 canonical_id。
- physical_state 仅在文本明确可判断时填 liquid/gas/solid，否则 null。
- entity_mentions 覆盖：企业、化学品、设备、工艺、地点、事故致因(causal_factor)、事故后果、措施；致因(causal_factor)应包含"压力""超压""减薄""断裂""泄漏""中毒"等状态/事件。
- relation_phrases 只抽取真实语义关系谓词（动词/动宾，如"导致""引发""造成""引起""涉及""发生于""违反""储存""使用"），不要抽取介词（"在""于""对"）或名词性描述（"承载能力""存在…情况"）作为谓词。
- 每个关系的主语(subject_mention_id)/宾语(object_mention_id)必须是两个不同的有意义实体；不要自环；因果谓词（导致/造成/引起）的主语应是致因(causal_factor)或事件，不要用化学品/设备充当致因。
输出 JSON 字段：
{
  "entity_mentions": [{"mention_id":"m1","surface":"原文实体","type_hint":"chemical|equipment|enterprise|process|site|causal_factor|accident|measure|hazard_class","context":"所在短句","physical_state":null}],
  "relation_phrases": [{"relation_id":"r1","subject_mention_id":"m1","predicate_surface":"导致","object_mention_id":"m2","evidence_quote":"原文证据"}],
  "attribute_mentions": [{"mention_id":"a1","subject_mention_id":"m1","property":"death_count","value":"3","evidence_quote":"原文证据"}]
}"""

    _STANDARD_TASK = """【任务】从标准/法规文本片段中抽取条款(Clause)与安全要求(Requirement)候选，以及实体提及。
【约束】
- 只依据给定文本，不要编造。
- 不要生成 Requirement ID（后续阶段生成）。
- 每个要求识别 modality/subject/action/object/quantitative_constraint。
- subject/object 若对应实体，用 entity_mentions 的 mention_id 关联（subject_mention_id/object_mention_id）；无对应则留 null。
- quantitative_constraint 保留比较词+数值+单位（如"<1.20kg/L""不超过80%"）。
输出 JSON 字段：
{
  "entity_mentions": [{"mention_id":"m1","surface":"液氯贮槽","type_hint":"equipment","context":"...","physical_state":null}],
  "clause_mentions": [{"clause_id":"c1","clause_number":"6.3.1","text":"...条款原文..."}],
  "requirement_candidates": [{"requirement_id":"req1","clause_id":"c1","modality":"应","subject":"液氯贮槽","subject_mention_id":"m1","action":"接受","object":"液氯","object_mention_id":"m2","condition":null,"quantitative_constraint":"<1.20kg/L","evidence_quote":"...原文..."}],
  "relation_phrases": [],
  "attribute_mentions": []
}"""
