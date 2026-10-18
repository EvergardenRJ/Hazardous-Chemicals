"""Stable evidence bindings and deterministic Wiki quality gates."""
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit

CITATION = re.compile(r"\[Wiki证据(\d+)\]")
HIGH_RISK = {"急救", "泄漏应急", "火灾/爆炸处置", "储存要求", "运输与装卸", "相关标准法规"}
SECTIONS = ["基本概述", "理化性质", "危险特性", "健康危害", "生产与使用", "储存要求", "运输与装卸", "设备设施与自动化控制", "个体防护", "泄漏应急", "火灾/爆炸处置", "急救", "典型事故经验", "常见事故原因", "防范与整改措施", "相关标准法规", "知识总结"]

def display_source_text(text):
    return str(text or "").replace("来源：模型背景知识（Codex 当前会话生成，待核实）", "来源：大模型知识库")

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def source_signature(m):
    return digest({k:m.get(k) for k in ("doc_id","chunk_id","text","page_start","page_end","source_revision","code","status","document_status","effective_date","repeal_date","version")})

def evidence_id(item):
    m = item.get("metadata") or {}
    return "ev-" + source_signature(m)[:24]

def section_hash(content, evidence):
    stable = CITATION.sub(lambda m: "[evidence:" + evidence[int(m.group(1))-1]["evidence_id"] + "]" if 0<int(m.group(1))<=len(evidence) else m.group(0), content)
    return digest(stable)

def is_high_risk(title):
    return title in HIGH_RISK or any(word in title for word in ("急救", "泄漏", "火灾", "爆炸", "储存", "运输", "法规", "标准"))

def parse_sections(markdown):
    sections, current = [], None
    for line in (markdown or "").splitlines():
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = {"section": line[3:].strip(), "content": ""}
        elif current is not None:
            current["content"] += line + "\n"
    if current:
        sections.append(current)
    return sections

def infer_blocks(content, table, prior_blocks=None):
    """Legacy/manual content is explicitly marked; citation presence is not a truth judgment."""
    if prior_blocks:
        spans=[]
        for b in prior_blocks:
            if b.get("knowledge_source")!="external" or not b.get("text"):continue
            pos=content.find(b["text"])
            if pos>=0:spans.append((pos,pos+len(b["text"]),b))
        if spans:
            result=[];cursor=0
            for start,end,b in sorted(spans,key=lambda x:x[0]):
                if start<cursor:continue
                result.extend(infer_blocks(content[cursor:start],table));result.append(copy.deepcopy(b));cursor=end
            result.extend(infer_blocks(content[cursor:],table));return result
    blocks = []
    for text in re.split(r"\n\s*\n", content.strip()):
        if not text.strip():
            continue
        nums = [int(x) for x in CITATION.findall(text)]
        refs = list(dict.fromkeys(table[n-1]["evidence_id"] for n in nums if 0 < n <= len(table)))
        source = "mixed" if refs and "模型补充" in text else ("grounded" if refs else "model_prior")
        blocks.append({"text": text, "knowledge_source": source, "evidence_ids": nums, "evidence_refs": refs})
    return blocks

def bind_sections(sections, fallback_evidence=None):
    """Convert per-section source numbers to revision-global labels without losing local evidence."""
    result, table, by_id = [], [], {}
    issues = []
    for original in sections:
        s = copy.deepcopy(original)
        title = str(s.get("section") or "").strip()
        s["section_id"] = s.get("section_id") or "sec-" + digest(title)[:16]
        local = fallback_evidence if s.get("citation_scope") == "global" and "original_content" not in s else s.get("evidence")
        if not isinstance(local, list):
            local = fallback_evidence or []
        mapping = {}
        for i, item in enumerate(local, 1):
            if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
                issues.append(title + ": 证据格式无效")
                continue
            eid = evidence_id(item)
            if eid not in by_id:
                e = copy.deepcopy(item)
                e["evidence_id"] = eid
                e["source_hash"] = digest(e["metadata"].get("text", ""))
                table.append(e)
                by_id[eid] = len(table)
            mapping[i] = by_id[eid]
        content = s.get("original_content",s.get("content")) if s.get("citation_scope") == "global" else s.get("content")
        content = display_source_text(content)
        s["original_content"] = content
        def convert(match):
            n = int(match.group(1))
            if n not in mapping:
                issues.append(f"{title}: 局部引用 {n} 缺少证据")
                return match.group(0)
            return f"[Wiki证据{mapping[n]}]"
        s["content"] = CITATION.sub(convert, content).strip()
        source_blocks = s.get("original_knowledge_blocks") if s.get("citation_scope") == "global" else s.get("knowledge_blocks")
        if isinstance(source_blocks, list) and source_blocks:
            s["original_knowledge_blocks"] = copy.deepcopy(source_blocks)
            blocks = []
            for b in source_blocks:
                if not isinstance(b, dict):
                    issues.append(title + ": 知识块不是对象")
                    continue
                b = copy.deepcopy(b)
                nums = b.get("evidence_ids") or []
                converted = []
                for n in nums:
                    try:
                        n = int(n)
                    except (TypeError, ValueError):
                        issues.append(title + ": 非法知识块证据号")
                        continue
                    if n not in mapping:
                        issues.append(title + ": 知识块缺少证据")
                    else:
                        converted.append(mapping[n])
                b["text"] = CITATION.sub(convert, display_source_text(b.get("text")))
                b["evidence_ids"] = list(dict.fromkeys(converted))
                b["evidence_refs"] = [table[n-1]["evidence_id"] for n in b["evidence_ids"]]
                blocks.append(b)
            s["knowledge_blocks"] = blocks
        else:
            s["knowledge_blocks"] = infer_blocks(s["content"], table)
            s["legacy_blocks_inferred"] = True
        s["citation_scope"] = "global"
        s["evidence_refs"] = list(dict.fromkeys(table[int(n)-1]["evidence_id"] for n in CITATION.findall(s["content"]) if 0 < int(n) <= len(table)))
        sources = {b.get("knowledge_source") for b in s["knowledge_blocks"]}
        s["knowledge_source"] = next(iter(sources)) if len(sources) == 1 else ("mixed" if sources else "unknown")
        s["content_hash"] = section_hash(s["content"], table)
        s["status"] = s.get("status", "draft")
        if s.get("applicable") is False:
            s["status"] = "not_applicable"
        result.append(s)
    return result, table, list(dict.fromkeys(issues))

