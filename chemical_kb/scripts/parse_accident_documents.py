# -*- coding: utf-8 -*-
"""
事故报告多格式解析 (Phase 2)

将 PDF / DOCX / DOC / 图片 统一解析成标准 JSON，每个源文件生成一个 JSON。
策略：
  - PDF：优先文本层（每页有效文本 >= 阈值用 text），否则 OCR 兜底，不盲目全量 OCR
  - DOCX：python-docx 解析段落 + 表格，保留顺序
  - DOC：先看魔数（改名 docx / OLE2 / RTF），OLE2 用 antiword/catdoc 转文本
  - 图片（单张/图片目录）：PaddleOCR
轻量清洗，不破坏标题/章节/事故要素。

幂等：默认跳过已存在的输出 JSON（可用 --force 覆盖）。
单个坏文件不中断整体流程。
"""
import os
import re
import sys
import json
import csv
import time
import hashlib
import subprocess
from pathlib import Path

import fitz  # PyMuPDF

BASE = "/root/autodl-tmp/chemical_kb"
ACCIDENT_DIR = Path(BASE) / "data" / "pdf" / "事故"
OUT_ROOT = Path(BASE) / "data" / "accident"
PARSED_DIR = OUT_ROOT / "parsed_documents"
INVENTORY_JSON = OUT_ROOT / "inventory.json"
REPORT_CSV = OUT_ROOT / "parse_report.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

# PDF 文本层判定阈值：每页有效文本 >= 该值才认为有可用文本层
TEXT_THRESHOLD = 100


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def clean_text(text):
    """轻量清洗：去 NUL、合并异常空格、去行尾空格、去重复空行"""
    if not text:
        return ""
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_magic(path, n=8):
    with open(path, "rb") as f:
        return f.read(n)


# ------------------------------------------------------------
# OCR 初始化（延迟到真正需要 OCR 时才加载，节省内存）
# ------------------------------------------------------------
_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        print("   [OCR] 初始化 PaddleOCR (GPU)...", flush=True)
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            use_gpu=True,
            gpu_mem=10000,
            rec_batch_num=16,
        )
        print("   [OCR] 就绪", flush=True)
    return _ocr


def ocr_image_array(arr):
    ocr = get_ocr()
    result = ocr.ocr(arr, cls=True)
    texts = []
    if result:
        for block in result:
            if block:
                for item in block:
                    txt = item[1][0]
                    score = item[1][1]
                    if score >= 0.5:
                        texts.append(txt)
    return "\n".join(texts)


def ocr_pdf_page(page, dpi=250):
    import numpy as np
    from PIL import Image
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return ocr_image_array(np.array(img))


# ------------------------------------------------------------
# 各格式解析
# ------------------------------------------------------------

def parse_pdf(path):
    doc = fitz.open(str(path))
    pages = []
    methods = []
    total_chars = 0
    for i, page in enumerate(doc):
        text = page.get_text()
        if len(text.strip()) >= TEXT_THRESHOLD:
            method = "text"
        else:
            method = "ocr"
            text = ocr_pdf_page(page)
        text = clean_text(text)
        total_chars += len(text)
        methods.append(method)
        pages.append({"page": i + 1, "text": text})
    doc.close()
    if "ocr" in methods and "text" in methods:
        parse_method = "mixed"
    elif "ocr" in methods:
        parse_method = "ocr"
    else:
        parse_method = "text"
    return pages, parse_method, total_chars


def iter_block_items(parent):
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.ns import qn
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)


def docx_to_text(path):
    from docx import Document
    document = Document(str(path))
    blocks = []
    for block in iter_block_items(document):
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        if isinstance(block, Paragraph):
            t = block.text.strip()
            if t:
                blocks.append(t)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                line = " | ".join(cells).strip()
                if line.strip(" |"):
                    blocks.append(line)
    return "\n".join(blocks)


def parse_docx(path):
    text = docx_to_text(path)
    pages = [{"page": 1, "text": clean_text(text)}]
    return pages, "docx", len(text)


