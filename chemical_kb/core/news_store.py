"""Independent candidate-news mirror. Never writes KG or Wiki files."""
from __future__ import annotations
import hashlib,json,os,re,sqlite3,subprocess,threading
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from core.config import BASE_DIR
NEWS_DIR=Path(os.environ.get('CHEMNEWS_DATA_DIR',str(BASE_DIR/'data/news')))
CONFIG=Path(os.environ.get('CHEMNEWS_SYNC_CONFIG',str(NEWS_DIR/'sync.json')))
_sync_lock=threading.Lock()
SCHEMA="""
CREATE TABLE IF NOT EXISTS articles(id INTEGER PRIMARY KEY,url TEXT NOT NULL UNIQUE,source_id TEXT NOT NULL,title TEXT NOT NULL,published_at TEXT,event_at TEXT,article_type TEXT NOT NULL,review_status TEXT NOT NULL DEFAULT 'candidate',review_note TEXT NOT NULL DEFAULT '',payload TEXT NOT NULL,origin_hash TEXT NOT NULL,removed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY AUTOINCREMENT,article_id INTEGER NOT NULL,payload TEXT NOT NULL,origin_hash TEXT NOT NULL,mirrored_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS news_date ON articles(published_at,id);
CREATE INDEX IF NOT EXISTS news_source ON articles(source_id);
"""
def now(): return datetime.now(timezone.utc).isoformat()
def digest(row): return hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
@contextmanager
def connection():
    NEWS_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(NEWS_DIR/'mirror.sqlite3',timeout=15);db.row_factory=sqlite3.Row
    db.execute('PRAGMA temp_store=MEMORY')
    db.executescript(SCHEMA)
    try:
        with db: yield db
    finally: db.close()
def meta(db,key,default=None):
    r=db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
    return json.loads(r[0]) if r else default

def put_meta(db,key,value): db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,ensure_ascii=False)))
def safe_url(value):
    try:
        p=urlsplit(value or '')
        return value if p.scheme in ('https','http') and p.hostname and not p.username and not p.password else ''
    except ValueError: return ''
