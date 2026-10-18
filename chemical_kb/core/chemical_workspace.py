"""Chemical-centered workflow with real sources and CPU-only extractive drafts."""
import copy
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from flask import jsonify, request, send_file
from core.source_files import resolve_source
from core.wiki.citations import SECTIONS
from core.wiki.repository import NotFound, safe_entity

def extractive_sections(payload):
    evidence = payload["evidence"]
    result = []
    for source in payload["sections"]:
        selected = [e for e in evidence if e["evidence_id"] in source.get("evidence_refs", [])][:4]
        if not selected:
            result.append({"section": source["section"], "content": "本节暂无已绑定的原文摘录，需要补充资料后人工核实。",
                           "knowledge_blocks": [{"text": "本节暂无已绑定的原文摘录，需要补充资料后人工核实。", "knowledge_source": "model_prior", "evidence_ids": []}]})
            continue
        blocks = []
        for i, item in enumerate(selected, 1):
            m = item["metadata"]
            text = str(m.get("text") or "").strip()
            content = "**" + str(m.get("title") or "原文资料") + "**（来源页码：" + str(m.get("page_start") or "未记录") + "）\n\n" + text + " [Wiki证据" + str(i) + "]"
            blocks.append({"text": content, "knowledge_source": "grounded", "evidence_ids": [i]})
        result.append({"section": source["section"], "content": "\n\n".join(b["text"] for b in blocks), "knowledge_blocks": blocks,
                       "evidence": [{"metadata": copy.deepcopy(e["metadata"])} for e in selected]})
    return result

def register(app, service, metadata_provider, reviews_provider, graph_provider, base):
    base = Path(base)
    platform = app.extensions["wiki_platform"]

    def document_rows(docid):
        rows = [m for m in metadata_provider() if m.get("doc_id") == docid]
        if not rows:
            rows = [m for m in platform.corpus() if m.get("doc_id") == docid]
        return rows

    @app.get("/api/documents/<path:docid>/detail")
    def chemical_document_detail(docid):
        rows = document_rows(docid)
        if not rows:
            return jsonify(error="资料不存在"), 404
        path = resolve_source(base, rows[0])
        return jsonify(doc_id=docid, title=rows[0].get("title"), code=rows[0].get("code"), chunks=rows,
                       file_available=bool(path), file_type=path.suffix[1:] if path else None,
                       source_url="/api/documents/" + quote(docid, safe="") + "/source" if path else None)

    @app.get("/api/documents/<path:docid>/source")
    def chemical_document_source(docid):
        rows = document_rows(docid)
        if not rows:
            return jsonify(error="资料不存在"), 404
        path = resolve_source(base, rows[0])
        if not path:
            return jsonify(error="未找到唯一对应的原文件，请先阅读已保存的原文摘录。"), 404
        return send_file(path, as_attachment=path.suffix.lower() != ".pdf", download_name=path.name)

    @app.get("/api/chemical/<entity>")
    def chemical_summary(entity):
        try:
            entity = safe_entity(entity)
            p = service.detail(entity)
        except (NotFound, ValueError):
            return jsonify(error="化学品条目不存在"), 404
        docs = {}
        for item in p["evidence"]:
            m = item["metadata"]
            docid = m.get("doc_id")
            if not docid:
                continue
            if docid not in docs:
                path = resolve_source(base, m)
                docs[docid] = {"doc_id": docid, "title": m.get("title"), "code": m.get("code"),
                              "source": m.get("source"), "document_type": m.get("document_type"),
                              "file_available": bool(path), "file_type": path.suffix[1:] if path else None,
                              "source_url": "/api/documents/" + quote(docid, safe="") + "/source" if path else None,
                              "evidence_count": 0, "pages": []}
            docs[docid]["evidence_count"] += 1
            if m.get("page_start") not in docs[docid]["pages"]:
                docs[docid]["pages"].append(m.get("page_start"))
        from core.kg.relation_catalog import current_relations
        reviewed, pending = reviews_provider()
        relations = [r for r in current_relations(reviewed, pending)
                     if entity in " ".join(str(r["assertion"].get(k) or "") for k in ("subject_label", "object_label", "source_text_quote"))]
        from core import news_store
        news = news_store.list_articles({"q": entity, "size": 10})
        graph = graph_provider("approved")
        graph_ids = {n["id"] for n in graph["nodes"] if entity in n["label"]}
        return jsonify(entity=entity, profile=p.get("chemical_profile", {}), revision=p["revision_id"],
                       is_published=p["is_published"], freshness=p["freshness"],
                       sections=[{"section": s["section"], "review_status": s["review_status"],
                                  "evidence_count": len(s.get("evidence_refs", [])),
                                  "sources": dict(Counter(b.get("knowledge_source") for b in s.get("knowledge_blocks", [])))}
                                 for s in p["sections"]],
                       evidence_count=len(p["evidence"]), documents=list(docs.values()),
                       relations=relations, graph_node_ids=sorted(graph_ids),
                       news=news["items"], news_total=news["total"], accidents=p.get("accident_reading", []),
                       external_sources=p.get("external_sources", []), requirements=platform.requirements(),
                       tasks=[t for t in platform.tasks() if t["kind"].startswith("source_draft")][:10])

    @app.post("/api/chemical/<entity>/draft")
    def chemical_source_draft(entity):
        try:
            p = service.repo.read(safe_entity(entity))
            data = request.get_json(silent=True) or {}
            title = safe_entity(data.get("title") or (entity + "（原文摘录专题）"))
            if title == entity:
                raise ValueError("请使用新的专题名称，保留原化学品条目。")
            try:
                service.repo.entry(title)
                return jsonify(error="同名专题已存在，请打开已有草稿或更换名称。", entity=title), 409
            except NotFound:
                pass
            source_sections = extractive_sections(p)
            def work(task_id):
                for i, _ in enumerate(source_sections, 1):
                    platform.progress(task_id, i)
                saved = platform.commit(title, source_sections, extra={
                    "page_type": "topic", "generation_backend": "cpu_extractive",
                    "source_entity": entity, "source_revision": p["revision_id"],
                    "product_scope": "由绑定原文建立的摘录专题；不调用生成模型，不替代人工核实。",
                    "chemical_profile": p.get("chemical_profile", {})}, reason="source_excerpt_draft")
                return {"entity": title, "revision": saved["revision_id"], "automatic_approval": False}
            task = platform.task("source_draft:" + entity, work, len(source_sections))
            return jsonify(task_id=task["task_id"], entity=title, generation_backend="cpu_extractive"), 202
        except (ValueError, NotFound) as exc:
            return jsonify(error=str(exc)), 400

