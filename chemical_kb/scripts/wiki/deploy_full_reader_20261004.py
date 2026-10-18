import os,sys,json,tarfile,shutil,hashlib,subprocess,time,signal,urllib.request
from pathlib import Path
base=Path('/root/autodl-tmp/chemical_kb');out=base/'docs/wiki_full_catalogue_20261004'
expected={'core/wiki/platform.py':'b4449cfec05f76402fe38c7ea4417a5020714fbdab6d2effaf7b9a0f7c78aa37','explorer_web/src/WikiTools.jsx':'8f1e07fa337ece927f111003af6017aa6ef7fec710f03c49489dc631cc761b32','explorer_web/src/WikiWorkspace.jsx':'d6aba3dc844a257750eeda5ad98d12b70ac0d7b18ec5f8ab800c8d1b18e0da7a','explorer_web/src/wiki.css':'ca1207b0da46e262a3dd31ba27a9864ff07cfdf9bec6f270471dbba2aa391408','explorer_web/dist/index.html':'1bc2ad7d5ef23769947628be592e0431a955b740238625c290f5175a0783c5e3'}
for rel,sha in expected.items():assert hashlib.sha256((base/rel).read_bytes()).hexdigest()==sha,rel+' changed'
api_pid=3954;cmd=Path('/proc/'+str(api_pid)+'/cmdline').read_bytes();assert b'app.explorer_api' in cmd and b'8503' in cmd
kg_before=Path('/proc/5132/cmdline').read_bytes();assert b'extract_corpus.py' in kg_before
stage=base/'.full_reader_stage_20261004';stage.mkdir(exist_ok=True)
with tarfile.open('/root/autodl-tmp/wiki-full-reader-20261004.tgz') as t:
 for m in t.getmembers():assert (stage/m.name).resolve().is_relative_to(stage.resolve()) and not m.issym() and not m.islnk()
 t.extractall(stage)
backup=base/'backups'/('wiki_full_reader_20261004_'+time.strftime('%H%M%S'));backup.mkdir(parents=True)
code=[p for p in expected if p!='explorer_web/dist/index.html']
for rel in code:
 target=backup/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(base/rel,target)
newdist=base/'explorer_web/.dist_full_new';shutil.copytree(stage/'explorer_web/dist',newdist)
for rel in code:
 target=base/rel;temp=target.with_suffix(target.suffix+'.full-new');shutil.copy2(stage/rel,temp);os.replace(temp,target)
os.replace(base/'explorer_web/dist',backup/'dist');os.replace(newdist,base/'explorer_web/dist')
os.kill(api_pid,signal.SIGTERM)
for _ in range(30):
 if not Path('/proc/'+str(api_pid)).exists():break
 time.sleep(.2)
else:raise RuntimeError('API did not stop; KG left running')
env=os.environ.copy();env.update(PYTHONPATH=str(base),CHEM_KB_BASE_DIR=str(base))
with (base/'logs/explorer_api_full_reader_20261004.log').open('ab') as f:
 proc=subprocess.Popen(['nice','-n','19','/root/miniconda3/envs/kb/bin/python','-u','-m','app.explorer_api','--host','127.0.0.1','--port','8503'],cwd=base,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
for _ in range(40):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8503/api/wiki',timeout=2) as r:assert r.status==200
  break
 except Exception:time.sleep(.5)
else:raise RuntimeError('API unavailable; inspect deployment log')
with urllib.request.urlopen('http://127.0.0.1:8503/api/wiki/platform',timeout=120) as r:summary=json.load(r)
assert Path('/proc/5132/cmdline').read_bytes()==kg_before
report={'backup':str(backup),'api_pid':proc.pid,'summary':summary,'kg_pid':5132,'kg_preserved':True,'local_gpu':False,'gpu_processes':subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader'],text=True)}
(out/'reader_deployment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
