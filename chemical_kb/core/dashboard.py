"""Read-only dashboard facts, distinct aggregation and source drill-through."""
from __future__ import annotations

from contextlib import closing
import hashlib
import itertools
import json
import math
import re
import sqlite3
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UNKNOWN = "未标注"
VERSION = "dashboard-1.0"
DIMENSIONS = {
    "type": "资料类型", "source": "来源标签", "collection": "资料范围",
    "chemical": "化学品名称提及", "status": "记录状态", "country": "来源国家",
    "month": "月份", "year": "年份", "subject_type": "主体类型",
    "predicate": "关系类型", "object_type": "客体类型", "page_type": "条目类型",
}
TYPE_LABELS = {
    "pdf": "旧资料 · PDF", "docx": "旧资料 · DOCX", "doc": "旧资料 · DOC",
    "md": "旧资料 · Markdown", "accident": "事故报告", "事故": "事故报告",
    "standard": "标准", "regulation": "法规", "incident": "事故报道",
    "investigation": "调查报道", "policy": "政策法规", "education": "安全教育",
    "historical": "历史资料", "news": "资讯", "chemical": "化学品",
    "process": "工艺", "equipment": "设备", "source": "来源资料",
    "topic": "专题", "legacy": "历史条目", "requirement": "要求",
    "clause": "条款", "enterprise": "企业", "site": "场所",
}
STATUS_LABELS = {"approved": "已接受", "modified": "已修订", "rejected": "已拒绝",
                 "pending": "待审核", "candidate": "候选文章", "reviewed": "已核查",
                 "draft": "草稿", "published": "已发布"}
DATASETS = {
    "documents": {
        "label": "资料文档", "unit": "篇", "key": "doc_id",
        "dimensions": ["type", "source", "collection", "chemical", "month", "year"],
        "metrics": {"count": ["唯一文档数", "篇"], "chunks": ["原文片段数", "条"],
                    "characters": ["片段字符数", "字符"], "evidence": ["已接受断言数", "条"]},
        "time_label": "资料发布日期", "multi": ["chemical"],
        "note": "按 doc_id 去重。化学品为目录名称的字面提及，未做语义实体判定；多标签分组总计重新去重。来源是资料标签，不等于发布机构。未从标题中的年份推测发布日期。",
    },
    "news": {
        "label": "新闻文章", "unit": "篇", "key": "article_id",
        "dimensions": ["type", "source", "country", "status", "chemical", "month", "year"],
        "metrics": {"count": ["唯一文章数", "篇"], "characters": ["标题与摘要字符数", "字符"]},
        "time_label": "文章发布日期", "multi": ["chemical"],
        "note": "按 article_id 去重，排除已移除记录。文章分类沿用来源系统规则，不代表事件已核实。发布日期不等于事故发生日期；来源国家不等于事故地点。",
    },
    "relations": {
        "label": "已接受知识", "unit": "条", "key": "assertion_id",
        "dimensions": ["type", "source", "status", "subject_type", "predicate", "object_type", "chemical", "month", "year"],
        "metrics": {"count": ["已接受断言数", "条"]},
        "time_label": "审核时间", "multi": ["chemical"],
        "note": "只纳入当前 approved/modified 记录。包含实体关系与字面量属性，不包含暂存候选或历史审核事件。化学品维度只使用已标注为 chemical 的关系端点。",
    },
    "wiki": {
        "label": "Wiki 条目", "unit": "项", "key": "wiki_id",
        "dimensions": ["page_type", "status", "month", "year"],
        "metrics": {"count": ["唯一条目数", "项"]},
        "time_label": "条目更新时间", "multi": [],
        "note": "按 wiki_id 去重。草稿与已发布分别统计，更新时间不是文献发布时间。",
    },
}
WATCHED = [
    "data/vector_store/index_metadata.json", "data/legacy/chunks_metadata.json",
    "data/knowledge/documents.json", "data/wiki/registry.sqlite",
    "data/news/mirror.sqlite3",
    "data/kg/review/reviewed.jsonl", "data/kg/review/pending.jsonl",
    "data/legacy/reviewed.jsonl", "data/kg/entity_aliases.jsonl",
]


class StaleSnapshot(ValueError):
    pass


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def label(value):
    return TYPE_LABELS.get(str(value or ""), str(value or UNKNOWN))


