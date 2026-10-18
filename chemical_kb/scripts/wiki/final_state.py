"""Record final read-only deployment state and authored-file hashes."""
import hashlib,json,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from core.wiki.service import WikiService
from core.wiki.jobs import Jobs,kg_busy
service=WikiService();jobs=Jobs(service.repo).list()
upgrade=[j for j in jobs if str(j["spec"].get("idempotency_key","")).startswith("wiki-upgrade-20261001-")]
assert len(upgrade)==3 and all(j["state"]=="queued" and not j["lease_owner"] for j in upgrade)
assert sum(j["progress"]["total"] for j in upgrade)==26
deployment=json.loads((root/"docs/llmwiki_upgrade_20261001/deployment.json").read_text())
for pid,needle in ((2950,b"scripts/kg/extract_corpus.py"),(deployment["api_pid"],b"app.explorer_api"),(deployment["worker_pid"],b"core.wiki.worker")):
    assert needle in Path(f"/proc/{pid}/cmdline").read_bytes()
assert kg_busy()
files=list((root/"core/wiki").glob("*.py"))+[root/p for p in (
"core/wiki_store.py","core/wiki_generator.py","core/wiki_quality_validator.py","core/kg/wiki_review_manager.py",
"core/updater.py","core/vector_store.py","core/index_transaction.py","core/llm.py","app/explorer_api.py","app/pages/5_Knowledge_Wiki.py",
"explorer_web/src/Panels.jsx","explorer_web/src/WikiWorkspace.jsx","explorer_web/src/wiki.css")]
files+=list((root/"tests").glob("test_wiki*.py"))
docs=root/"docs/llmwiki_upgrade_20261001"
(docs/"CURRENT_CODE_SHA256.json").write_text(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2),encoding="utf-8")
state={"entries":len(service.list()),"published":sum(bool(e["published_revision"]) for e in service.repo.list()),
"jobs":[{"entity":j["entity"],"state":j["state"],"sections":j["progress"]["total"],"block_reason":j["block_reason"]} for j in upgrade],
"kg_pid":2950,"api_pid":deployment["api_pid"],"worker_pid":deployment["worker_pid"],"tests":{"isolated_total":49,"passed":49},
"browser":{"fixture_write_flow":"passed","production_read_only":"passed","page_errors":0},
"fact_accuracy":"not_measured; expert labels required","generation_throughput":"not_measured; waiting for GPU"}
(docs/"FINAL_STATE.json").write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
checksums="\n".join(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+str(p.relative_to(docs)) for p in sorted(docs.rglob("*")) if p.is_file() and p.name!="SHA256SUMS")+"\n"
(docs/"SHA256SUMS").write_text(checksums,encoding="utf-8")
print(json.dumps(state,ensure_ascii=False))
