# -*- coding: utf-8 -*-
"""Wiki Generator v0.5：Outline → 逐 Section 独立生成 → 逐 Section 校验 → 拼接。

不再一次性生成整篇长 Markdown，避免 token 截断 / 后半段缺失 / 结构损坏 / 乱码 / section 丢失。

每个 section 由 LLM 输出结构化 JSON（含 knowledge_blocks 标注 grounded / model_prior），
逐 section 校验（WikiQualityValidator），失败只重生成该 section，不整篇重跑。
"""
import re
import json

from core.rag import RAGSystem
from core.wiki_store import WikiStore
from core.wiki_quality_validator import WikiQualityValidator
from core.kg.extractor import parse_llm_json

# 17 个规范 section（v0.5 规格 1）。某实体不适合某节时，LLM 输出 applicable=false 跳过。
WIKI_SECTIONS = [
    "基本概述", "理化性质", "危险特性", "健康危害", "生产与使用", "储存要求",
    "运输与装卸", "设备设施与自动化控制", "个体防护", "泄漏应急", "火灾/爆炸处置",
    "急救", "典型事故经验", "常见事故原因", "防范与整改措施", "相关标准法规", "知识总结",
]

SECTION_QUERIES = {
    "基本概述": "是什么？有哪些基本定义、用途和基本信息？",
    "理化性质": "有哪些理化性质（外观、密度、沸点、熔点、溶解性、物态等）？",
    "危险特性": "有哪些危险特性（易燃、易爆、氧化、腐蚀、毒害等）？",
    "健康危害": "对人体健康有哪些危害（急性/慢性、中毒表现等）？",
    "生产与使用": "在生产和使用过程中有哪些安全要求？",
    "储存要求": "在储存过程中有哪些安全要求？",
    "运输与装卸": "在运输和装卸过程中有哪些安全要求？",
    "设备设施与自动化控制": "需要配置哪些安全设施和自动化控制措施？",
    "个体防护": "作业人员需要采取哪些个体防护措施？",
    "泄漏应急": "发生泄漏后有哪些应急处置措施？",
    "火灾/爆炸处置": "发生火灾或爆炸时如何处置？",
    "急救": "中毒或受伤后有哪些急救措施？",
    "典型事故经验": "有哪些典型事故案例和经验教训？",
    "常见事故原因": "常见的事故原因有哪些？",
    "防范与整改措施": "有哪些防范措施和整改措施？",
    "相关标准法规": "有哪些相关标准和法规？",
    "知识总结": "综合总结该化学品的安全知识要点？",
}

_SECTION_SYSTEM_PROMPT = (
    "你是一名化工安全领域专家。你只输出一个合法的 JSON 对象，"
    "不输出任何解释性文字、不输出 Markdown 代码围栏以外的内容，"
    "绝不伪造文献、标准号、页码或证据编号。"
)


def _extract_content_fallback(raw):
    """从（可能被截断的）JSON 文本里正则提取 "content" 字段并解码转义。"""
    if not raw:
        return None
    m = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.DOTALL)
    if not m:
        return None
    s = m.group(1)
    try:
        return json.loads('"' + s + '"')
    except Exception:
        return s.replace("\\n", "\n").replace('\\"', '"')