def day(value):
    if not value or not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
        return dt.date().isoformat()
    except (ValueError, TypeError):
        return None


def safe_url(value):
    from urllib.parse import urlsplit
    try:
        p = urlsplit(value or "")
        return value if p.scheme in ("http", "https") and p.hostname and not p.username and not p.password else None
    except ValueError:
        return None


def quantile(values, p):
    values = sorted(values)
    if not values:
        return None
    at = (len(values) - 1) * p
    lo, hi = math.floor(at), math.ceil(at)
    return values[lo] + (values[hi] - values[lo]) * (at - lo)


def dimension_values(row, field, time_axis="published"):
    if field == "chemical":
        return sorted(set(row.get("chemicals") or [UNKNOWN]))
    if field in ("month", "year"):
        value = row.get("event_date") if time_axis == "event" else row.get("date")
        return [value[:7 if field == "month" else 4] if value else UNKNOWN]
    return [str(row.get(field) or UNKNOWN)]


def metric_value(rows, metric):
    if metric == "count":
        return len({row["id"] for row in rows})
    return sum(row.get(metric, 0) or 0 for row in rows)


def aggregate(rows, dimensions, metric="count", time_axis="published"):
    """Each fact contributes once per group; totals never sum overlapping groups."""
    groups = defaultdict(dict)
    for row in rows:
        for key in itertools.product(*(dimension_values(row, f, time_axis) for f in dimensions)):
            groups[key][row["id"]] = row
    return [{"key": list(key), "value": metric_value(list(facts.values()), metric), "records": len(facts)}
            for key, facts in groups.items()]


def public_row(row):
    return {k: v for k, v in row.items() if not k.startswith("_")}


