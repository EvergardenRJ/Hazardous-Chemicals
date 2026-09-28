# -*- coding: utf-8 -*-
"""AI 预审核（Pre-Review）：对 pending 断言做 LLM 判断，输出 ai_approved / ai_rejected / ai_uncertain。

v0.7 关键约束：
- AI 只做「预审」，绝不写 reviewed.jsonl（人工 approved 仍是最高可信状态）。
- 结果落盘 data/kg/review/ai_preview.jsonl，decision ∈ {ai_approved, ai_rejected, ai_uncertain, overridden}。
- 不替用户审核：最终 approve/reject/modify 由人工在「KG 审核中心」点击决定。
- 图谱里 ai_approved / ai_uncertain 用不同线型显示，ai_rejected / overridden 回退为 pending（不显示或虚线）。
"""
import json
from datetime import datetime
from pathlib import Path

from core.llm import QwenLLM
from core.kg.review_manager import ReviewManager
from core.kg.extractor import parse_llm_json

AI_PREVIEW_FILE = ReviewManager().review_dir / "ai_preview.jsonl"

DECISIONS = {"ai_approved", "ai_rejected", "ai_uncertain"}

AI_SYSTEM_PROMPT = (
    "你是一名化工安全知识图谱「预审」助手。你对候选三元组（断言）做可靠性判断，"
    "只输出一个严格 JSON，不输出任何解释。绝不编造证据，绝不在证据不足时把结论写成 ai_approved。"
)


def _read_records():
    if not AI_PREVIEW_FILE.exists():
        return []
    rows = []
    with open(AI_PREVIEW_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def load_ai_decisions():
    """返回 {assertion_id: 最后一条 AI 记录}。"""
    out = {}
    for r in _read_records():
        aid = r.get("assertion_id", "")
        if aid:
            out[aid] = r
    return out


def get_ai_decision(assertion_id):
    return load_ai_decisions().get(assertion_id)


def override_ai_decision(assertion_id, note="人工拒绝AI建议"):
    """追加一条 overridden 记录，让该断言在图谱中回退为 pending，AI 面板不再显示建议。"""
    rec = {
        "assertion_id": assertion_id,
        "decision": "overridden",
        "confidence": 0.0,
        "reason": note,
        "suggested_correction": "",
        "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "reviewed_by": "human_override",
        "review_version": "v0.7",
    }
    with open(AI_PREVIEW_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


class AIReviewer:
    """对 pending 断言逐条做 LLM 预审。可注入 mock_llm 用于离线测试（省算力）。"""

    def __init__(self, llm=None):
        self.llm = llm if llm is not None else QwenLLM()

    # ------------------------------------------------------------------ #
    def review_assertion(self, a):
        """返回一条 AI 预审记录 dict。LLM 失败/解析失败时降级 ai_uncertain。"""
        aid = a.get("assertion_id", "")
        rec = {
            "assertion_id": aid,
            "decision": "ai_uncertain",
            "confidence": 0.0,
            "reason": "",
            "suggested_correction": "",
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
            "reviewed_by": "ai_qwen3_4b",
            "review_version": "v0.7",
        }
        try:
            raw = self.llm.generate(self._build_prompt(a),
                                    system_prompt=AI_SYSTEM_PROMPT,
                                    max_new_tokens=512, temperature=0.2)
            obj, _ = parse_llm_json(raw)
        except Exception as e:
            rec["reason"] = f"LLM 调用失败：{e}"
            return rec
        if obj is None:
            rec["reason"] = "LLM 输出无法解析为 JSON"
            return rec
        decision = obj.get("decision", "ai_uncertain")
        rec["decision"] = decision if decision in DECISIONS else "ai_uncertain"
        try:
            conf = float(obj.get("confidence", 0.0) or 0.0)
            rec["confidence"] = max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            rec["confidence"] = 0.0
        rec["reason"] = str(obj.get("reason", ""))[:500]
        rec["suggested_correction"] = str(obj.get("suggested_correction", ""))[:500]
        return rec

    def review_pending(self, n=None, save=True):
        mgr = ReviewManager()
        existing = load_ai_decisions()
        pending = mgr.get_pending()
        if n is not None:
            pending = pending[:int(n)]
        results = []
        for a in pending:
            aid = a.get("assertion_id", "")
            # 幂等：已预审过（decision ∈ ai_*）的跳过，避免重复调用 LLM
            if aid in existing and existing[aid].get("decision") in DECISIONS:
                continue
            r = self.review_assertion(a)
            results.append(r)
            if save:
                with open(AI_PREVIEW_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return results

    # ------------------------------------------------------------------ #
    def _build_prompt(self, a):
        return f"""【候选断言预审】请基于以下 10 个字段判断这条三元组是否可靠，给出结论。

1. 主语实体：{a.get('subject_label', '')}（type={a.get('subject_type', '')}，id={a.get('subject_id', '')}）
2. 谓词关系：{a.get('predicate', '')}
3. 宾语实体：{a.get('object_label', '')}（type={a.get('object_type', '')}，id={a.get('object_id', '')}，kind={a.get('object_kind', '')}）
4. 抽取置信度：{a.get('confidence', '')}
5. 断言类型：{a.get('assertion_type', '')}（explicit=原文明确，inferred=模型推断）
6. 校验状态：{a.get('validation_status', '')}
7. 原文证据：{a.get('source_text_quote', '') or '（无）'}
8. 来源文档：{a.get('source_doc_id', '')}（chunk={a.get('source_chunk_id', '')}）
9. 出处位置：section={a.get('section', '')} page={a.get('page_start', '')}-{a.get('page_end', '')}
10. Schema 版本：{a.get('schema_version', '')}

【判断规则】
- 证据充分、实体类型/关系方向/谓词均正确 → ai_approved（confidence 高）。
- 证据不足、只能推断、方向或类型存疑 → ai_uncertain。
- 明显错误、类型不匹配、谓词语义不符、纯幻觉 → ai_rejected。
- 绝不把不确定判断写成 ai_approved；你只做预审，最终由人工决定。

【输出】只输出一个 JSON 对象：
{{"decision":"ai_approved|ai_rejected|ai_uncertain","confidence":0.0到1.0,"reason":"简述理由","suggested_correction":"若 ai_rejected 或需修正，给出修正建议（subject/predicate/object），否则空串"}}"""
