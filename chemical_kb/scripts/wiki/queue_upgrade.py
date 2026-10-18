"""Queue authorized content refresh, preserving existing revisions and expert edits."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from core.wiki.service import WikiService
from core.wiki.jobs import Jobs,kg_busy
from core.wiki.citations import SECTIONS
service=WikiService();jobs=Jobs(service.repo);queued=[]
assert kg_busy(),"Inspect resource state before scheduling upgrade"
for entity in ("氨","液氯","天然气"):
    p=service.detail(entity)
    if entity=="天然气":
        titles=list(SECTIONS);mode="replace_page"
    else:
        titles=list(dict.fromkeys(e.split(": ",1)[0] for e in p["validation"]["errors"]))
        titles=[t for t in titles if t in SECTIONS];mode="refresh"
    if not titles:continue
    job=jobs.create(entity,{"sections":titles,"mode":mode,"base_revision":p["revision_id"],
        "idempotency_key":"wiki-upgrade-20261001-"+entity})
    queued.append({k:job[k] for k in ("job_id","entity","state","block_reason","progress")})
    queued[-1]["sections"]=titles
out=root/"docs/llmwiki_upgrade_20261001/content_refresh_jobs.json"
out.write_text(json.dumps(queued,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(queued,ensure_ascii=False))