class DashboardRepository:
    def __init__(self, root, metadata_loader=None, relations_loader=None):
        self.root = Path(root)
        self.metadata_loader = metadata_loader
        self.relations_loader = relations_loader
        self._lock = threading.Lock()
        self._snapshot = None
        self._signature = None

    def signature(self):
        result = []
        for rel in WATCHED:
            p = self.root / rel
            if rel.endswith((".sqlite", ".sqlite3")) and p.exists():
                sql = "SELECT * FROM entries ORDER BY wiki_id" if rel.endswith("registry.sqlite") else "SELECT * FROM articles WHERE removed=0 ORDER BY id"
                rows = self.sqlite_rows(rel, sql)
                content = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                # WAL creation and checkpoints can change file metadata without changing facts.
                # Fingerprint the rows used by this dashboard, including committed WAL rows.
                times = []
                for row in rows:
                    for field in ("updated_at", "published_at"):
                        try:
                            dt = datetime.fromisoformat(str(row.get(field) or "").replace("Z", "+00:00"))
                            if not dt.tzinfo:
                                dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
                            times.append(int(dt.timestamp() * 1e9))
                        except (ValueError, TypeError):
                            pass
                result.append((rel, hashlib.sha256(content.encode()).hexdigest(), max(times) if times else None))
            else:
                result.append((rel, p.stat().st_size, p.stat().st_mtime_ns) if p.exists() else (rel, None, None))
        return tuple(result)

    def sqlite_rows(self, relative, sql):
        p = self.root / relative
        if not p.exists():
            return []
        with closing(sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql)]

    def snapshot(self):
        with self._lock:
            signature = self.signature()
            if self._snapshot is not None and signature == self._signature:
                return self._snapshot
            for attempt in range(2):
                loaded = self._load()
                after = self.signature()
                if after == signature:
                    break
                signature = after
            else:
                raise StaleSnapshot("来源正在更新，请稍后刷新数据快照")
            loaded["snapshot_id"] = hashlib.sha256(repr(signature).encode()).hexdigest()[:20]
            loaded["generated_at"] = datetime.now(timezone.utc).isoformat()
            mtimes = [item[2] for item in signature if item[2]]
            loaded["source_updated_at"] = datetime.fromtimestamp(max(mtimes) / 1e9, timezone.utc).isoformat() if mtimes else None
            self._signature, self._snapshot = signature, loaded
            return loaded

    def _load(self):
        wiki_rows = self.sqlite_rows("data/wiki/registry.sqlite", "SELECT * FROM entries")
        wiki = []
        for r in wiki_rows:
            summary = json.loads(r.get("summary") or "{}")
            wiki.append({"id": str(r["wiki_id"]), "title": r["entity"], "page_type": label(summary.get("page_type")),
                         "type": label(summary.get("page_type")), "status": "已发布" if r.get("published_revision") else "草稿",
                         "date": day(r.get("updated_at")), "source": "Wiki 注册目录", "chemicals": [],
                         "revision": r.get("published_revision") or r.get("draft_revision"), "_search": r["entity"]})
        names = sorted({r["entity"] for r in wiki_rows if json.loads(r.get("summary") or "{}").get("page_type") == "chemical"
                        and 1 <= len(r["entity"]) <= 40}, key=lambda x: (-len(x), x))
        if not names:
            names = ["氨", "甲醇", "液氯", "氢气", "苯", "硫酸"]
        pattern = re.compile("|".join(re.escape(n) for n in names))
        def mentions(text):
            return sorted(set(pattern.findall(text or "")))

        raw = self.metadata_loader() if self.metadata_loader else (
            read_json(self.root / WATCHED[0], []) + read_json(self.root / WATCHED[1], []))
        registry = {str(r.get("doc_id")): r for r in read_json(self.root / "data/knowledge/documents.json", [])}
        docs, chunks, duplicates, missing_ids = {}, {}, 0, 0
        for i, r in enumerate(raw):
            if not r.get("doc_id"):
                missing_ids += 1
                continue
            cid = str(r.get("chunk_id") or "row:" + str(i))
            if cid in chunks:
                duplicates += 1
                continue
            chunks[cid] = r
            did = str(r["doc_id"])
            meta = registry.get(did, {})
            if did not in docs:
                docs[did] = {
                    "id": did, "title": str(r.get("title") or meta.get("title") or did),
                    "type": label(r.get("document_type")), "source": str(meta.get("source") or r.get("source") or UNKNOWN).replace("legacy_hazmat_ai_service", "旧资料导入"),
                    "collection": "旧资料" if did.startswith("LEGACY:") else "原始索引",
                    "date": day(r.get("published_at") or meta.get("published_at")),
                    "chunks": 0, "characters": 0, "evidence": 0, "chemicals": [], "_chem": set(), "_text": [],
                    "_chunk_ids": [], "_search": "", "status": str(r.get("status") or UNKNOWN),
                }
            d = docs[did]
            text = str(r.get("text") or "")
            d["chunks"] += 1
            d["characters"] += len(text)
            d["_chem"].update(mentions(text))
            d["_text"].append(text)
            d["_chunk_ids"].append(cid)
        for d in docs.values():
            d["chemicals"] = sorted(d.pop("_chem"))
            d["_search"] = (d["title"] + "\n" + "\n".join(d.pop("_text"))).casefold()

        relations = []
        if self.relations_loader:
            for item in self.relations_loader():
                if item.get("status") not in ("approved", "modified"):
                    continue
                a = item["assertion"]
                rid = str(a.get("assertion_id") or item.get("assertion_id") or "")
                if not rid:
                    continue
                chemicals = sorted({str(a.get(side + "_label")) for side in ("subject", "object")
                                    if a.get(side + "_type") == "chemical" and a.get(side + "_label")})
                literal = a.get("object_kind") == "literal"
                r = {"id": rid, "title": " ".join(str(a.get(k) or "") for k in ("subject_label", "predicate", "object_label")),
                     "type": "字面量属性" if literal else "实体关系", "source": label(a.get("source_type")),
                     "status": STATUS_LABELS[item["status"]], "date": day(item.get("reviewed_at") or item.get("review", {}).get("reviewed_at")),
                     "subject_type": label(a.get("subject_type")), "object_type": label(a.get("object_type")),
                     "predicate": str(a.get("predicate") or UNKNOWN), "chemicals": chemicals,
                     "doc_id": a.get("source_doc_id"), "chunk_id": a.get("source_chunk_id"),
                     "page_start": a.get("page_start"), "page_end": a.get("page_end"),
                     "quote": a.get("source_text_quote") or "", "_assertion": a, "_search": json.dumps(a, ensure_ascii=False).casefold()}
                relations.append(r)
            relations = list({r["id"]: r for r in relations}.values())
        for r in relations:
            if r.get("doc_id") in docs:
                docs[r["doc_id"]]["evidence"] += 1

        news = []
        for r in self.sqlite_rows("data/news/mirror.sqlite3", "SELECT * FROM articles WHERE removed=0"):
            payload = json.loads(r.get("payload") or "{}")
            text = str(r.get("title") or "") + " " + str(payload.get("summary") or "")
            news.append({"id": str(r["id"]), "title": r["title"], "type": label(r["article_type"]),
                         "source": str(payload.get("source_org") or r.get("source_id") or UNKNOWN),
                         "country": str(payload.get("country") or UNKNOWN),
                         "status": STATUS_LABELS.get(r.get("review_status"), str(r.get("review_status") or UNKNOWN)),
                         "date": day(r.get("published_at")), "event_date": day(r.get("event_at")),
                         "characters": len(text), "chemicals": mentions(text), "url": safe_url(r.get("url")),
                         "summary": str(payload.get("summary") or ""), "_search": text.casefold()})
        data = {"documents": list(docs.values()), "news": news, "relations": relations, "wiki": wiki}
        available = {
            "documents": (self.root / WATCHED[0]).exists() or (self.root / WATCHED[1]).exists(),
            "news": (self.root / "data/news/mirror.sqlite3").exists(),
            "wiki": (self.root / "data/wiki/registry.sqlite").exists(),
            "relations": self.relations_loader is not None,
        }
        return {"data": data, "chunks": chunks, "chemical_names": names, "available": available,
                "quality": {"duplicate_chunk_ids": duplicates, "rows_without_document_id": missing_ids}}

    def bootstrap(self):
        s = self.snapshot()
        specs = {}
        for key, spec in DATASETS.items():
            rows = s["data"][key]
            dims = {}
            for field in spec["dimensions"]:
                counts = Counter(v for r in rows for v in dimension_values(r, field))
                dims[field] = {"label": DIMENSIONS[field], "type": "time" if field in ("month", "year") else "category",
                               "multi": field in spec["multi"], "coverage": round(100 * sum(UNKNOWN not in dimension_values(r, field) for r in rows) / len(rows), 1) if rows else None,
                               "values": [v for v, _ in counts.most_common(250)],
                               "missing": counts.get(UNKNOWN, 0)}
            specs[key] = {**spec, "dimensions": dims, "available": s["available"][key], "total": len(rows),
                          "unknown_date": sum(not r.get("date") for r in rows)}
        return {k: s[k] for k in ("snapshot_id", "generated_at", "source_updated_at", "quality")} | {
            "version": VERSION, "datasets": specs,
            "totals": {"documents": len(s["data"]["documents"]), "chunks": len(s["chunks"]),
                       "news": len(s["data"]["news"]), "wiki": len(s["data"]["wiki"]),
                       "relations": len(s["data"]["relations"])},
            "limitations": [
                "化学品名称提及采用最长名称优先的字面匹配，不能替代已审核实体。",
                "资料来源是已有标签；旧资料的 pdf/docx 是文件格式，不是文献类型。",
                "缺少结构化工艺、位置或事件去重时，相应维度不会显示为已知事实。",
                "未知日期单列；不从文件标题中的年份推测发布时间。",
            ],
        }

    def select(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("查询必须是对象")
        s = self.snapshot()
        if payload.get("snapshot_id") and payload["snapshot_id"] != s["snapshot_id"]:
            raise StaleSnapshot("数据快照已更新，请刷新后重新运行分析")
        dataset = payload.get("dataset", "documents")
        if dataset not in DATASETS:
            raise ValueError("未知数据集")
        if not s["available"][dataset]:
            raise ValueError("该数据集尚未接入")
        spec = DATASETS[dataset]
        dims = payload.get("dimensions", ["type"])
        if not isinstance(dims, list) or not 1 <= len(dims) <= 2 or len(set(dims)) != len(dims):
            raise ValueError("请选择一或两个不同维度")
        if any(f not in spec["dimensions"] for f in dims):
            raise ValueError("所选维度不适用于当前数据集")
        metric = payload.get("metric", "count")
        if metric not in spec["metrics"]:
            raise ValueError("所选指标不适用于当前数据集")
        time_axis = payload.get("time_axis", "published")
        if time_axis not in ("published", "event") or (time_axis == "event" and dataset != "news"):
            raise ValueError("时间口径不适用")
        unknown = payload.get("unknown", "include")
        if unknown not in ("include", "exclude", "only"):
            raise ValueError("未知日期设置无效")
        start, end = payload.get("from") or None, payload.get("to") or None
        for value in (start, end):
            if value and (not isinstance(value, str) or day(value) != value):
                raise ValueError("日期格式须为 YYYY-MM-DD")
        if start and end and start > end:
            raise ValueError("开始日期不能晚于结束日期")
        filters = payload.get("filters", [])
        if not isinstance(filters, list) or len(filters) > 12:
            raise ValueError("筛选数量超出限制")
        for f in filters:
            if not isinstance(f, dict) or f.get("field") not in spec["dimensions"] + ["id"]:
                raise ValueError("筛选字段不适用于当前数据集")
            values = f.get("values")
            if not isinstance(values, list) or not values or len(values) > 250 or any(not isinstance(v, str) or len(v) > 300 for v in values):
                raise ValueError("筛选值无效")
        q = payload.get("q", "")
        if not isinstance(q, str) or len(q) > 200:
            raise ValueError("关键词长度超过限制")
        q = q.casefold().strip()
        rows = []
        for row in s["data"][dataset]:
            date = row.get("event_date") if time_axis == "event" else row.get("date")
            if (unknown == "only" and date) or (unknown == "exclude" and not date):
                continue
            if date and ((start and date < start) or (end and date > end)):
                continue
            if q and q not in row.get("_search", ""):
                continue
            if any(not set(dimension_values(row, f["field"], time_axis)).intersection(f["values"]) for f in filters):
                continue
            rows.append(row)
        return s, dataset, spec, dims, metric, time_axis, rows

    def query(self, payload):
        s, dataset, spec, dims, metric, axis, rows = self.select(payload)
        groups = aggregate(rows, dims, metric, axis)
        temporal = dims[0] in ("month", "year")
        groups.sort(key=lambda g: (tuple(g["key"]) if temporal else (-g["value"], tuple(g["key"]))))
        total_groups = len(groups)
        groups = groups[:500]
        offset, size = int(payload.get("offset", 0)), int(payload.get("size", 25))
        if offset < 0 or size < 1 or size > 100:
            raise ValueError("分页参数无效")
        ordered = sorted(rows, key=lambda r: (r.get("date") or "", r["id"]), reverse=True)
        missing = {f: sum(UNKNOWN in dimension_values(r, f, axis) for r in rows) for f in spec["dimensions"]}
        date_missing = sum(not (r.get("event_date") if axis == "event" else r.get("date")) for r in rows)
        breakdown = {}
        for f in ("type", "source", "collection", "chemical", "country", "page_type", "status"):
            if f in spec["dimensions"]:
                gs = aggregate(rows, [f], "count", axis)
                gs.sort(key=lambda g: (-g["value"], g["key"][0]))
                breakdown[f] = gs[:100]
        numeric = "chunks" if dataset == "documents" else "characters" if dataset == "news" else None
        distribution, scatter = [], []
        if numeric:
            for g in aggregate(rows, [dims[0]], "count", axis)[:12]:
                selected = [r for r in rows if g["key"][0] in dimension_values(r, dims[0], axis)]
                vals = [r.get(numeric, 0) for r in selected]
                q1, q3 = quantile(vals, .25), quantile(vals, .75)
                low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
                inner = [v for v in vals if low <= v <= high]
                distribution.append({"name": g["key"][0], "n": len(vals),
                                     "box": [min(inner), q1, quantile(vals, .5), q3, max(inner)],
                                     "outliers": [v for v in vals if v < low or v > high][:80]})
            scatter = [{"id": r["id"], "name": r["title"], "type": r["type"],
                        "x": r.get("chunks", len(r.get("chemicals", []))), "y": r.get("characters", 0)}
                       for r in sorted(rows, key=lambda r: (-r.get("characters", 0), r["id"]))[:300]]
        histogram = []
        if numeric:
            all_values = [r.get("characters", 0) for r in rows]
            if all_values:
                step = max(1, math.ceil(max(all_values) / 8))
                for i in range(8):
                    histogram.append({"from": i * step, "to": (i + 1) * step,
                                      "value": sum(i * step <= v and (v <= (i + 1) * step if i == 7 else v < (i + 1) * step) for v in all_values)})
        timeline = aggregate([r for r in rows if (r.get("event_date") if axis == "event" else r.get("date"))], ["month", "type"], "count", axis)
        timeline.sort(key=lambda g: g["key"])
        tree = []
        if "source" in spec["dimensions"] and "type" in spec["dimensions"]:
            for g in aggregate(rows, ["type", "source"], metric, axis):
                tree.append({"type": g["key"][0], "source": g["key"][1], "value": g["value"], "records": g["records"]})
        links = []
        if dataset in ("documents", "news"):
            left = "collection" if dataset == "documents" else "country"
            for pair in [(left, "type"), ("type", "source")]:
                for g in aggregate(rows, list(pair), metric, axis):
                    links.append({"source": pair[0] + "|" + g["key"][0], "target": pair[1] + "|" + g["key"][1], "value": g["value"]})
        network = {"nodes": [], "links": [], "total_links": 0}
        if dataset == "relations":
            nodes = {}
            edges = []
            for r in rows:
                a = r["_assertion"]
                if a.get("object_kind") == "literal":
                    continue
                for side in ("subject", "object"):
                    identity = str(a.get(side + "_id") or "")
                    if identity:
                        nodes[identity] = {"id": identity, "name": a.get(side + "_label") or identity, "category": label(a.get(side + "_type"))}
                if a.get("subject_id") and a.get("object_id"):
                    edges.append({"source": a["subject_id"], "target": a["object_id"], "name": a.get("predicate") or "", "id": r["id"]})
            network = {"nodes": list(nodes.values())[:200], "links": edges[:300], "total_links": len(edges)}
        passport = {
            "dataset": spec["label"], "grain": spec["key"], "metric": spec["metrics"][metric][0],
            "unit": spec["metrics"][metric][1], "dimensions": [DIMENSIONS[d] for d in dims],
            "time": "事件日期" if axis == "event" else spec["time_label"],
            "dedup_key": spec["key"], "denominator": len(rows), "before_filter": len(s["data"][dataset]),
            "unknown_dates": date_missing, "missing": missing, "multi_label": any(d in spec["multi"] for d in dims),
            "note": spec["note"], "filters": payload.get("filters", []), "keyword": payload.get("q", ""), "date_from": payload.get("from"), "date_to": payload.get("to"),
            "unknown_policy": {"include": "未知日期单列保留", "exclude": "已排除未知日期", "only": "只看未知日期"}[payload.get("unknown", "include")],
            "version": VERSION, "snapshot_id": s["snapshot_id"], "source_updated_at": s["source_updated_at"],
            "display_limit": "聚合最多500组，散点展示字符数最高的300条，网络最多200节点/300边；总计仍按完整筛选集合",
        }
        return {"snapshot_id": s["snapshot_id"], "generated_at": s["generated_at"], "dataset": dataset,
                "dimensions": dims, "metric": metric, "total": len(rows), "value": metric_value(rows, metric),
                "groups": groups, "marginals": [aggregate(rows, [d], metric, axis) for d in dims], "marginals_by_field": {d: aggregate(rows, [d], metric, axis) for d in spec["dimensions"]}, "group_count": total_groups, "truncated_groups": max(0, total_groups - 500),
                "details": [public_row(r) for r in ordered[offset:offset + size]], "offset": offset, "size": size,
                "breakdown": breakdown, "distribution": distribution, "scatter": scatter,
                "timeline": timeline, "histogram": histogram, "tree": tree, "sankey": links, "network": network, "passport": passport}

    def detail(self, dataset, identity, snapshot_id=None, offset=0):
        s = self.snapshot()
        if snapshot_id and snapshot_id != s["snapshot_id"]:
            raise StaleSnapshot("数据快照已更新，请刷新后重新打开明细")
        if dataset not in DATASETS:
            raise ValueError("未知数据集")
        row = next((r for r in s["data"][dataset] if r["id"] == identity), None)
        if row is None:
            return None
        result = public_row(row)
        if dataset == "documents":
            ids = row["_chunk_ids"]
            result["fragments"] = [{
                "id": cid, "text": s["chunks"][cid].get("text") or "",
                "page_start": s["chunks"][cid].get("page_start"), "page_end": s["chunks"][cid].get("page_end"),
                "section": s["chunks"][cid].get("section_title") or "",
            } for cid in ids[offset:offset + 20]]
            result["fragment_total"] = len(ids)
            result["offset"] = offset
            result["accepted_assertions"] = [public_row(r) for r in s["data"]["relations"] if r.get("doc_id") == identity]
        result["snapshot_id"] = s["snapshot_id"]
        return result