def parse_doc(path):
    """老式 .doc：按魔数判断实际格式"""
    m = read_magic(path)
    if m.startswith(b"PK\x03\x04"):
        # 实际是改名 docx
        return parse_docx(path)
    if m.startswith(b"{\\rtf"):
        raw = path.read_text(encoding="utf-8", errors="replace")
        # 简单剥离 RTF 控制字（尽力而为）
        txt = re.sub(r"\\[a-z]+\-?\d* ?", "", raw)
        txt = re.sub(r"[\\{}]", "", txt)
        pages = [{"page": 1, "text": clean_text(txt)}]
        return pages, "rtf", len(txt)
    if m.startswith(b"\xd0\xcf\x11\xe0"):
        # 真实 OLE2 .doc，尝试 antiword / catdoc
        for tool in (["catdoc", "-d", "utf-8"], ["antiword", "-m", "UTF-8.txt"],
                     ["antiword"]):
            try:
                r = subprocess.run(tool + [str(path)], capture_output=True, timeout=120)
                if r.returncode == 0 and r.stdout.strip():
                    txt = r.stdout.decode("utf-8", errors="replace")
                    pages = [{"page": 1, "text": clean_text(txt)}]
                    return pages, "doc_" + tool[0], len(txt)
            except Exception:
                continue
        raise RuntimeError("无法解析 OLE2 .doc（缺 antiword/catdoc）")
    raise RuntimeError("未知 .doc 格式，魔数: %s" % m[:4].hex())


def parse_image(path):
    import numpy as np
    from PIL import Image
    img = np.array(Image.open(str(path)).convert("RGB"))
    text = clean_text(ocr_image_array(img))
    pages = [{"page": 1, "text": text}]
    return pages, "ocr", len(text)


def parse_image_dir(d):
    imgs = sorted([p for p in d.rglob("*") if p.is_file()],
                  key=lambda p: natural_key(p.name))
    pages = []
    total = 0
    for i, p in enumerate(imgs):
        import numpy as np
        from PIL import Image
        try:
            img = np.array(Image.open(str(p)).convert("RGB"))
            text = clean_text(ocr_image_array(img))
        except Exception as e:
            text = ""
            print("   [WARN] 图片 OCR 失败 %s: %s" % (p.name, e))
        total += len(text)
        pages.append({"page": i + 1, "text": text})
    return pages, "ocr", total


# ------------------------------------------------------------
# 单文档调度
# ------------------------------------------------------------

