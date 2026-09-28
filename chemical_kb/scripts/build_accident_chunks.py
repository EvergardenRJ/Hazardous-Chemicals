# -*- coding: utf-8 -*-
"""
事故文档 Chunk (Phase 4)

采用「章节优先 + 长度限制」切块：
  - 先按事故报告常见章节标题切分（一、二、三… / （一）（二）… / 1. 2. … / 关键词标题）
  - 章节 <= 1200 字整体保留，过长章节再按 ~1000 字 + 150 字重叠二次切分
  - 兼容现有标准法规 chunk schema（保留 document_type/status/source/code/char_count 字段）

输出 chunks_accident.jsonl，每个 chunk 一行 JSON。
"""
import re
import json
from pathlib import Path

BASE = "/root/autodl-tmp/chemical_kb"
OUT_ROOT = Path(BASE) / "data" / "accident"
PARSED_DIR = OUT_ROOT / "parsed_documents"
CHUNKS_DIR = OUT_ROOT / "chunks"
CHUNKS_FILE = CHUNKS_DIR / "chunks_accident.jsonl"

MAX_SECTION = 1200   # 章节超过该长度才二次切分
CHUNK_SIZE = 1000    # 二次切分目标长度
OVERLAP = 150        # 二次切分重叠
MIN_TEXT = 30        # 低于该长度的页文本跳过

# 常见事故报告章节标题（短行且以这些关键词开头/相等）
SECTION_KEYWORDS = [
    "事故基本情况", "基本情况", "事故概况", "事故发生经过", "事故经过",
    "事故应急处置", "应急处置", "事故原因", "直接原因", "间接原因",
    "事故性质", "人员伤亡", "伤亡情况", "经济损失", "责任认定", "责任追究",
    "事故防范措施", "防范措施", "整改措施", "调查结论", "企业概况",
    "设备情况", "处理意见", "事故责任", "事故类别",
]

HEADING_RE = re.compile(
    r'^\s*(?:'
    r'(?:第[一二三四五六七八九十百零]+[章节部分篇])'
    r'|(?:[一二三四五六七八九十]+[、.．])'
    r'|(?:[（(][一二三四五六七八九十]+[）)])'
    r'|(?:\d{1,2}[、.．]\s*)'
    r'|(?:\d{1,2}\.\d{1,2}\s*)'
    r')'
)


def is_heading(line):
    line = line.strip()
    if not line:
        return False
    if len(line) > 60:
        return False
    if HEADING_RE.match(line):
        return True
    for kw in SECTION_KEYWORDS:
        if line == kw or (line.startswith(kw) and len(line) <= len(kw) + 6):
            return True
    return False


def build_full_text(pages):
    full = []
    page_map = []
    for page in pages:
        t = page.get("text", "")
        if not t or not t.strip():
            continue
        if len(t.strip()) < MIN_TEXT:
            continue
        start = len(full)
        full.append(t + "\n")
        page_map.append((start, len(full) - 1, page["page"]))
    return "".join(full), page_map


def page_for_offset(page_map, off):
    """根据字符偏移量定位页码"""
    pg = 1
    for (s, e, p) in page_map:
        if s <= off <= e:
            return p
        if off > e:
            pg = p
    return pg


def split_sections(full):
    """按标题切分，返回 [(section_name, start, end)]，end 为绝对字符下标"""
    lines = full.split("\n")
    sections = []
    cur_name = "正文"
    cur_start = 0
    pos = 0
    for line in lines:
        if is_heading(line):
            if pos > cur_start:
                sections.append((cur_name, cur_start, pos))
            cur_name = line.strip()
            cur_start = pos + len(line) + 1
        pos += len(line) + 1
    if pos > cur_start:
        sections.append((cur_name, cur_start, pos))
    # 合并空段落
    sections = [(n, s, e) for (n, s, e) in sections if full[s:e].strip()]
    return sections


def build_chunks(doc):
    doc_id = doc["doc_id"]
    title = doc.get("title", "")
    source_file = doc.get("source_file", "")
    source_path = doc.get("source_path", "")
    pages = doc.get("pages", [])

    full, page_map = build_full_text(pages)
    if not full.strip():
        return []

    sections = split_sections(full)
    chunks = []
    idx = 0

    for sec_name, s0, s1 in sections:
        seg = full[s0:s1]
        seg = seg.strip()
        if not seg:
            continue
        seg_len = len(seg)

        if seg_len <= MAX_SECTION:
            pieces = [(0, seg_len)]
        else:
            pieces = []
            pos = 0
            while pos < seg_len:
                end = min(pos + CHUNK_SIZE, seg_len)
                pieces.append((pos, end))
                if end >= seg_len:
                    break
                pos = end - OVERLAP

        for (a, b) in pieces:
            chunk_text = seg[a:b].strip()
            if not chunk_text:
                continue
            a0 = s0 + a
            a1 = s0 + b - 1
            ps = page_for_offset(page_map, a0)
            pe = page_for_offset(page_map, a1)
            idx += 1
            chunks.append({
                "chunk_id": "%s_c%04d" % (doc_id, idx),
                "doc_id": doc_id,
                "doc_type": "accident",
                "document_type": "事故",
                "title": title,
                "source_file": source_file,
                "source_path": source_path,
                "section": sec_name,
                "page_start": ps,
                "page_end": pe,
                "text": chunk_text,
                "char_count": len(chunk_text),
                "code": "",
                "status": "ACTIVE",
                "source": "事故",
                "quality": "normal" if len(chunk_text) >= 100 else "short",
            })
    return chunks


def main():
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("事故文档 Chunk 切分")
    print("=" * 60)

    files = sorted(Path(PARSED_DIR).glob("*.json"))
    print("解析文档数:", len(files))

    all_chunks = []
    section_counter = {}
    for i, fp in enumerate(files, 1):
        with open(fp, encoding="utf-8") as f:
            doc = json.load(f)
        chunks = build_chunks(doc)
        all_chunks.extend(chunks)
        for c in chunks:
            section_counter[c["section"]] = section_counter.get(c["section"], 0) + 1
        if i % 50 == 0:
            print("  已处理 %d/%d" % (i, len(files)))

    # 写 JSONL
    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # 统计
    lens = [c["char_count"] for c in all_chunks]
    print("\n" + "=" * 60)
    print("Chunk 统计")
    print("=" * 60)
    print("事故文档数:", len(files))
    print("chunk 总数:", len(all_chunks))
    if lens:
        print("平均 chunk 长度: %.0f 字符" % (sum(lens) / len(lens)))
        print("最短:", min(lens), "最长:", max(lens))
    print("空 chunk:", sum(1 for l in lens if l == 0))

    print("\n章节识别情况（出现次数 Top 30）:")
    for sec, cnt in sorted(section_counter.items(), key=lambda x: -x[1])[:30]:
        print("   %s: %d" % (sec, cnt))

    print("\n输出文件:", CHUNKS_FILE)


if __name__ == "__main__":
    main()
