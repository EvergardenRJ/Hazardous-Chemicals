"""Guarded server-local deployment. No KG data/index mutation."""
import hashlib,json,os,shutil,signal,subprocess,sys,time,urllib.request
from pathlib import Path
runtime=Path("/root/autodl-tmp/chemical_kb").resolve()
stage=Path("/root/autodl-tmp/chemical_kb_wiki_stage_20261001").resolve()
py="/root/miniconda3/envs/kb/bin/python"
expected={
"app/explorer_api.py":"8a4c1cdaa19f408091b7913aad01701cd51baf77858727156ec13f0da7cd7507",
"core/updater.py":"7938e2f5fa5fbfb779025d77f06bf614160ba2da72bf8c967264f6299c0e3e0b",
"core/vector_store.py":"8131692ee302c61f056d2af2e0bda621a4699f3dadd5d3d024f6a584e86b6fb5",
"core/llm.py":"edd74a2f9c1041380325d7e5e0a8ff08e4ea86bfa3baf385bf8b7574eb9c93a0",
"core/wiki_store.py":"a956f3f5721fd327de7877b1394de006c661d3ca74a513e99bc9627b62f410bf",
"core/wiki_generator.py":"ed8c0d5875e27b1dbca216f6c2b43a1149e1635de69919642e4246dba3b838ee",
"core/wiki_quality_validator.py":"85281a080d2cee82cb503734fdb5e3960d3dba8deb4cfe7f97abcd2659f1fb4d",
"app/pages/5_Knowledge_Wiki.py":"848a6362a787d99f8b7825c0a02b60e6605da286c70730f153b7b0f8ea5ba9b3",
"explorer_web/src/Panels.jsx":"f84b40f1ed31f861c704b01cac6b284fcbbef761d9482781bf33a7061647a137",
"explorer_web/src/App.jsx":"ec5f9f4bf8f14b0b6333e027c956b8ef97ff30e349f248d01694342403b6f314",
"explorer_web/src/GraphCanvas.jsx":"ea6944fd9438c0febaee564f30377dac2aefd0b29f9bc3a7291d1545e86152ab",
"explorer_web/src/NewsWorkspace.jsx":"0e88dd8e103658cdeb6b6d645783c5b0f30be2ddba4bed3357eadbcda41e9381",
"explorer_web/src/news.css":"90a1af1dcf65d9677364105f0eae7b989e898261cc78519c89fe3a77444540f0",
"explorer_web/src/styles.css":"ea3ac3f0791b63a64708f1158ced1f34e8bcde94093d80d25340648646d3f3e4"}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for rel,value in expected.items():
    if sha(runtime/rel)!=value:raise RuntimeError("Concurrent modification: "+rel)
manifest=json.loads((stage/"release_manifest.json").read_text())
for rel,value in manifest.items():
    if sha(stage/rel)!=value:raise RuntimeError("Release hash mismatch: "+rel)
    target=runtime/rel
    if target.exists() and rel not in expected and not rel.startswith("explorer_web/dist/"):
        raise RuntimeError("Untracked existing target: "+rel)
kg=Path("/proc/2950/cmdline")
if not kg.exists() or b"scripts/kg/extract_corpus.py" not in kg.read_bytes():raise RuntimeError("Extraction baseline changed; inspect before deployment")
kg_start=Path("/proc/2950/stat").read_text().split()[21]
api_pid=4023;api_cmd=Path(f"/proc/{api_pid}/cmdline").read_bytes()
if b"app.explorer_api" not in api_cmd or b"8503" not in api_cmd:raise RuntimeError("API PID no longer matches")
sys.path.insert(0,str(stage))
import faiss
index=faiss.read_index(str(runtime/"data/vector_store/faiss.index"))
metadata_path=runtime/"data/vector_store/index_metadata.json"
metadata=json.loads(metadata_path.read_text(encoding="utf-8"))
assert index.ntotal==len(metadata)==24606
before_metadata=sha(metadata_path)
backup=runtime/"backups"/("wiki_v2_"+time.strftime("%Y%m%d_%H%M%S"));backup.mkdir(parents=True)
for rel in set(expected)|set(manifest):
    target=runtime/rel
    if target.is_file() and not rel.startswith("explorer_web/dist/"):
        dst=backup/"code"/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,dst)
