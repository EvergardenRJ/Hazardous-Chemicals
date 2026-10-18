"""Low-priority CPU source watcher; never loads models or changes corpus/KG data."""
import os,time,json
from pathlib import Path
from .platform import Platform
from .service import WikiService

def watch_once(p,folder,seen):
    changed=False;processed=0
    present={f.name:f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in ('.pdf','.docx','.pptx','.xlsx','.txt','.md','.html','.htm')}
    for name in list(seen):
        if name not in present:
            old=seen.pop(name);changed=True
            if not any(x['id']==old['id'] for x in seen.values()):p.withdraw(old['id'])
    for name,f in sorted(present.items()):
        state=[f.stat().st_size,f.stat().st_mtime_ns];old=seen.get(name)
        if old and old['state']==state:continue
        source=p.ingest(name,f.read_bytes());seen[name]={'state':state,'id':source['id']};changed=True
        if old and old['id']!=source['id'] and not any(x['id']==old['id'] for x in seen.values()):p.withdraw(old['id'])
        processed+=1
        if processed>=10:break
    if changed:
        path=p.root/'watched_sources.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(seen,ensure_ascii=False),encoding='utf-8');os.replace(tmp,path)
    return processed

def main():
    if hasattr(os,'nice'):os.nice(15)
    p=Platform(WikiService());folder=p.root/'incoming';folder.mkdir(exist_ok=True);manifest=p.root/'watched_sources.json'
    seen=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {};stamp=None
    while True:
        try:
            meta=p.base/'data/vector_store/index_metadata.json';current=(meta.stat().st_mtime_ns,meta.stat().st_size) if meta.exists() else None
            if stamp is not None and current!=stamp and not any(t['state']=='running' for t in p.tasks()):p.sync()
            stamp=current;watch_once(p,folder,seen);p.service.refresh_sources(meta)
        except Exception as e:print(json.dumps({'maintenance_error':str(e)[:400]},ensure_ascii=False),flush=True)
        time.sleep(60)
if __name__=='__main__':main()
