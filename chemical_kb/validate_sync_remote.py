from core.news_store import sync,status,NEWS_DIR,CONFIG
import json,subprocess,os,signal,time
print('incremental_sync_1',json.dumps(sync(),ensure_ascii=False))
print('incremental_sync_2',json.dumps(sync(),ensure_ascii=False))
c=json.loads(CONFIG.read_text());cmd=['ssh','-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+c['known_hosts_file'],'-i',c['identity_file'],c['user']+'@'+c['host'],'permission-probe']
r=subprocess.run(cmd,input='{}',capture_output=True,text=True,timeout=20);out=json.loads(r.stdout)
print('forced_exporter_probe',{'exit':r.returncode,'schema':out['schema_version'],'total':out['total']})
pid=int((NEWS_DIR/'workbench.pid').read_text());argv=open('/proc/'+str(pid)+'/cmdline','rb').read()
if b'app.explorer_api' not in argv:raise RuntimeError('workbench pid mismatch')
os.kill(pid,signal.SIGTERM)
for _ in range(30):
 try:os.kill(pid,0)
 except ProcessLookupError:break
 time.sleep(.1)