shutil.copytree(runtime/"explorer_web/dist",backup/"dist")
shutil.copytree(runtime/"data/wiki",backup/"wiki")
shutil.copytree("/root/autodl-tmp/data/wiki",backup/"old_wiki")
(backup/"baseline.json").write_text(json.dumps({"code":expected,"metadata_sha256":before_metadata,"vectors":index.ntotal,
    "kg_pid":2950,"kg_start":kg_start,"api_pid":api_pid,"release_files":list(manifest)},indent=2),encoding="utf-8")
for rel in manifest:
    if rel.startswith("explorer_web/dist/"):continue
    target=runtime/rel;target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_name(target.name+".wiki-new");shutil.copy2(stage/rel,tmp);os.replace(tmp,target)
subprocess.run([py,str(runtime/"scripts/wiki/patch_compat.py")],check=True,cwd=runtime)
env={**os.environ,"CHEM_KB_BASE_DIR":str(runtime),"CHEM_KB_WIKI_DIR":str(runtime/"data/wiki")}
result=subprocess.run([py,str(runtime/"scripts/wiki/migrate.py"),"--root",str(runtime/"data/wiki"),
    "--extra-root","/root/autodl-tmp/data/wiki","--apply"],check=True,cwd=runtime,env=env,capture_output=True,text=True)
docs=runtime/"docs/llmwiki_upgrade_20261001";docs.mkdir(parents=True,exist_ok=True)
(docs/"migration_apply.json").write_text(result.stdout,encoding="utf-8")
subprocess.run([py,str(runtime/"scripts/wiki/repair_audit.py"),"--root",str(runtime/"data/wiki"),
    "--output",str(docs/"citation_repair_audit.json")],check=True,cwd=runtime,env=env)
dist_new=runtime/"explorer_web"/".dist-wiki-new"
shutil.copytree(runtime/"explorer_web/dist",dist_new)
shutil.copytree(stage/"explorer_web/dist",dist_new,dirs_exist_ok=True)
os.replace(runtime/"explorer_web/dist",runtime/"explorer_web"/(".dist-before-wiki-"+backup.name))
os.replace(dist_new,runtime/"explorer_web/dist")
(runtime/"logs").mkdir(exist_ok=True)
os.kill(api_pid,signal.SIGTERM)
for _ in range(50):
    if not Path(f"/proc/{api_pid}").exists():break
    time.sleep(.1)
log=(runtime/"logs/explorer_api_wiki_v2.log").open("ab")
proc=subprocess.Popen([py,"-u","-m","app.explorer_api","--host","127.0.0.1","--port","8503"],
    cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
for _ in range(60):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8503/api/wiki",timeout=2) as response:registry=json.load(response)
        if len(registry["entities"])==6:break
    except Exception:pass
    time.sleep(.5)
else:raise RuntimeError("API restart verification failed; backup available at "+str(backup))
worker_log=(runtime/"logs/wiki_worker_v2.log").open("ab")
worker=subprocess.Popen([py,"-u","-m","core.wiki.worker"],cwd=runtime,env=env,
    stdout=worker_log,stderr=subprocess.STDOUT,start_new_session=True)
(runtime/"logs/wiki_worker_v2.pid").write_text(str(worker.pid))
assert kg_start==Path("/proc/2950/stat").read_text().split()[21]
assert before_metadata==sha(metadata_path)
report={"backup":str(backup),"api_pid":proc.pid,"worker_pid":worker.pid,"kg_pid":2950,"kg_start_preserved":True,
        "entities":registry["entities"],"metadata_unchanged":True,"vectors":index.ntotal}
(docs/"deployment.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False))