def date_value(row):
    v=row.get('published_at_utc')
    if v:
        try: return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).isoformat()
        except ValueError: pass
    raw=row.get('published_at_raw') or ''
    # Foreign date-only strings retain their precision; never fill event_at.
    jp=re.fullmatch(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日',raw.strip())
    if jp:
        try: return datetime(*map(int,jp.groups())).date().isoformat()
        except ValueError: return None
    for fmt in ('%A %d %B %Y','%d %B %Y','%d %b %Y'):
        try: return datetime.strptime(raw.strip(),fmt).date().isoformat()
        except ValueError: pass
    m=re.match(r'^(\d{4}-\d{2}-\d{2})(?:$|[ T])',raw)
    return m.group(1) if m else None

def article_type(row):
    text=(row.get('title','')+' '+row.get('summary','')).lower();sid=row.get('source_id','')
    if sid=='aria_fr': return 'investigation'
    if sid=='nite_chem': return 'policy'
    if sid=='ntsb_news' and any(t in text for t in ('investigation','report','recommends','recommendation','finds','caused')): return 'investigation'
    if sid=='worksafe_vic' and any(t in text for t in ('fined','charges','charged','prosecut','sentenced')): return 'policy'
    if sid=='mem_history': return 'historical'
    if sid=='mem_report' or any(t in text for t in ('调查报告','investigation report','final report')): return 'investigation'
    if any(t in text for t in ('事故','泄漏','爆炸','火灾','fatal','explosion','leak','fire','killed','incident')): return 'incident'
    if any(t in text for t in ('条例','法规','办法','征求意见','标准','处罚','fined','prosecut','regulation','enforcement','sentenced')): return 'policy'
    if any(t in text for t in ('科普','安全提示','宣传','awareness','safety tips')): return 'education'
    return 'news'

def manifest():
    with connection() as db: return {str(r['id']):r['origin_hash'] for r in db.execute('SELECT id,origin_hash FROM articles WHERE removed=0')}
def apply_export(data):
    if data.get('schema_version')!=1 or not isinstance(data.get('manifest'),dict): raise ValueError('unsupported export')
    expected=data['manifest']
    if len(expected)!=data.get('total') or digest(expected)!=data.get('snapshot_hash'): raise ValueError('snapshot manifest mismatch')
    timestamp=now();inserted=changed=0
    with connection() as db:
        for item in data['records']:
            row=item['record'];aid=int(row['id']);fingerprint=digest(row)
            if fingerprint!=item['hash'] or expected.get(str(aid))!=fingerprint: raise ValueError('record checksum mismatch')
            if not safe_url(row.get('url')) or not row.get('title'): raise ValueError('invalid news URL/title')
            old=db.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone()
            payload=json.dumps(row,ensure_ascii=False)
            if old and old['origin_hash']!=fingerprint:
                db.execute('INSERT INTO versions(article_id,payload,origin_hash,mirrored_at) VALUES(?,?,?,?)',(aid,old['payload'],old['origin_hash'],timestamp));changed+=1
            elif not old: inserted+=1
            db.execute("""INSERT INTO articles(id,url,source_id,title,published_at,event_at,article_type,payload,origin_hash) VALUES(?,?,?,?,?,NULL,?,?,?)
ON CONFLICT(id) DO UPDATE SET url=excluded.url,source_id=excluded.source_id,title=excluded.title,published_at=excluded.published_at,article_type=excluded.article_type,payload=excluded.payload,origin_hash=excluded.origin_hash,removed=0""",(aid,row['url'],row['source_id'],row['title'],date_value(row),article_type(row),payload,fingerprint))
        for aid in data.get('removed',[]): db.execute('UPDATE articles SET removed=1 WHERE id=?',(int(aid),))
        actual={str(r['id']):r['origin_hash'] for r in db.execute('SELECT id,origin_hash FROM articles WHERE removed=0')}
        if actual!=expected: raise ValueError('mirror does not match upstream snapshot')
        put_meta(db,'sources',data['sources']);put_meta(db,'backfill',data.get('backfill',[]))
        result={'last_success_at':timestamp,'last_attempt_at':timestamp,'exported_at':data['exported_at'],'total':len(actual),'inserted':inserted,'changed':changed,'last_error':None,'snapshot_hash':data['snapshot_hash']}
        put_meta(db,'sync',result)
    return result

def sync():
    if not CONFIG.exists(): return {'configured':False,'message':'自动同步待配置'}
    if not _sync_lock.acquire(blocking=False): return {'running':True}
    try:
        import fcntl
        NEWS_DIR.mkdir(parents=True,exist_ok=True)
        with (NEWS_DIR/'sync.lock').open('a') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return {'running':True}
            timestamp=now()
            try:
                config=json.loads(CONFIG.read_text(encoding='utf-8'))
                command=['ssh','-T','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+config['known_hosts_file'],'-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2','-i',config['identity_file'],'-p',str(config.get('port',22)),config['user']+'@'+config['host'],'chemnews-export']
                result=subprocess.run(command,input=json.dumps({'known':manifest()}),capture_output=True,text=True,timeout=45)
                if result.returncode: raise RuntimeError(result.stderr.strip()[:300] or 'SSH export failed')
                if len(result.stdout)>32*1024*1024: raise ValueError('export exceeds size limit')
                return apply_export(json.loads(result.stdout))
            except Exception as exc:
                with connection() as db:
                    state=meta(db,'sync',{});state.update(last_attempt_at=timestamp,last_error=str(exc)[:350]);put_meta(db,'sync',state)
                return {'error':str(exc)[:350]}
    finally: _sync_lock.release()

def sync_async():
    if _sync_lock.locked(): return False
    threading.Thread(target=sync,daemon=True).start();return True

def status():
    with connection() as db:
        stats=dict(db.execute('SELECT COUNT(*) total,SUM(published_at IS NULL) unknown_dates,SUM(event_at IS NULL) unknown_events FROM articles WHERE removed=0').fetchone())
        stats.update(sync=meta(db,'sync',{}),sources=[{**x,'index_url':safe_url(x.get('index_url'))} for x in meta(db,'sources',[])],backfill=meta(db,'backfill',[]),running=_sync_lock.locked(),configured=CONFIG.exists())
        stats['countries']=[r[0] for r in db.execute("SELECT DISTINCT json_extract(payload,'$.country') FROM articles WHERE removed=0 ORDER BY 1")]
        stats['types']=[r[0] for r in db.execute('SELECT DISTINCT article_type FROM articles WHERE removed=0 ORDER BY 1')]
        return stats

def present(r):
    origin=json.loads(r['payload']);origin.update(id=r['id'],published_at=r['published_at'],event_at=r['event_at'],article_type=r['article_type'],review_status=r['review_status'],review_note=r['review_note'])
    origin['url']=safe_url(origin['url']);origin['index_url']=safe_url(origin.get('index_url'))
    try: origin['matched_terms']=json.loads(origin.get('matched_terms') or '[]')
    except (ValueError,TypeError): origin['matched_terms']=[]
    return origin

def list_articles(params):
    where=['removed=0'];values=[]
    for field in ('source_id','article_type','review_status'):
        if params.get(field): where.append(field+'=?');values.append(params[field])
    if params.get('country'): where.append("json_extract(payload,'$.country')=?");values.append(params['country'])
    if params.get('q'):
        where.append("(title LIKE ? ESCAPE '\\' OR json_extract(payload,'$.summary') LIKE ? ESCAPE '\\')")
        term='%'+params['q'].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';values.extend([term,term])
    axis='event_at' if params.get('time')=='event' else 'published_at'
    for key,op in (('from','>='),('to','<=')):
        if params.get(key):
            datetime.strptime(params[key],'%Y-%m-%d');where.append('substr('+axis+',1,10) '+op+' ?');values.append(params[key])
    if params.get('unknown')=='1': where.append(axis+' IS NULL')
    page=max(1,int(params.get('page',1)));size=min(100,max(1,int(params.get('size',20))))
    clause=' AND '.join(where)
    with connection() as db:
        total=db.execute('SELECT COUNT(*) FROM articles WHERE '+clause,values).fetchone()[0]
        rows=db.execute('SELECT * FROM articles WHERE '+clause+' ORDER BY '+axis+' IS NULL,'+axis+' DESC,id DESC LIMIT ? OFFSET ?',values+[size,(page-1)*size]).fetchall()
        timeline=[{'date':r[0] or 'unknown','count':r[1]} for r in db.execute('SELECT substr('+axis+',1,7),COUNT(*) FROM articles WHERE '+clause+' GROUP BY 1 ORDER BY 1',values)]
        return {'items':[present(r) for r in rows],'total':total,'page':page,'size':size,'timeline':timeline,'time':axis}

def detail(aid):
    with connection() as db:
        r=db.execute('SELECT * FROM articles WHERE id=? AND removed=0',(aid,)).fetchone()
        if not r: return None
        item=present(r);item['versions']=[{'mirrored_at':v['mirrored_at'],'record':json.loads(v['payload'])} for v in db.execute('SELECT * FROM versions WHERE article_id=? ORDER BY id DESC LIMIT 20',(aid,))]
        return item
