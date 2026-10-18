"""Apply verified delta, snapshot the live Wiki DB, and restart only Wiki-serving processes."""
import hashlib,json,os,shutil,signal,sqlite3,subprocess,time,urllib.request
from pathlib import Path
runtime=Path("/root/autodl-tmp/chemical_kb")
stage=Path("/root/autodl-tmp/wiki_polish_stage_20261001")
py="/root/miniconda3/envs/kb/bin/python"
manifest=json.loads((stage/"delta_manifest.json").read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for rel,item in manifest.items():
    if sha(stage/rel)!=item["after"]:raise RuntimeError("Delta corrupt: "+rel)
    target=runtime/rel
    if item["before"] is not None and sha(target)!=item["before"]:raise RuntimeError("Concurrent edit: "+rel)
    if item["before"] is None and target.exists():raise RuntimeError("New target already exists: "+rel)
deployment=json.loads((runtime/"docs/llmwiki_upgrade_20261001/deployment.json").read_text())
backup=Path(deployment["backup"])/"polish";backup.mkdir()
shutil.copytree(runtime/"data/wiki/entries",backup/"entries")
with sqlite3.connect(runtime/"data/wiki/registry.sqlite") as src,sqlite3.connect(backup/"registry.sqlite") as dst:src.backup(dst)
for rel,item in manifest.items():
    target=runtime/rel
    if target.exists():
        old=backup/"code"/rel;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,old)
    target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_name(target.name+".wiki-polish")
    shutil.copy2(stage/rel,tmp);os.replace(tmp,target)
api_pid=deployment["api_pid"];worker_pid=deployment["worker_pid"]
for pid,needle in ((api_pid,b"app.explorer_api"),(worker_pid,b"core.wiki.worker")):
    assert needle in Path(f"/proc/{pid}/cmdline").read_bytes();os.kill(pid,signal.SIGTERM)
time.sleep(1)
env={**os.environ,"CHEM_KB_BASE_DIR":str(runtime),"CHEM_KB_WIKI_DIR":str(runtime/"data/wiki")}
api_log=(runtime/"logs/explorer_api_wiki_v2.log").open("ab")
api=subprocess.Popen([py,"-u","-m","app.explorer_api","--host","127.0.0.1","--port","8503"],cwd=runtime,env=env,
 stdout=api_log,stderr=subprocess.STDOUT,start_new_session=True)
for _ in range(40):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8503/api/wiki",timeout=2) as r:data=json.load(r)
        if len(data.get("sections",[]))==17:break
    except Exception:pass
    time.sleep(.5)
else:raise RuntimeError("New routes not available")
log=(runtime/"logs/wiki_worker_v2.log").open("ab")
worker=subprocess.Popen([py,"-u","-m","core.wiki.worker"],cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(runtime/"logs/wiki_worker_v2.pid").write_text(str(worker.pid))
deployment.update(api_pid=api.pid,worker_pid=worker.pid,polish_backup=str(backup))
(runtime/"docs/llmwiki_upgrade_20261001/deployment.json").write_text(json.dumps(deployment,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(deployment,ensure_ascii=False))
