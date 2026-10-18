"""Flask binding for the shared Wiki service. No GPU model is created by a request."""
import json
from pathlib import Path
from flask import jsonify, request, send_file
from .citations import SECTIONS
from .jobs import Jobs
from .repository import Conflict, NotFound
from .service import WikiService

def register(app,root=None):
    service=WikiService(root);jobs=Jobs(service.repo)
    app.extensions["wiki_v2"]=service
    def guarded(fn):
        def wrapped(*args,**kwargs):
            try:return fn(*args,**kwargs)
            except Conflict as exc:return jsonify(error=str(exc),error_code="revision_conflict"),409
            except NotFound as exc:return jsonify(error=str(exc),error_code="not_found"),404
            except (ValueError,TypeError) as exc:return jsonify(error=str(exc),error_code="invalid_request"),400
        wrapped.__name__=fn.__name__
        return wrapped
    def create(entity):
        data=request.get_json(silent=True) or {}
        sections=data.get("sections") or SECTIONS
        if not isinstance(sections,list) or not sections or any(s not in SECTIONS for s in sections) or len(set(sections))!=len(sections):
            raise ValueError("请选择规范章节，不能重复")
        data={**data,"sections":sections}
        return jsonify(job=jobs.create(entity,data)),202

    @app.get("/api/wiki")
    @guarded
    def wiki_v2_list():
        entries=service.list();return jsonify(entities=[e["entity"] for e in entries],entries=entries,sections=SECTIONS)
    @app.get("/api/wiki/jobs")
    @guarded
    def wiki_v2_jobs():
        return jsonify(jobs=jobs.list())
    @app.post("/api/wiki/jobs")
    @guarded
    def wiki_v2_create():
        return create((request.get_json(silent=True) or {}).get("entity"))
    @app.get("/api/wiki/jobs/<job_id>")
    @guarded
    def wiki_v2_job(job_id):
        return jsonify(job=jobs.get(job_id))
    @app.post("/api/wiki/jobs/<job_id>/<action>")
    @guarded
    def wiki_v2_job_action(job_id,action):
        if action=="cancel":return jsonify(job=jobs.cancel(job_id))
        if action=="retry":return jsonify(job=jobs.retry(job_id))
        raise NotFound("任务操作不存在")
    @app.get("/api/wiki/lint")
    @guarded
    def wiki_v2_lint():
        return jsonify(findings=service.lint())
    @app.get("/api/wiki/search")
    @guarded
    def wiki_v2_search():
        return jsonify(results=service.search(request.args.get("q",""),mode=request.args.get("mode","wiki")))
    @app.get("/api/wiki/<entity>")
    @guarded
    def wiki_v2_detail(entity):
        return jsonify(service.detail(entity,request.args.get("view","draft"),request.args.get("revision")))
    @app.post("/api/wiki/<entity>/generate")
    @guarded
    def wiki_v2_generate(entity):
        return create(entity)
    @app.post("/api/wiki/<entity>/refresh")
    @guarded
    def wiki_v2_refresh(entity):
        return create(entity)
    @app.post("/api/wiki/<entity>/review")
    @guarded
    def wiki_v2_review(entity):
        return jsonify(record=service.review(entity,request.get_json(silent=True) or {}))
    @app.post("/api/wiki/<entity>/publish")
    @guarded
    def wiki_v2_publish(entity):
        return jsonify(entry=service.publish(entity,request.get_json(silent=True) or {}))
    @app.post("/api/wiki/<entity>/rollback")
    @guarded
    def wiki_v2_rollback(entity):
        return jsonify(entry=service.publish(entity,request.get_json(silent=True) or {},rollback=True))
    @app.get("/api/wiki/<entity>/compare")
    @guarded
    def wiki_v2_compare(entity):
        return jsonify(service.compare(entity,request.args.get("before"),request.args.get("after")))
    @app.get("/api/wiki/<entity>/evidence/<evidence_id>/pdf")
    @guarded
    def wiki_v2_pdf(entity,evidence_id):
        import os
        base=Path(os.environ.get("CHEM_KB_BASE_DIR","/root/autodl-tmp/chemical_kb"))
        payload=service.repo.read(entity,request.args.get("revision"))
        item=next((e for e in payload["evidence"] if e["evidence_id"]==evidence_id),None)
        if not item:raise NotFound("此版本没有该证据")
        from core.source_files import resolve_source
        candidate=resolve_source(base,item["metadata"],pdf_only=True)
        if candidate:
            return send_file(candidate,mimetype="application/pdf",as_attachment=False)
        raise NotFound("原 PDF 尚未关联或来源为其他格式；请核对原文摘录或在化学品专题下载原文件。")
    @app.get("/api/wiki/<entity>/history")
    @guarded
    def wiki_v2_history(entity):
        return jsonify(service.repo.history(entity))
    @app.get("/api/wiki/<entity>/export")
    @guarded
    def wiki_v2_export(entity):
        view=request.args.get("view","published")
        if view=="published" and not service.repo.entry(entity)["published_revision"]:
            raise NotFound("此条目尚未发布，请选择草稿导出")
        p=service.detail(entity,view,request.args.get("revision"))
        from flask import Response
        header="---\n"+ "\n".join(k+": "+json.dumps(v,ensure_ascii=False) for k,v in {
            "title":p["entity"],"wiki_id":p["wiki_id"],"revision_id":p["revision_id"],"view":p["view"],
            "created_at":p["created_at"],"freshness":p["freshness"],"published":p["is_published"]}.items())+"\n---\n\n"
        return Response(header+p["markdown"],mimetype="text/markdown",
            headers={"Content-Disposition":"attachment; filename=wiki-"+p["revision_id"]+".md"})
    from .platform_routes import register as register_platform
    register_platform(app,service)
    return service
