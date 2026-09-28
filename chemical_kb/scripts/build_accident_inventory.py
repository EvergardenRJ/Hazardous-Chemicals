# -*- coding: utf-8 -*-
"""
事故文件盘点 (Phase 1)

递归扫描 data/pdf/事故 目录，统计各类文件数量/大小，
检测损坏/空/重名文件，并生成事故文档清单 inventory.json / accident_inventory.csv。

清单以「可解析单元」为单位：
  - 单个 .pdf/.docx/.doc/.jpg/.png 文件 → 1 条记录
  - 纯图片子目录（多页扫描报告）→ 1 条记录（pages = 排序后的图片）

本脚本只读，不修改任何原始文件，也不触碰现有标准法规知识库。
"""
import os
import re
import json
import csv
import hashlib
from pathlib import Path
from collections import Counter, defaultdict

BASE = "/root/autodl-tmp/chemical_kb"
ACCIDENT_DIR = Path(BASE) / "data" / "pdf" / "事故"
OUT_ROOT = Path(BASE) / "data" / "accident"

SUPPORTED = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}

INVENTORY_JSON = OUT_ROOT / "inventory.json"
INVENTORY_CSV = OUT_ROOT / "accident_inventory.csv"


def md5_file(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def read_magic(path, n=8):
    with open(path, "rb") as f:
        return f.read(n)


def natural_key(name):
    """自然排序：1.jpg, 2.jpg, ..., 10.jpg 而非 1,10,2"""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def is_corrupted(path, ext):
    """根据文件头魔数判断是否损坏"""
    if path.stat().st_size == 0:
        return True, "empty"
    m = read_magic(path)
    if ext == ".pdf":
        ok = m.startswith(b"%PDF")
    elif ext == ".docx":
        ok = m.startswith(b"PK\x03\x04")
    elif ext == ".doc":
        # 真实 OLE2 doc、被改名成 .doc 的 docx/zip、RTF 都算可处理
        ok = m.startswith(b"\xd0\xcf\x11\xe0") or m.startswith(b"PK\x03\x04") or m.startswith(b"{\\rtf")
    elif ext in (".jpg", ".jpeg"):
        ok = m.startswith(b"\xff\xd8\xff")
    elif ext == ".png":
        ok = m.startswith(b"\x89PNG")
    else:
        ok = True
    return (not ok), "bad_magic" if not ok else ""


def scan():
    """返回 (单文件清单, 图片目录清单)"""
    single_files = []
    image_dirs = []

    # 顶层子目录：判断是否为「纯图片目录」
    subdirs = [d for d in ACCIDENT_DIR.iterdir() if d.is_dir()]

    for d in subdirs:
        inner = [p for p in d.rglob("*") if p.is_file()]
        if inner and all(p.suffix.lower() in IMAGE_EXTS for p in inner):
            # 纯图片目录 → 一个多页扫描文档
            image_dirs.append(d)
        else:
            # 非纯图片目录里的文件逐个作为单文件
            single_files.extend(sorted(inner, key=lambda p: natural_key(str(p))))

    # 顶层散文件
    single_files.extend([p for p in ACCIDENT_DIR.iterdir() if p.is_file()])

    return single_files, image_dirs


def build_manifest():
    single_files, image_dirs = scan()

    manifest = []
    stats = {
        "total_physical_files": 0,
        "by_ext": Counter(),
        "total_size_bytes": 0,
        "empty_files": [],
        "corrupted_files": [],
        "duplicate_names": [],
        "duplicate_content": [],
    }

    name_map = defaultdict(list)   # file_name -> [paths]
    md5_map = defaultdict(list)    # md5 -> [paths]

    # ---- 物理文件统计 ----
    all_files = list(single_files)
    for d in image_dirs:
        all_files.extend([p for p in d.rglob("*") if p.is_file()])

    for p in all_files:
        ext = p.suffix.lower()
        size = p.stat().st_size
        stats["total_physical_files"] += 1
        stats["by_ext"][ext] += 1
        stats["total_size_bytes"] += size
        name_map[p.name].append(str(p))
        if size == 0:
            stats["empty_files"].append(str(p))
        try:
            stats["md5_cache"] = getattr(stats, "md5_cache", {})
            h = md5_file(p)
            stats["md5_cache"][str(p)] = h
            md5_map[h].append(str(p))
        except Exception as e:
            stats["corrupted_files"].append(str(p) + " (md5 fail: %s)" % e)

    for name, paths in name_map.items():
        if len(paths) > 1:
            stats["duplicate_names"].append({"file_name": name, "paths": paths})

    for h, paths in md5_map.items():
        if len(paths) > 1:
            stats["duplicate_content"].append({"md5": h, "paths": paths})

    # ---- 生成清单（解析单元）----
    # 单文件
    for p in single_files:
        ext = p.suffix.lower()
        size = p.stat().st_size
        rel = str(p.relative_to(ACCIDENT_DIR))
        file_id = "ACC_" + hashlib.md5(rel.encode("utf-8")).hexdigest()[:16]
        corrupt, why = is_corrupted(p, ext)
        manifest.append({
            "file_id": file_id,
            "file_name": p.name,
            "file_path": str(p),
            "rel_path": rel,
            "file_ext": ext.lstrip("."),
            "file_size": size,
            "source_type": "accident",
            "is_image_dir": False,
            "page_count": "",
            "parse_status": "failed" if corrupt else "pending",
            "parse_method": "",
            "corrupted": corrupt,
            "error": why if corrupt else "",
        })

    # 图片目录
    for d in image_dirs:
        imgs = sorted([p for p in d.rglob("*") if p.is_file()],
                      key=lambda p: natural_key(p.name))
        rel = str(d.relative_to(ACCIDENT_DIR))
        file_id = "ACC_" + hashlib.md5(rel.encode("utf-8")).hexdigest()[:16]
        size = sum(p.stat().st_size for p in imgs)
        manifest.append({
            "file_id": file_id,
            "file_name": d.name,
            "file_path": str(d),
            "rel_path": rel,
            "file_ext": "jpg",  # 目录内图片统一按 jpg 记
            "file_size": size,
            "source_type": "accident",
            "is_image_dir": True,
            "page_count": len(imgs),
            "parse_status": "pending",
            "parse_method": "",
            "corrupted": False,
            "error": "",
        })

    return manifest, stats


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("事故文件盘点")
    print("事故目录:", ACCIDENT_DIR)
    print("=" * 60)

    manifest, stats = build_manifest()

    # 保存 JSON
    with open(INVENTORY_JSON, "w", encoding="utf-8") as f:
        json.dump({"manifest": manifest, "stats": {
            "total_physical_files": stats["total_physical_files"],
            "by_ext": dict(stats["by_ext"]),
            "total_size_bytes": stats["total_size_bytes"],
            "empty_files": stats["empty_files"],
            "corrupted_files": stats["corrupted_files"],
            "duplicate_names": stats["duplicate_names"],
            "duplicate_content": stats["duplicate_content"],
        }}, f, ensure_ascii=False, indent=2)

    # 保存 CSV
    fields = ["file_id", "file_name", "file_path", "file_ext", "file_size",
              "source_type", "is_image_dir", "page_count", "parse_status",
              "parse_method", "corrupted", "error"]
    with open(INVENTORY_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in manifest:
            w.writerow({k: m.get(k, "") for k in fields})

    # 打印统计
    print("\n[统计]")
    print("物理文件总数:", stats["total_physical_files"])
    print("按扩展名:")
    for ext, c in sorted(stats["by_ext"].items()):
        print("   %s: %d" % (ext, c))
    print("总大小: %.2f MB" % (stats["total_size_bytes"] / 1024 / 1024))
    print("解析单元(清单记录)总数:", len(manifest))
    print("  - 单文件:", sum(1 for m in manifest if not m["is_image_dir"]))
    print("  - 图片目录:", sum(1 for m in manifest if m["is_image_dir"]))
    print("空文件:", len(stats["empty_files"]))
    print("损坏文件:", len(stats["corrupted_files"]))
    print("重名文件组:", len(stats["duplicate_names"]))
    print("内容重复组:", len(stats["duplicate_content"]))

    if stats["empty_files"]:
        print("\n[空文件列表]")
        for p in stats["empty_files"]:
            print("  ", p)
    if stats["corrupted_files"]:
        print("\n[损坏文件列表]")
        for p in stats["corrupted_files"]:
            print("  ", p)
    if stats["duplicate_names"]:
        print("\n[重名文件]")
        for d in stats["duplicate_names"]:
            print("  名称:", d["file_name"])
            for p in d["paths"]:
                print("      ", p)
    if stats["duplicate_content"]:
        print("\n[内容重复]")
        for d in stats["duplicate_content"]:
            print("  md5:", d["md5"])
            for p in d["paths"]:
                print("      ", p)

    print("\n清单已保存:", INVENTORY_JSON)
    print("CSV 已保存:", INVENTORY_CSV)


if __name__ == "__main__":
    main()