class WikiGenerator:
    def __init__(self, rag_system=None, case_retriever=None):
        if rag_system is None:
            raise ValueError("WikiGenerator 需要已初始化的 RAGSystem")
        self.rag = rag_system
        self.store = WikiStore()
        self.validator = WikiQualityValidator()
        self.case_retriever = case_retriever  # 可选：wiki_generation 案例检索

    # ------------------------------------------------------------------ #
    # Outline
    # ------------------------------------------------------------------ #
    def build_outline(self, entity):
        """返回 17 个规范 section 作为 outline。各 section 可 applicable=false 跳过。"""
        return list(WIKI_SECTIONS)

    def _section_query(self, entity, section):
        return f"{entity}{SECTION_QUERIES.get(section, '有哪些安全相关信息？')}"

    # ------------------------------------------------------------------ #
    # 主生成
    # ------------------------------------------------------------------ #
    def generate(self, entity, save=True):
        print(f"\n开始分章节生成 Wiki: {entity}")
        sections = []
        outline = self.build_outline(entity)
        for i, section in enumerate(outline):
            print(f"  [{i + 1}/{len(outline)}] {section}")
            result = self._generate_section_with_retry(entity, section)
            if result.get("applicable") is False:
                print(f"    → 跳过（不适用）")
                continue
            if (result.get("content") or "").strip():
                sections.append(result)
            else:
                print(f"    → 空内容，跳过")
        markdown = self._assemble_markdown(entity, sections)
        validation = self.validator.validate_wiki(sections)
        print(f"  生成完成：{len(sections)} 个 section，校验 {validation}")

        if save:
            self.store.save(entity, markdown, self._flatten_evidence(sections))
            self.store.save_sections(entity, sections)
            print("  Wiki 保存成功")

        return {
            "entity": entity,
            "wiki": markdown,
            "sections": sections,
            "evidence": self._flatten_evidence(sections),
            "validation": validation,
        }

    def _generate_section_with_retry(self, entity, section, max_retry=2):
        query = self._section_query(entity, section)
        evidence = self.rag.retrieve_evidence(query).get("evidence", [])
        cases = self._retrieve_wiki_cases(query)

        result = self._generate_section(entity, section, evidence, cases)
        ok, errors = self.validator.validate_section(result, evidence)
        attempt = 0
        while not ok and attempt < max_retry:
            print(f"    section「{section}」校验失败，重试 {attempt + 1}: {errors}")
            result = self._generate_section(entity, section, evidence, cases)
            ok, errors = self.validator.validate_section(result, evidence)
            attempt += 1

        result["_validated"] = ok
        result["_errors"] = errors
        result["evidence"] = evidence  # 该 section 的局部 evidence
        return result

    def _generate_section(self, entity, section, evidence, cases):
        context = self._build_evidence_context(evidence)
        case_str = self._build_case_context(cases)
        prompt = self._build_section_prompt(entity, section, context, case_str)
        raw = self.rag.llm.generate(
            prompt, system_prompt=_SECTION_SYSTEM_PROMPT,
            max_new_tokens=4096, temperature=0.2,
        )
        obj, _ = parse_llm_json(raw)
        if obj is None:
            # JSON 可能被截断：尝试正则提取 content 字段，至少不丢正文
            content = _extract_content_fallback(raw)
            obj = {"section": section, "applicable": True,
                   "content": content if content is not None else (raw or ""),
                   "knowledge_blocks": []}
        obj.setdefault("section", section)
        obj.setdefault("applicable", True)
        obj.setdefault("content", "")
        obj.setdefault("knowledge_blocks", [])
        return obj

    # ------------------------------------------------------------------ #
    # Prompt 构建
    # ------------------------------------------------------------------ #
    def _build_evidence_context(self, evidence):
        if not evidence:
            return "（无本地文档证据，可用模型补充知识，但需明确标注）"
        parts = []
        for i, item in enumerate(evidence):
            meta = item.get("metadata", {}) if isinstance(item, dict) else {}
            parts.append(
                f"[Wiki证据{i + 1}]\n标题: {meta.get('title', '')}\n"
                f"编号: {meta.get('code', '')}\n页码: {meta.get('page_start', '')}\n"
                f"内容: {meta.get('text', '')[:600]}"
            )
        return "\n\n".join(parts)

    def _retrieve_wiki_cases(self, query):
        if self.case_retriever is None:
            return None
        try:
            return self.case_retriever.retrieve(query, task_type="wiki_generation",
                                                source_type="wiki",
                                                top_k_success=2, top_k_failure=2)
        except Exception:
            return None

    def _build_case_context(self, cases):
        if not cases:
            return "（无历史 Wiki 案例）"
        parts = []
        for c in cases.get("success_cases", []):
            parts.append(
                f"【历史成功案例】section={c.get('section', '')}\n"
                f"内容: {(c.get('reviewed_content') or c.get('source_text', ''))[:400]}"
            )
        for c in cases.get("failure_cases", []):
            parts.append(
                f"【历史失败案例（负例，不要照抄错误写法）】section={c.get('section', '')}\n"
                f"Incorrect: {(c.get('source_text') or '')[:300]}\n"
                f"Reason: {c.get('error_type', '')} - {c.get('review_comment', '')}\n"
                f"Corrected: {(c.get('reviewed_content') or '')[:300]}"
            )
        return "\n\n".join(parts)

    def _build_section_prompt(self, entity, section, context, case_str):
        return f"""请为化学品「{entity}」生成 Wiki 的「{section}」章节。

【知识来源规则】
1. 你可以同时使用两类知识：
   A. Grounded（文档证据）：下方"参考资料"里的内容，引用时必须标注 [Wiki证据N]。
   B. Model Prior（你的专业背景知识）：证据之外的补充，knowledge_source=model_prior。
2. 严格区分来源，model_prior 内容绝不添加证据引用。
3. 禁止伪造标准号、法规、页码、文献。
4. 不确定的内容明确表达"不确定/需进一步核实"。
5. 若本化学品不适合这一章节，输出 applicable=false，content 留空。
6. 保持简洁：每节 content 控制在 800-1200 字，只写重点，避免罗列。

【参考资料】
{context}

【历史 Wiki 案例】
{case_str}

【输出】只输出一个 JSON 对象：
{{
  "section": "{section}",
  "applicable": true,
  "content": "Markdown 文本；grounded 句子末尾标注 [Wiki证据N]；model_prior 句子以（模型补充）开头",
  "knowledge_blocks": [
    {{"text": "一句 grounded 内容", "knowledge_source": "grounded", "evidence_ids": [1]}},
    {{"text": "一句 model_prior 内容", "knowledge_source": "model_prior", "evidence_ids": []}}
  ]
}}"""

    # ------------------------------------------------------------------ #
    # 拼接
    # ------------------------------------------------------------------ #
    def _assemble_markdown(self, entity, sections):
        out = [f"# {entity}"]
        for s in sections:
            out.append(f"## {s.get('section', '')}")
            out.append((s.get('content') or '').strip())
            out.append("")
        return "\n\n".join(out).strip()

    def _flatten_evidence(self, sections):
        """合并各 section 的 evidence（按 chunk_id 去重），返回全局列表。"""
        seen = set()
        out = []
        for s in sections:
            for item in s.get("evidence", []):
                if not isinstance(item, dict):
                    continue
                cid = (item.get("metadata") or {}).get("chunk_id")
                if cid is None or cid in seen:
                    continue
                seen.add(cid)
                out.append(item)
        return out
