"""Read-only file descriptions, exact column profiles and real sample rows."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import hashlib
import json
import math
import threading

from core.dashboard import StaleSnapshot, quantile, day

FILES = [
    dict(id="main_chunks", name="index_metadata.json", label="主资料片段", group="可分析的数据文件", format="JSON", path="data/vector_store/index_metadata.json",
         about="标准、法规和事故报告的原文片段。文件最外层是数组，每个对象是一段文本，保留所属文档、类型、原文和已有页码。它是检索与来源追溯的基础。",
         grain="一行一个原文片段", note="片段行数不是文档数；同一 doc_id 对应多段文本。发布日期不在这些字段中，标题年份不能当作发布日期。"),
    dict(id="legacy_chunks", name="chunks_metadata.json", label="旧资料片段", group="可分析的数据文件", format="JSON", path="data/legacy/chunks_metadata.json",
         about="旧资料导入后的文本片段数组。每行包含原文件名称、格式类别、段落文本及顺序。doc_id 与 chunk_id 使用 LEGACY 前缀。",
         grain="一行一个旧资料片段", note="document_type 在这里表示 PDF、DOCX、DOC、Markdown 等文件格式；原页码缺失时，不从段落顺序推算页码。"),
    dict(id="document_registry", name="documents.json", label="文档目录", group="可分析的数据文件", format="JSON", path="data/knowledge/documents.json",
         about="登记资料文档的目录数组，包含标题、编号、来源标签、PDF 路径和片段数量。用 doc_id 与原文片段关联。",
         grain="一行一个目录记录", note="目录只覆盖已登记资料，不等同于全库文档总数。pdf_path 的 nan 等占位值表示尚未提供可用文件路径。"),
    dict(id="news_table", name="mirror.sqlite3 / articles", label="新闻文章表", group="可分析的数据文件", format="SQLite 表", path="data/news/mirror.sqlite3",
         about="新闻镜像数据库中的 articles 表。记录文章标题、来源、原站网址、发布日期、事件日期、分类及复核状态；payload 为附加内容的 JSON 字符串。",
         grain="一行一篇未移除文章", note="只展示 removed=0 的文章。published_at 是文章发布日期，event_at 是事件日期，二者不能替代；payload 中的来源国家不能当作事故地点。"),
    dict(id="review_main", name="reviewed.jsonl", label="主知识审核记录", group="可分析的数据文件", format="JSONL", path="data/kg/review/reviewed.jsonl",
         about="追加保存的知识断言审核历史。文件每一行是一个 JSON 对象，包含断言内容、审核决定、审核时间和引用依据；同一断言可出现多次。",
         grain="一行一次审核记录", note="历史审核行数不等于当前已接受断言数。Dashboard 使用当前 approved / modified 状态，此处保留原始历史结构。"),
    dict(id="review_legacy", name="legacy / reviewed.jsonl", label="旧知识审核记录", group="可分析的数据文件", format="JSONL", path="data/legacy/reviewed.jsonl",
         about="旧系统导入的知识审核记录。结构同样为一行一个 JSON 对象，断言内部可能包含主体、关系、客体及原文引句。",
         grain="一行一个导入审核记录", note="与主审核记录共同形成当前知识目录，不能直接把两份文件的行数相加作为已接受知识数量。"),
    dict(id="wiki_table", name="registry.sqlite / entries", label="Wiki 条目目录", group="可分析的数据文件", format="SQLite 表", path="data/wiki/registry.sqlite",
         about="Wiki 注册目录中的 entries 表。每条记录连接条目名称、唯一 ID、草稿或发布修订以及更新时间；summary 保存条目类型等 JSON 信息。",
         grain="一行一个注册条目", note="条目更新时间不是参考文献的发表日期。存在草稿修订不表示已经发布，正文存放在条目文件中。"),
    dict(id="knowledge_schema", name="schema_v1.json", label="知识结构定义", group="可分析的数据文件", format="JSON 对象", path="data/kg/schema_v1.json",
         about="实体类型、关系类型、审核约束及来源追溯规则的结构定义。最外层是一个 JSON 对象，entity_types 与 relation_types 等字段内部仍是嵌套结构。",
         grain="一行展示完整定义对象", note="这是结构配置，不是事实记录集合；实体类型数量不能当作实际实体数量。嵌套字段可点击样例查看 JSON。"),
]
DOC_CLASSES = [
    ("standard_pdf", "标准文件（PDF）", "标准", "PDF", "标准 PDF 通常包含封面、编号、适用范围、术语、条款、表格及附录。固定版面利于按已有页码追溯；扫描页可能需要 OCR。"),
    ("regulation_pdf", "法规文件（PDF）", "法规", "PDF", "法规 PDF 常包含发布或修订说明、章节和条款。原文中的日期可能指立法、施行或修订时间，不能自动当作这份文件的发布日期。"),
    ("accident_pdf", "事故报告（PDF）", "事故报告", "PDF", "事故报告 PDF 通常以事故经过、原因分析、人员损失、责任认定和整改建议组织内容。正文中的事故时间需要单独标注后才能做事件分析。"),
    ("legacy_pdf", "旧资料（PDF）", "旧资料 · PDF", "PDF", "旧资料中的 PDF 采用固定页面版式，可能含扫描图、表格或应急预案。当前导入保留了文本片段；部分记录未保留原页码。"),
    ("legacy_docx", "旧资料（DOCX）", "旧资料 · DOCX", "DOCX", "DOCX 是可编辑的 Word 文档，常由标题、段落、列表和表格组成。导入后的文本按段落或主题组织；段落顺序不等于 Word 排版页码。"),
    ("legacy_doc", "旧资料（DOC）", "旧资料 · DOC", "DOC", "DOC 是旧版 Word 格式，常见于历史制度、操作规程和预案。页面、嵌入对象与表格经转换后可能呈现为文本片段，阅读时应结合原资料核对。"),
    ("legacy_md", "旧资料（Markdown）", "旧资料 · Markdown", "Markdown", "Markdown 是纯文本格式，使用标题标记、列表、链接和表格语法表达层次。没有固定分页；当前预览展示保留在索引中的文本。"),
]
for key, name, doc_type, fmt, about in DOC_CLASSES:
    FILES.append(dict(id=key, name=name, label=name, group="原始资料类别", format=fmt, doc_type=doc_type, path=None, about=about,
                      grain="一行一份已索引文档", note="这里展示文档索引及真实原文片段样例，不是原始二进制文件的行列。记录数按文档 ID 去重；未读取原文件，文件体积不适用。"))
DEFINITIONS = {d["id"]: d for d in FILES}
FIELD_HELP = {
    "chunk_id": ("片段 ID", "原文片段的标识，可与来源引用关联。"),
    "doc_id": ("文档 ID", "所属文档的标识。同一文档可包含多个片段。"),
    "assertion_id": ("断言 ID", "断言标识。同一个断言可能有多次审核记录。"),
    "wiki_id": ("条目 ID", "Wiki 条目唯一标识。"),
    "id": ("文章 ID", "镜像文章的记录标识，按标识处理，不计算均值。"),
    "title": ("标题 / 文件名称", "来源中保留的标题或原文件名称。"),
    "entity": ("条目名称", "注册的 Wiki 条目名称。"),
    "text": ("原文片段", "导入或解析时保留的原始文本，不代表整份资料。"),
    "sample_text": ("原文样例", "该文档的首个已索引片段，保持来源文本。"),
    "sample_page": ("样例起始页", "样例片段的已有起始页码，缺失时不推测。"),
    "source": ("来源标签", "资料目录中的来源标签，不一定是发布机构。"),
    "source_id": ("新闻来源 ID", "新闻站点或来源目录的标识。"),
    "source_file": ("来源文件", "原解析记录中提供的文件名称。"),
    "source_path": ("来源路径", "原解析记录中提供的文件路径。"),
    "document_type": ("资料类型 / 格式", "主资料表示标准、法规等内容类别；旧资料表示 PDF、DOCX 等格式。"),
    "doc_type": ("类型补充", "部分来源记录提供的额外类型字段。"),
    "code": ("资料编号", "标准编号或法规公告编号；非所有资料都有编号。"),
    "status": ("记录状态", "保留来源系统的状态值，具体含义应结合该文件用途理解。"),
    "review_status": ("复核状态", "新闻来源系统的复核状态，不等于事件已证实。"),
    "reviewed_at": ("审核时间", "这次审核记录的时间。"),
    "reviewed_by": ("审核者", "原审核记录中保存的审核标识。"),
    "page_start": ("起始页", "原片段保留的起始页码。"),
    "page_end": ("结束页", "原片段保留的结束页码。"),
    "char_count": ("片段字符数", "来源记录保存的字符数量。"),
    "characters": ("片段字符总数", "此文档各唯一片段的文本长度之和。"),
    "chunks": ("片段数量", "此文档关联的片段数量。"),
    "ordinal": ("片段顺序", "旧资料片段的顺序号，不是页码。"),
    "section": ("章节", "解析记录提供的章节名称。"),
    "section_title": ("段落 / 主题标题", "旧资料片段对应的主题名称。"),
    "quality": ("来源质量标签", "解析或导入时写入的标签，不等同于内容正确率。"),
    "content_hash": ("内容指纹", "用于辨识文本内容的哈希值。"),
    "pdf_path": ("PDF 路径", "目录记录保存的原文件路径，可能缺失或为占位值。"),
    "url": ("原站网址", "原新闻文章的网址。"),
    "published_at": ("文章发布日期", "文章发布时间，不是事故发生日期。"),
    "event_at": ("事件日期", "单独提供的事件发生时间；不能用文章日期补齐。"),
    "article_type": ("文章分类", "来源系统对报道内容的分类。"),
    "payload": ("附加内容 JSON", "新闻摘要、来源机构等附加信息，以 JSON 字符串存储。"),
    "summary": ("条目摘要 JSON", "Wiki 条目类型等信息，以 JSON 字符串存储。"),
    "removed": ("移除标记", "新闻表中的移除状态，此预览仅包含未移除记录。"),
    "updated_at": ("更新时间", "记录更新时间，不等于原文发表时间。"),
    "draft_revision": ("草稿修订", "当前草稿的修订标识。"),
    "published_revision": ("发布修订", "当前已发布的修订标识；缺失表示尚未发布。"),
    "assertion": ("断言对象", "主体、关系、客体和来源证据等嵌套字段。"),
    "schema_version": ("结构版本", "当前知识结构定义的版本。"),
    "entity_types": ("实体类型定义", "实体类别、说明及约束的嵌套结构。"),
    "relation_types": ("关系类型定义", "关系类别及适用对象的嵌套结构。"),
}
NUMBERS = {"page_start", "page_end", "sample_page", "char_count", "characters", "chunks", "ordinal", "removed"}
IDS = {"id", "doc_id", "chunk_id", "wiki_id", "assertion_id", "source_id", "content_hash", "draft_revision", "published_revision"}
DATES = {"published_at", "event_at", "updated_at", "reviewed_at", "created_at", "finalized_at"}
TEXTS = {"text", "sample_text", "title", "source_path", "source_file", "section", "section_title", "pdf_path", "url"}
TYPES = {"identifier": "标识", "number": "数值", "date": "日期 / 时间", "text": "文本", "category": "类别", "object": "对象", "array": "数组", "boolean": "布尔", "json": "JSON 字符串"}


def missing(v, field=""):
    return v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {} or (field == "pdf_path" and isinstance(v, str) and v.casefold() in {"nan", "none", "null"})


def kind(field, values):
    if field in IDS or field.endswith("_id"): return "identifier"
    if field in NUMBERS: return "number"
    if field in DATES or field.endswith("_at"): return "date"
    if field in ("payload", "summary"): return "json"
    if field in TEXTS: return "text"
    if not values: return "text"
    types = Counter("boolean" if isinstance(v, bool) else "number" if isinstance(v, (int, float)) else "object" if isinstance(v, dict) else "array" if isinstance(v, list) else "category" for v in values)
    return types.most_common(1)[0][0]


def valid(v, typ):
    if typ == "number": return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    if typ == "date": return isinstance(v, str) and day(v) is not None
    if typ == "identifier": return isinstance(v, (str, int)) and not isinstance(v, bool)
    if typ == "object": return isinstance(v, dict)
    if typ == "array": return isinstance(v, list)
    if typ == "boolean": return isinstance(v, bool)
    if typ == "json":
        try: json.loads(v); return isinstance(v, str)
        except (TypeError, ValueError): return False
    return isinstance(v, str)


def canonical(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def bins(values, count=10):
    if not values: return []
    lo, hi = min(values), max(values)
    if hi == lo: return [dict(start=lo, end=hi, count=len(values))]
    width = (hi - lo) / count
    counts = [0] * count
    for v in values: counts[min(count-1, int((v-lo)/width))] += 1
    return [dict(start=lo+i*width, end=lo+(i+1)*width, count=n) for i, n in enumerate(counts)]


def profile(rows, field):
    vals = [r.get(field) for r in rows]
    known = [v for v in vals if not missing(v, field)]
    typ = kind(field, known)
    ok = [v for v in known if valid(v, typ)]
    identities = Counter(canonical(v) for v in ok)
    label, desc = FIELD_HELP.get(field, (field.replace("_", " "), "来源中实际保存的字段；未配置专门的业务含义，请结合样例核对。"))
    result = dict(name=field, label=label, description=desc, type=typ, type_label=TYPES[typ],
                  total=len(rows), valid=len(ok), missing=len(vals)-len(known), mismatched=len(known)-len(ok),
                  unique=len(identities), most_common=[], histogram=[], statistics=None, profile_basis="全部当前表记录")
    if typ == "number" and ok:
        avg = sum(ok)/len(ok)
        result["statistics"] = dict(mean=avg, std=math.sqrt(sum((v-avg)**2 for v in ok)/len(ok)),
                                   quantiles=[min(ok), quantile(ok,.25), quantile(ok,.5), quantile(ok,.75), max(ok)])
        result["histogram"] = bins(ok)
        result["distribution_label"] = "有效数值的分布"
    elif typ in ("text", "json", "object", "array") and ok:
        lengths = [len(v) if isinstance(v, str) else len(canonical(v)) for v in ok]
        result["histogram"] = bins(lengths)
        result["distribution_label"] = "文本 / JSON 字符长度分布"
        result["length_range"] = [min(lengths), max(lengths)]
    elif typ == "date" and ok:
        dates = Counter(day(v)[:7] for v in ok)
        result["most_common"] = [dict(value=k, count=n) for k,n in sorted(dates.items())]
        result["distribution_label"] = "已知日期按月份分布"
    elif typ in ("category", "boolean"):
        result["most_common"] = [dict(value=json.loads(k), count=n) for k,n in identities.most_common(5)]
        result["distribution_label"] = "高频值（占全部记录的比例）"
    if identities:
        value, count = identities.most_common(1)[0]
        result["most_common_value"] = str(json.loads(value))[:100]
        result["most_common_count"] = count
    if typ == "identifier": result["distribution_label"] = "标识按不同值计数，不作数值运算"
    return result


class FileCatalog:
    def __init__(self, repo):
        self.repo = repo
        self.root = repo.root
        self.lock = threading.RLock()
        self.revision = None
        self.cache = {}

    def context(self, requested=None):
        snapshot = self.repo.snapshot()
        schema = self.root / "data/kg/schema_v1.json"
        stamp = (schema.stat().st_size, schema.stat().st_mtime_ns) if schema.exists() else None
        revision = hashlib.sha256(repr((snapshot["snapshot_id"], stamp)).encode()).hexdigest()[:20]
        if requested and requested != revision: raise StaleSnapshot("文件数据已更新，请更新数据说明快照后继续浏览")
        if revision != self.revision:
            with self.lock:
                self.cache = {}
                self.revision = revision
        return snapshot, revision

    def load(self, key, snapshot):
        d = DEFINITIONS[key]
        if "doc_type" in d:
            rows = []
            for doc in snapshot["data"]["documents"]:
                if doc["type"] != d["doc_type"]: continue
                chunk = snapshot["chunks"].get(doc["_chunk_ids"][0], {}) if doc["_chunk_ids"] else {}
                rows.append(dict(doc_id=doc["id"], title=doc["title"], document_type=doc["type"], source=doc["source"],
                                 chunks=doc["chunks"], characters=doc["characters"], sample_page=chunk.get("page_start"), sample_text=chunk.get("text", "")))
            return rows
        p = self.root / d["path"]
        if not p.is_file(): return []
        if key == "news_table": return self.repo.sqlite_rows(d["path"], "SELECT * FROM articles WHERE removed=0 ORDER BY id")
        if key == "wiki_table": return self.repo.sqlite_rows(d["path"], "SELECT * FROM entries ORDER BY wiki_id")
        if d["format"] == "JSONL":
            rows = []
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip(): continue
                row = json.loads(line)
                if not isinstance(row, dict): raise ValueError("JSONL 记录必须是对象")
                rows.append(row)
            return rows
        content = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(content, dict): return [content]
        if not isinstance(content, list) or any(not isinstance(row, dict) for row in content): raise ValueError("JSON 数据结构不符合文件定义")
        return content

    def prepared(self, key, snapshot, revision):
        if key not in DEFINITIONS: raise ValueError("文件类别不存在")
        with self.lock:
            if key not in self.cache:
                rows = self.load(key, snapshot)
                fields = list(dict.fromkeys(field for row in rows for field in row))
                ordered = ["doc_id","chunk_id","id","wiki_id","assertion_id","title","entity","document_type","source","source_id","page_start","page_end","char_count","text","sample_text"]
                fields = [f for f in ordered if f in fields] + [f for f in fields if f not in ordered]
                profiles = [profile(rows, f) for f in fields]
                self.context(revision)
                self.cache[key] = (rows, profiles)
            return self.cache[key]

    def list(self):
        snapshot, revision = self.context()
        entries = []
        for d in FILES:
            rows = self.load(d["id"], snapshot) if "doc_type" in d else None
            if "doc_type" in d:
                available, total = bool(rows), len(rows)
            else:
                available = (self.root/d["path"]).is_file()
                if d["id"] == "news_table": total=len(snapshot["data"]["news"])
                elif d["id"] == "wiki_table": total=len(snapshot["data"]["wiki"])
                else: total=len(self.load(d["id"], snapshot)) if available else None
            entries.append({**d, "available":available, "rows":total,
                            "bytes":(self.root/d["path"]).stat().st_size if d["path"] and available else None})
        self.context(revision)
        return dict(files=entries, catalog_revision=revision, snapshot_id=snapshot["snapshot_id"],
                    note="字段统计基于完整当前表记录；下方样例为分页预览。标识列不计算均值，未知值不参与有效值分布。")

    def detail(self, key, revision=None, offset=0, size=20, sort=None, descending=False):
        snapshot, revision = self.context(revision)
        rows, columns = self.prepared(key, snapshot, revision)
        if offset < 0 or size < 1 or size > 100: raise ValueError("预览分页参数无效")
        names = {c["name"] for c in columns}
        if sort and sort not in names: raise ValueError("排序字段不存在")
        selected = rows
        if sort:
            def sortkey(r):
                v=r.get(sort)
                return (missing(v,sort), 0 if isinstance(v,(float,int)) and not isinstance(v,bool) else 1, v if isinstance(v,(float,int)) and not isinstance(v,bool) else canonical(v))
            selected=sorted(rows,key=sortkey,reverse=descending)
        d=DEFINITIONS[key]
        self.context(revision)
        return dict(file={**d,"bytes":(self.root/d["path"]).stat().st_size if d["path"] and (self.root/d["path"]).is_file() else None},
                    catalog_revision=revision, snapshot_id=snapshot["snapshot_id"], total=len(rows),
                    columns=columns, rows=selected[offset:offset+size], offset=offset, size=size,
                    invalid_type_rule="数值列要求有限数字；日期要求可解析的日期或时间；标识不参与数值运算。未声明字段按非空值中的主要类型检查。",
                    preview_json=json.dumps(rows[0],ensure_ascii=False,indent=2)[:4500] if rows else None)