def parse_one(item, force=False):
    file_id = item["file_id"]
    out = PARSED_DIR / (file_id + ".json")
    if out.exists() and not force:
        return {"doc_id": file_id, "status": "skip", "method": "", "chars": 0,
                "pages": 0, "error": ""}

    title = item["file_name"]
    for ext in (".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"):
        if title.lower().endswith(ext):
            title = title[: -len(ext)]
            break

    path = item["file_path"]
    try:
        if item.get("is_image_dir"):
            pages, method, chars = parse_image_dir(Path(path))
            file_type = "jpg"
        else:
            ext = item["file_ext"].lower()
            if ext == "pdf":
                pages, method, chars = parse_pdf(path)
                file_type = "pdf"
            elif ext == "docx":
                pages, method, chars = parse_docx(path)
                file_type = "docx"
            elif ext == "doc":
                pages, method, chars = parse_doc(path)
                file_type = "doc"
            elif ext in ("jpg", "jpeg", "png"):
                pages, method, chars = parse_image(path)
                file_type = ext
            else:
                raise RuntimeError("不支持的类型: " + ext)

        full_text = "\n".join(p["text"] for p in pages)
        doc = {
            "doc_id": file_id,
            "doc_type": "accident",
            "title": title,
            "source_file": item["file_name"],
            "source_path": path,
            "file_type": file_type,
            "parse_method": method,
            "page_count": len(pages),
            "pages": pages,
            "full_text": full_text,
            "char_count": chars,
            "metadata": {"source": "事故报告"},
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        return {"doc_id": file_id, "status": "success", "method": method,
                "chars": chars, "pages": len(pages), "error": ""}
    except Exception as e:
        return {"doc_id": file_id, "status": "failed", "method": "",
                "chars": 0, "pages": 0, "error": str(e)}


def main():
    force = "--force" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("事故报告多格式解析")
    print("=" * 60)

    with open(INVENTORY_JSON, encoding="utf-8") as f:
        inv = json.load(f)
    manifest = inv["manifest"]

    # 跳过损坏/空文件
    todo = [m for m in manifest if m.get("parse_status") != "failed"]
    if limit:
        todo = todo[:limit]

    print("待解析文档:", len(todo), "/ 总清单:", len(manifest))

    results = []
    t0 = time.time()
    for i, item in enumerate(todo, 1):
        print("[%d/%d] %s (%s)" % (i, len(todo), item["file_id"],
                                   item["file_ext"]), flush=True)
        r = parse_one(item, force=force)
        results.append(r)
        if r["status"] != "skip":
            print("        -> %s 方法=%s 页=%s 字符=%s %s" %
                  (r["status"], r["method"] or "-", r["pages"],
                   r["chars"], r.get("error") or ""))

    cost = time.time() - t0

    # 写报告
    with open(REPORT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "status", "method", "page_count", "char_count", "error"])
        # 关联 file_name
        name_map = {m["file_id"]: m["file_name"] for m in manifest}
        for r in results:
            w.writerow([r["doc_id"], r["status"], r["method"], r["pages"],
                        r["chars"], r.get("error", "")])

    # 质量统计
    print("\n" + "=" * 60)
    print("解析质量统计")
    print("=" * 60)
    ok = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "failed"]
    skipped = [r for r in results if r["status"] == "skip"]
    print("成功:", len(ok))
    print("失败:", len(failed))
    print("跳过(已存在):", len(skipped))
    print("直接文本解析:", sum(1 for r in ok if r["method"] in ("text", "docx", "mixed")))
    print("OCR(含图片):", sum(1 for r in ok if "ocr" in r["method"]))
    print("Word解析(docx/doc):",
          sum(1 for r in ok if r["method"] in ("docx", "doc_catdoc", "doc_antiword", "rtf")))
    print("图片OCR:", sum(1 for r in ok if r["method"] == "ocr"))

    empty = [r for r in ok if r["chars"] == 0]
    short = [r for r in ok if 0 < r["chars"] < 100]
    print("空文本:", len(empty))
    print("短文本(<100字):", len(short))
    if ok:
        avg = sum(r["chars"] for r in ok) / len(ok)
        print("平均文本长度: %.0f 字符" % avg)
    print("总耗时: %.1f 秒" % cost)

    if failed:
        print("\n[失败列表]")
        name_map = {m["file_id"]: m["file_name"] for m in manifest}
        for r in failed:
            print("  %s  %s: %s" % (r["doc_id"], name_map.get(r["doc_id"], ""),
                                     r.get("error", "")))

    # 随机抽样检查：2 PDF + 1 Word + 1 图片
    print("\n" + "=" * 60)
    print("随机抽样质量检查（前 500 字）")
    print("=" * 60)
    name_map = {m["file_id"]: m["file_name"] for m in manifest}
    pick_pdf = [r for r in ok if r["method"] in ("text", "ocr", "mixed")][:2]
    pick_word = [r for r in ok if r["method"] in ("docx", "doc_catdoc", "doc_antiword", "rtf")][:1]
    pick_img = [r for r in ok if r["method"] == "ocr" and
                any(m["file_id"] == r["doc_id"] and m.get("is_image_dir") for m in manifest)][:1]
    if not pick_img:
        pick_img = [r for r in ok if r["method"] == "ocr"][:1]

    samples = []
    for label, rs in [("PDF", pick_pdf), ("Word", pick_word), ("图片", pick_img)]:
        for r in rs:
            samples.append((label, r))

    for si, (label, r) in enumerate(samples, 1):
        fp = PARSED_DIR / (r["doc_id"] + ".json")
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
        print("\n[样本%d] %s" % (si, label))
        print("文件:", d.get("source_file", ""))
        print("方法:", d.get("parse_method", ""))
        print("页数:", d.get("page_count", ""))
        txt = d.get("full_text", "")
        print("文本前500字:\n%s" % txt[:500])

    print("\n解析完成。输出目录:", PARSED_DIR)


if __name__ == "__main__":
    main()
