# -*- coding: utf-8 -*-
"""解析质量统计（Phase 3 辅助）：读 parse_report.csv，输出成功/失败/空/短等指标。"""
import csv
from collections import Counter
from pathlib import Path

BASE = "/root/autodl-tmp/chemical_kb"
CSV = Path(BASE) / "data/accident/parse_report.csv"

rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))

status = Counter(r["status"] for r in rows)
print("status 分布:", dict(status))

ok = [r for r in rows if r["status"] == "success"]
print("成功:", len(ok))

chars = [int(r["char_count"]) for r in ok if r["char_count"].strip().isdigit()]
print("空文本(char=0):", sum(1 for c in chars if c == 0))
print("短文本(<100):", sum(1 for c in chars if 0 < c < 100))
if chars:
    print("平均文本长度: %.0f 字符" % (sum(chars) / len(chars)))
    print("最短/最长:", min(chars), "/", max(chars))

print("解析方法分布:", dict(Counter(r["method"] for r in ok)))
