"""Dashboard endpoints only read knowledge data; POST queries have no data mutations."""
import csv
import io
import json
from flask import Blueprint, Response, jsonify, request
from core.dashboard import DATASETS, DashboardRepository, StaleSnapshot, public_row
from core.data_catalog import FileCatalog


def register(app, root, metadata_loader, relations_loader):
    repo = DashboardRepository(root, metadata_loader, relations_loader)
    bp = Blueprint("dashboard", __name__)
    files = FileCatalog(repo)
    app.extensions["dashboard_file_catalog"] = files
    app.extensions["dashboard_repository"] = repo

    def error(exc):
        if isinstance(exc, StaleSnapshot):
            return jsonify(error=str(exc), error_code="snapshot_changed"), 409
        if isinstance(exc, (ValueError, TypeError)):
            return jsonify(error=str(exc)), 400
        app.logger.exception("Dashboard source read failed")
        return jsonify(error="来源数据暂时不可读取，请重试或检查数据说明"), 503

    @bp.get("/api/dashboard/bootstrap")
    def bootstrap():
        try:
            return jsonify(repo.bootstrap())
        except Exception as exc:
            return error(exc)

    @bp.get("/api/dashboard/files")
    def file_catalog():
        try:
            return jsonify(files.list())
        except Exception as exc:
            return error(exc)

    @bp.get("/api/dashboard/files/<key>")
    def file_preview(key):
        try:
            return jsonify(files.detail(
                key, request.args.get("catalog_revision"),
                int(request.args.get("offset", 0)), int(request.args.get("size", 20)),
                request.args.get("sort") or None, request.args.get("direction", "asc") == "desc"))
        except Exception as exc:
            return error(exc)

    @bp.post("/api/dashboard/query")
    def query():
        try:
            return jsonify(repo.query(request.get_json(silent=True)))
        except Exception as exc:
            return error(exc)

    @bp.get("/api/dashboard/detail/<dataset>/<path:identity>")
    def detail(dataset, identity):
        try:
            offset = int(request.args.get("offset", 0))
            if offset < 0:
                raise ValueError("偏移量无效")
            result = repo.detail(dataset, identity, request.args.get("snapshot_id"), offset)
            return jsonify(result) if result else (jsonify(error="记录不存在"), 404)
        except Exception as exc:
            return error(exc)

    @bp.post("/api/dashboard/export")
    def export():
        try:
            payload = request.get_json(silent=True)
            s, dataset, spec, dims, metric, axis, rows = repo.select(payload)
            query = repo.query({**payload, "size": 1})
            headers = ["记录ID", "标题", "资料类型", "来源", "日期", "状态", "化学品名称提及", "片段数", "字符数"]
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(["数据快照", s["snapshot_id"], "指标版本", query["passport"]["version"]])
            writer.writerow(["统计说明", spec["note"]])
            writer.writerow(["筛选条件", json.dumps(payload, ensure_ascii=False)])
            writer.writerow(headers)
            def clean(value):
                v = str(value if value is not None else "")
                return "'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v
            for row in sorted(rows, key=lambda r: r["id"]):
                writer.writerow([clean(v) for v in [
                    row["id"], row["title"], row.get("type"), row.get("source"),
                    row.get("event_date") if axis == "event" else row.get("date"),
                    row.get("status"), "、".join(row.get("chemicals", [])),
                    row.get("chunks"), row.get("characters")]])
            return Response("\ufeff" + stream.getvalue(), mimetype="text/csv",
                            headers={"Content-Disposition": 'attachment; filename="dashboard-records.csv"'})
        except Exception as exc:
            return error(exc)

    app.register_blueprint(bp)
    return repo
