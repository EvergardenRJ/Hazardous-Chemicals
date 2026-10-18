import hashlib, json, sqlite3, subprocess, urllib.request
from pathlib import Path
from core.wiki.gpu_policy import local_gpu_allowed
from core.wiki.jobs import kg_busy

base = Path('/root/autodl-tmp/chemical_kb')
root = 'http://127.0.0.1:8503'
with urllib.request.urlopen(root + '/api/wiki/platform/settings', timeout=10) as r:
    assert json.load(r)['local_gpu'] is True
with urllib.request.urlopen(root + '/api/wiki/platform', timeout=30) as r:
    summary = json.load(r)
assert summary['local_gpu'] is True
gpu = next(r for r in summary['requirements'] if r['feature'] == 'local_gpu')
assert gpu['ready'] is True
asset = next((base / 'explorer_web/dist/assets').glob('WikiWorkspace-*.js'))
with urllib.request.urlopen(root + '/assets/' + asset.name, timeout=10) as r:
    assert 'javascript' in r.headers.get('Content-Type', '')
    js = r.read().decode()
assert '本地 GPU 禁用' not in js
assert 'local_gpu)===!0?' in js
assert '当前不使用服务器 GPU' not in js
with sqlite3.connect('file:' + str(base/'data/wiki/registry.sqlite') + '?mode=ro', uri=True) as db:
    jobs = db.execute('select state,count(*) from jobs group by state').fetchall()
assert local_gpu_allowed()
result = {'gpu_allowed': True, 'api_settings': True, 'api_summary': True,
          'served_ui_updated': True, 'ui_asset': asset.name, 'kg_busy': kg_busy(), 'jobs': jobs,
          'entries': summary['entries'], 'gpu': subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.used,memory.total', '--format=csv,noheader'], text=True).strip()}
Path('/tmp/wiki_gpu_enable_20261018/verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
