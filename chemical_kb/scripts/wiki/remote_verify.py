import json,os,shutil,sys,tempfile
from pathlib import Path
stage=Path(__file__).resolve().parents[2];sys.path.insert(0,str(stage))
os.environ["CHEM_KB_WIKI_DIR"]=str(stage/"data/wiki")
from core.wiki.service import WikiService
from core.wiki.jobs import kg_busy,Jobs
from core.wiki.worker import Worker
service=WikiService(stage/"data/wiki")
report=service.import_legacy("/root/autodl-tmp/data/wiki")
(stage/"migration_dry_run.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
assert len(service.list())==6
assert all(not e["published_revision"] for e in service.repo.list())
main=[e for e in service.list() if e["entity"] in ("氨","液氯","天然气")]
assert sum(e["review_counts"]["pending"] for e in main)==37
assert kg_busy()
worker=Worker(service,rag_factory=lambda:(_ for _ in ()).throw(AssertionError("GPU loaded during extraction")))
assert worker.once() is False
from app.explorer_api import app
client=app.test_client()
for url in ("/api/health","/api/summary","/api/graph?mode=approved","/api/wiki","/api/wiki/氨","/api/wiki/jobs","/api/wiki/lint"):
    response=client.get(url)
    assert response.status_code==200,(url,response.status_code,response.data[:200])
assert client.get("/api/wiki").json["entities"]==[e["entity"] for e in service.list()]
# Isolation restore exercise: SQLite snapshot + immutable files, after simulated loss of projection.
with tempfile.TemporaryDirectory() as temp:
    target=Path(temp)/"wiki";shutil.copytree(service.repo.root,target,ignore=shutil.ignore_patterns("registry.sqlite*"))
    import sqlite3
    with sqlite3.connect(service.repo.db) as src,sqlite3.connect(target/"registry.sqlite") as dst:src.backup(dst)
    restored=WikiService(target)
    assert [(e["entity"],e["draft_revision"]) for e in restored.repo.list()]==[(e["entity"],e["draft_revision"]) for e in service.repo.list()]
    for e in restored.repo.list():restored.repo.read(e["entity"])
    restored.rebuild_projection()
    assert restored.search("氨")==[]
print(json.dumps({"entries":len(service.list()),"main_pending":37,"published":0,"api_smoke":7,"isolated_restore":"passed","kg_busy":True,
 "validation_errors":{e["entity"]:len(service.detail(e["entity"])["validation"]["errors"]) for e in service.repo.list()}},ensure_ascii=False))