def render(entity, sections):
    return "# " + entity + "\n\n" + "\n\n".join("## " + s["section"] + "\n\n" + s["content"].strip() for s in sections if s.get("applicable", True))

def validate_section(s, evidence, strict=False, publication=False):
    errors = []
    content = str(s.get("content") or "").strip()
    if s.get("applicable") is False:
        return [] if s.get("skip_reason") else ["不适用章节缺少原因"]
    if not content:
        return ["章节内容为空"]
    if "\ufffd" in content or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", content):
        errors.append("正文存在乱码或控制字符")
    if content.count("\x60\x60\x60") % 2:
        errors.append("Markdown 围栏未闭合")
    table = {e.get("evidence_id") for e in evidence}
    nums = [int(n) for n in CITATION.findall(content)]
    if any(n < 1 or n > len(evidence) for n in nums):
        errors.append("正文引用越界")
    blocks = s.get("knowledge_blocks") or []
    if not blocks:
        errors.append("缺少结构化知识块")
    allowed = {"grounded", "model_prior", "mixed", "unknown", "external"}
    covered = set()
    for b in blocks:
        if not isinstance(b, dict):
            errors.append("知识块格式无效")
            continue
        source = b.get("knowledge_source")
        ids = b.get("evidence_ids") or []
        refs = b.get("evidence_refs") or []
        if source not in allowed:
            errors.append("知识来源类型无效")
        if source == "grounded" and not (ids or refs):
            errors.append("文档证据块没有引用")
        if source == "model_prior" and (ids or refs):
            errors.append("模型补充块伪装为文档引用")
        if source == "external":
            name=b.get("source_name")
            parts=urlsplit(str(b.get("source_url") or ""))
            host=(parts.hostname or "").lower()
            allowed_host=(name=="Wikipedia" and host.endswith(".wikipedia.org")) or (name=="百度百科" and host in {"baike.baidu.com","bkso.baidu.com"})
            if parts.scheme!="https" or not allowed_host or not b.get("retrieved_at") or not b.get("external_source_id"):
                errors.append("百科知识块缺少合法来源链接、日期或来源标识")
            if ids or refs:
                errors.append("外部百科不能冒充本地文档证据")
        if any(ref not in table for ref in refs):
            errors.append("知识块稳定证据 ID 缺失")
        for n in ids:
            try:
                if isinstance(n, bool) or not 1 <= int(n) <= len(evidence):
                    raise ValueError()
                covered.add(int(n))
            except (ValueError, TypeError):
                errors.append("知识块引用越界")
        if strict and (not str(b.get("text") or "").strip() or str(b.get("text") or "").strip() not in content):
            errors.append("知识块文本与正文不一致")
        if publication and is_high_risk(s.get("section","")) and source != "grounded":
            errors.append("高风险章节含未被文档支持的内容")
    if strict and set(nums) - covered:
        errors.append("正文引用未在知识块绑定")
    if publication:
        for n in covered:
            state=str(evidence[n-1].get("metadata",{}).get("status","")).lower()
            if state in ("repealed","withdrawn","deleted","inactive","废止","撤回"):
                errors.append("引用了已废止或撤回的来源，需说明历史适用范围并重新核实")
    if s.get("_validated") is False:
        errors.append("生成阶段校验未通过")
    if s.get("status") in ("failed", "evidence_insufficient", "legacy_unverified"):
        errors.append("章节需要补证或核实")
    return list(dict.fromkeys(errors))

def validate_revision(payload, publication=False):
    errors = list(payload.get("binding_errors") or [])
    sections, evidence = payload.get("sections", []), payload.get("evidence", [])
    if not sections:
        errors.append("没有章节")
    if len({s.get("section") for s in sections}) != len(sections):
        errors.append("章节重复")
    for s in sections:
        errors.extend(s.get("section", "") + ": " + e for e in validate_section(s, evidence, strict=True, publication=publication))
    return {"ok": not errors, "errors": list(dict.fromkeys(errors))}
