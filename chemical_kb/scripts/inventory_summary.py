# -*- coding: utf-8 -*-
"""盘点摘要：原始文件类型/数量 + 损坏/空/重复统计。"""
import json
import collections
from pathlib import Path

BASE = "/root/autodl-tmp/chemical_kb"
inv = json.load(open(Path(BASE) / "data/accident/inventory.json", encoding="utf-8"))

print("顶层 keys:", list(inv.keys()))
m = inv.get("manifest", [])
print("parse_units(manifest):", len(m))

exts = collections.Counter()
raw = 0
img_files = 0
for x in m:
    if x.get("is_image_dir"):
        exts["图片目录"] += 1
        n = len(x.get("files", []))
        raw += n
        img_files += n
    else:
        e = str(x.get("file_ext", "")).lower()
        exts[e] += 1
        raw += 1

print("raw_files_total:", raw)
print("图片目录内文件数:", img_files)
print("按单元类型:", dict(exts))

for k in ("corrupted", "empty", "duplicate", "duplicates", "summary"):
    if k in inv:
        print(k, "=", inv[k])
