import hashlib,json,os,sys,urllib.parse,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8503"+path,timeout=30) as r:return r.status,json.load(r)
results={}
for path in ("/api/health","/api/summary","/api/wiki","/api/wiki/jobs","/api/wiki/lint","/api/news/status","/api/news","/api/graph?mode=approved"):
    status,obj=get(path);results[path]={"status":status,"keys":list(obj)[:10]}
_,registry=get("/api/wiki");assert len(registry["entries"])==6
pending=sum(e["review_counts"]["pending"] for e in registry["entries"] if e["entity"] in ("氨","液氯","天然气"));assert pending==37
for entity in ("氨","液氯","天然气"):
    status,detail=get("/api/wiki/"+urllib.parse.quote(entity))
    assert detail["view"]=="draft" and not detail["is_published"]
_,summary=get("/api/summary");assert summary["wikis"]==6
from core.wiki.service import WikiService
from core.wiki.worker import Worker
from core.wiki.jobs import kg_busy
service=WikiService(root/"data/wiki")
assert kg_busy() and Worker(service,rag_factory=lambda:(_ for _ in ()).throw(AssertionError("GPU loaded"))).once() is False
deployment=json.loads((root/"docs/llmwiki_upgrade_20261001/deployment.json").read_text(encoding="utf-8"))
backup=Path(deployment["backup"]);preserved=[]
for rel in (backup/"wiki").rglob("*"):
    if rel.is_file():
        live=root/"data/wiki"/rel.relative_to(backup/"wiki")
        assert hashlib.sha256(rel.read_bytes()).digest()==hashlib.sha256(live.read_bytes()).digest()
        preserved.append(str(rel.relative_to(backup/"wiki")))
baseline=json.loads((backup/"baseline.json").read_text())
assert hashlib.sha256((root/"data/vector_store/index_metadata.json").read_bytes()).hexdigest()==baseline["metadata_sha256"]
assert Path("/proc/2950/stat").read_text().split()[21]==baseline["kg_start"]
report={"api":results,"legacy_files_unchanged":len(preserved),"main_pending":pending,"wiki_count":6,
    "kg_pid_preserved":True,"metadata_unchanged":True,"worker_resource_guard":"passed","summary_chunks":summary["chunks"]}
(root/"docs/llmwiki_upgrade_20261001/live_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
