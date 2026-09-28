# -*- coding: utf-8 -*-
"""Wiki Quality Validator：逐 section 校验 + 整篇校验。

v0.5 规格 4：检查 section 完整、截断、fence 闭合、乱码、重复/空 section、
citation 指向真实 evidence、model_prior 伪装 grounded、总长度。
"""
import re

# 明显异常字符：Unicode 替换符 U+FFFD + 控制字符（用转义序列，避免非字符/私用区）
_GARBLED_RE = re.compile("[�\x00-\x08\x0b\x0c\x0e-\x1f]")
# 终端标点（用于判断是否可能被截断）
_TERMINAL = ("。", "．", ".", "!", "！", "?", "？", ")", "）", "]", "】", ":", "：")
_FENCE_RE = re.compile(r"```")
_EVID_RE = re.compile(r"\[Wiki证据(\d+)\]")


class WikiQualityValidator:
    # ------------------------------------------------------------------ #
    # 逐 section 校验：返回 (ok, errors)
    # ------------------------------------------------------------------ #
    def validate_section(self, result, evidence):
        errors = []
        result = result or {}
        content = (result.get("content") or "").strip()
        applicable = result.get("applicable", True)

        # 1. 不适用 → 不算失败（跳过）
        if applicable is False:
            return True, []

        # 2. 空 section
        if not content:
            errors.append("section 内容为空")
            return False, errors

        # 3. Markdown fence 未闭合
        fences = _FENCE_RE.findall(content)
        if fences and len(fences) % 2 != 0:
            errors.append("markdown fence 未闭合")

        # 4. 乱码 / 异常字符
        if _GARBLED_RE.search(content):
            errors.append("检测到乱码/异常字符")

        # 5. 可能截断（结尾无终端标点 且 长度较短）
        if not content.endswith(_TERMINAL) and len(content) < 300:
            errors.append("疑似截断（结尾无终止标点）")

        # 6. knowledge_blocks 引用检查
        blocks = result.get("knowledge_blocks") or []
        n_evidence = len(evidence or [])
        for b in blocks:
            if not isinstance(b, dict):
                continue
            src = b.get("knowledge_source", "")
            ids = b.get("evidence_ids") or []
            # model_prior 伪装 grounded：标了 model_prior 却带 evidence_ids
            if src == "model_prior" and ids:
                errors.append(f"model_prior 块带了 evidence_ids={ids}（伪装引用）")
            # grounded 引用越界
            if src == "grounded":
                for eid in ids:
                    try:
                        if int(eid) < 1 or int(eid) > n_evidence:
                            errors.append(f"evidence_id={eid} 越界（证据共 {n_evidence} 条）")
                    except (ValueError, TypeError):
                        errors.append(f"evidence_id={eid} 非法")

        return (len(errors) == 0), errors

    # ------------------------------------------------------------------ #
    # 整篇校验：返回 {ok, errors, section_count, total_len}
    # ------------------------------------------------------------------ #
    def validate_wiki(self, sections):
        errors = []
        seen = set()
        empty = 0
        total_len = 0
        for s in sections or []:
            sec = s.get("section", "")
            content = (s.get("content") or "").strip()
            total_len += len(content)
            if sec in seen:
                errors.append(f"重复 section: {sec}")
            seen.add(sec)
            if not content:
                empty += 1
        if empty:
            errors.append(f"{empty} 个空 section")
        if total_len < 500:
            errors.append(f"总长度过短（{total_len} 字符）")
        if total_len > 30000:
            errors.append(f"总长度过长（{total_len} 字符）")
        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "section_count": len(sections or []),
            "total_len": total_len,
        }
