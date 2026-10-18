"""Read original public news on demand; keep cache on the news data disk."""
from __future__ import annotations
import hashlib, ipaddress, json, re, socket, sqlite3, threading, time
from datetime import datetime, timezone
from contextlib import closing
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from core import news_store
UA='ChemNewsCollector/1.0 (original-news-reader)'
MAX_BYTES=4*1024*1024
HOSTS=frozenset(('www.aria.developpement-durable.gouv.fr','www.worksafe.vic.gov.au','www.ntsb.gov','www.nite.go.jp','www.mem.gov.cn','www.chemicalsafety.org.cn','www.cigia.org.cn','www.csb.gov','www.gov.uk','press.hse.gov.uk','www.mom.gov.sg','www.worksafe.govt.nz'))
_locks=[threading.Lock() for _ in range(64)]
_host_locks={h:threading.Lock() for h in HOSTS}
_last={};_robots={}
def now():return datetime.now(timezone.utc).isoformat()
def validate_url(url,host=None):
 p=urlsplit(url)
 if p.scheme not in ('http','https') or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,80,443) or (host and p.hostname!=host):raise ValueError('来源链接不在已登记新闻网站范围')
 return p
def public_address(host):
 addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
 if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('来源域名未解析到公网地址')
class Redirects(HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  validate_url(newurl,urlsplit(req.full_url).hostname)
  return super().redirect_request(req,fp,code,msg,headers,newurl)
def download(url,host):
 validate_url(url,host);public_address(host)
 delay=2-(time.monotonic()-_last.get(host,0))
 if delay>0:time.sleep(delay)
 try:
  req=Request(url,headers={'User-Agent':UA,'Accept':'text/html,application/pdf;q=0.8'})
  with build_opener(Redirects()).open(req,timeout=15) as response:
   chunks=[];size=0;deadline=time.monotonic()+35
   while True:
    if time.monotonic()>deadline:raise TimeoutError('正文响应超时')
    chunk=response.read(65536)
    if not chunk:break
    chunks.append(chunk);size+=len(chunk)
    if size>MAX_BYTES:raise ValueError('原文超过单次读取大小上限')
   raw=b''.join(chunks)
   return raw,dict(response.headers),response.geturl()
 finally:_last[host]=time.monotonic()
def decoded(raw,headers):
 charset=re.search(r'charset\s*=\s*["\']?([\w-]+)',headers.get('Content-Type',''),re.I)
 if not charset:charset=re.search(br'charset\s*=\s*["\']?([\w-]+)',raw[:4096],re.I)
 name=charset[1] if charset else 'utf-8'
 if isinstance(name,bytes):name=name.decode('ascii','replace')
 try:return raw.decode(name,'replace')
 except LookupError:return raw.decode('utf-8','replace')
def may_read(url,host):
 cached=_robots.get(host)
 if not cached or time.monotonic()-cached[0]>21600:
  origin=urlsplit(url);robots_url=origin.scheme+'://'+host+'/robots.txt'
  try:
   raw,headers,_=download(robots_url,host);robot_text=decoded(raw,headers)
   if re.search(r'<(?:html|title)\b',robot_text,re.I):raise ValueError('来源访问规则返回验证页')
  except HTTPError as exc:
   if exc.code not in (404,410):raise
   robot_text='User-agent: *\nAllow: /'
  parser=RobotFileParser();parser.parse(robot_text.splitlines());_robots[host]=(time.monotonic(),parser)
 if not _robots[host][1].can_fetch(UA,url):raise PermissionError('原站暂不允许自动读取此链接')
SELECTORS={
 'www.ntsb.gov':['div[id$="RichHtmlField"]','.ExternalClass','.newsArticle','.ms-rtestate-field'],
 'www.worksafe.vic.gov.au':['article[role="main"] .rpl-content','article[role="main"]','main'],
 'www.aria.developpement-durable.gouv.fr':['.entry-content','.post-content','.article-content','article'],
 'www.nite.go.jp':['#main_content','#mainContents','#mainContent','.main-content','#main'],
 'www.mem.gov.cn':['.TRS_Editor','.article-content','.content'],
 'www.chemicalsafety.org.cn':['.article-content','.news-content','.content-detail','.detail-content'],
 'www.cigia.org.cn':['.article-content','.news-content','#content','.content'],
 'www.csb.gov':['.contentArea','.content-area','.content','.mainContent','main'],
 'www.gov.uk':['.gem-c-govspeak','.govspeak'],
 'press.hse.gov.uk':['.entry-content','article'],
 'www.mom.gov.sg':['.content-body','.rte','.rich-text','.content','main'],
 'www.worksafe.govt.nz':['.typography','.content-body','.main-content','main'],
}
def clean_text(node):return re.sub(r'[\t\r\f\v ]+',' ',node.get_text(' ',strip=True)).strip()
def extract(body,url,title=''):
 host=validate_url(url).hostname;soup=BeautifulSoup(body,'html.parser')
 if re.search(r'^(?:One moment|Just a moment|Access denied|Forbidden)',clean_text(soup.title) if soup.title else '',re.I):raise PermissionError('原站返回访问验证页')
 for n in soup.select('script,style,noscript,nav,footer,header,aside,[hidden],.cookie-banner,.breadcrumb,.breadcrumbs,.social-share'):n.decompose()
 for n in soup.select('form'):n.unwrap()
 root=None
 for selector in SELECTORS.get(host,[]):
  options=[n for n in soup.select(selector) if len(clean_text(n))>=80]
  if options:root=max(options,key=lambda n:len(clean_text(n)));break
 if root is None:root=max(soup.select('article,main,[role="main"]'),key=lambda n:len(clean_text(n)),default=None)
 if root is None:
  options=[n for n in soup.select('div,section,td') if len(n.find_all('p'))>=2]
  def score(n):return sum(len(clean_text(p)) for p in n.find_all('p'))-2*sum(len(clean_text(a)) for a in n.find_all('a'))
  root=max(options,key=score,default=None)
 if root is None:return [],[]
 for n in root.select('.share,.sharing,.related,.related-content,.pagination,.contact-us'):n.decompose()
 paragraphs=[]
 for n in root.select('h2,h3,h4,p,li,blockquote,table'):
  if n.find_parent(['p','li','blockquote','table']):continue
  value=clean_text(n)
  if value and value!=title and (not paragraphs or value!=paragraphs[-1]):paragraphs.append(value)
 if not paragraphs:paragraphs=[s.strip() for s in root.get_text('\n',strip=True).splitlines() if s.strip()]
 links=[];seen=set()
 for a in root.select('a[href]'):
  link=urljoin(url,a['href']);p=urlsplit(link);label=clean_text(a)
  if p.scheme not in ('http','https') or p.username or p.password or not label or link in seen:continue
  seen.add(link);links.append({'label':label,'url':link,'attachment':bool(re.search(r'\.(pdf|docx?|xlsx?|zip)(?:$|[?#])',link,re.I))})
 if sum(len(p) for p in paragraphs)<80:return [],links
 return paragraphs,links
def read_original(item):
 url=item['url'];host=validate_url(url).hostname
 with _host_locks[host]:
  may_read(url,host);raw,headers,final_url=download(url,host)
 mime=headers.get('Content-Type','').lower()
 result={'url':final_url,'fetched_at':now(),'language':item.get('language'),'paragraphs':[],'links':[],'from_cache':False}
 if 'application/pdf' in mime or raw.startswith(b'%PDF-'):result.update(status='document',format='pdf');return result
 if not any(x in mime for x in ('html','text/')):raise ValueError('此原文是下载文件')
 paragraphs,links=extract(decoded(raw,headers),final_url,item['title'])
 result.update(status='ready' if paragraphs else 'unavailable',format='html',paragraphs=paragraphs,links=links)
 if not paragraphs:result['message']='原站正文暂未能读取'
 result['content_hash']=hashlib.sha256(json.dumps([paragraphs,links],ensure_ascii=False).encode()).hexdigest()
 return result
def content(aid,refresh=False):
 item=news_store.detail(aid)
 if not item:return None
 with _locks[aid%len(_locks)]:
  news_store.NEWS_DIR.mkdir(parents=True,exist_ok=True)
  with closing(sqlite3.connect(news_store.NEWS_DIR/'content.sqlite3',timeout=15)) as db, db:
   db.execute('PRAGMA temp_store=MEMORY')
   db.execute('CREATE TABLE IF NOT EXISTS contents(article_id INTEGER PRIMARY KEY,url TEXT NOT NULL,result TEXT NOT NULL,checked REAL NOT NULL)')
   row=db.execute('SELECT url,result,checked FROM contents WHERE article_id=?',(aid,)).fetchone()
   if row and row[0]==item['url'] and not refresh:
    cached=json.loads(row[1]);age=time.time()-row[2]
    if age<(7*86400 if cached['status'] in ('ready','document') else 300):return {**cached,'from_cache':True}
  try:result=read_original(item)
  except Exception as exc:
   if isinstance(exc,PermissionError):message=str(exc)
   elif isinstance(exc,HTTPError):message=f'原站返回 HTTP {exc.code}'
   else:message='原站正文暂时无法读取，请稍后重试'
   result={'status':'unavailable','message':message,'url':item['url'],'fetched_at':now(),'paragraphs':[],'links':[],'from_cache':False}
  if result['status']=='unavailable' and row and row[0]==item['url']:
   previous=json.loads(row[1])
   if previous['status'] in ('ready','document'):return {**previous,'from_cache':True,'refresh_error':result.get('message')}
  with closing(sqlite3.connect(news_store.NEWS_DIR/'content.sqlite3',timeout=15)) as db, db:
   db.execute('PRAGMA temp_store=MEMORY')
   db.execute('INSERT INTO contents VALUES(?,?,?,?) ON CONFLICT(article_id) DO UPDATE SET url=excluded.url,result=excluded.result,checked=excluded.checked',(aid,item['url'],json.dumps(result,ensure_ascii=False),time.time()))
  return result
