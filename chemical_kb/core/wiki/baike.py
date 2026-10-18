"""Baidu official public article reader; no challenge solving or proxy rotation."""
import hashlib,json,re,time,unicodedata
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit,quote
from .repository import now

HOSTS={"baike.baidu.com","bkso.baidu.com"}
_PRIMARY_BLOCKED_UNTIL=0

def official_url(url):
    p=urlsplit(str(url))
    if p.scheme!="https" or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443) or not p.path.startswith("/item/"):
        raise ValueError("需要百度官方 HTTPS 词条地址")
    return p

def is_challenge(raw):
    prefix=raw[:18000].decode("utf-8","replace")
    return bool(re.search(r"<title[^>]*>\s*(?:百度安全验证|安全验证|访问验证|百度一下).*?</title>",prefix,re.S))

def fetch_article_bytes(url,download,prefer_public=False):
    global _PRIMARY_BLOCKED_UNTIL
    p=official_url(url)
    fallback=urlunsplit(("https","bkso.baidu.com",p.path,p.query,""))
    candidates=[url] if p.hostname=="bkso.baidu.com" else ([fallback] if prefer_public or time.monotonic()<_PRIMARY_BLOCKED_UNTIL else [url,fallback])
    errors=[]
    for candidate in dict.fromkeys(candidates):
        try:
            raw,final=download(candidate)
            official_url(final)
            if is_challenge(raw):raise ValueError("百度安全验证页面，未取得词条正文")
            return raw,final
        except Exception as exc:
            response=getattr(exc,"response",None)
            code=getattr(response,"status_code",None)
            recover=code in (403,429) or "安全验证" in str(exc)
            if urlsplit(candidate).hostname=="baike.baidu.com" and recover:
                _PRIMARY_BLOCKED_UNTIL=time.monotonic()+600
                errors.append(str(exc)[:180]);continue
            raise
    raise ValueError("百度官方词条入口暂不可用："+"; ".join(errors))

def normalized(text):
    return re.sub(r"[^\w]","",unicodedata.normalize("NFKC",str(text)).casefold())

def parse_article(raw,url,expected,aliases=()):
    from bs4 import BeautifulSoup
    official_url(url)
    if is_challenge(raw):raise ValueError("验证页不能作为百科内容")
    soup=BeautifulSoup(raw,"html.parser")
    title_node=soup.select_one("h1.J-lemma-title") or soup.find("h1")
    if not title_node:raise ValueError("页面缺少词条标题")
    title=title_node.get_text("",strip=True)
    if normalized(title) not in {normalized(x) for x in [expected,*aliases]}:
        raise ValueError("词条标题不匹配："+title)
    for n in soup.select("script,style,sup,[class*=superscript],[class*=reference]"):n.decompose()
    sections=[];heading="基本概述";paragraphs=[]
    def flush():
        if paragraphs:sections.append({"heading":heading,"text":"\n".join(paragraphs)[:5000]})
    for node in soup.find_all(["h2","h3","div"]):
        if node.name in ("h2","h3"):
            h=node.get_text("",strip=True)
            if h in ("目录","参考资料","词条图册","相关视频"):continue
            flush();heading=h;paragraphs=[]
        elif any(c.startswith("para_") or c=="para" for c in node.get("class",[])):
            text=node.get_text("",strip=True)
            text=re.sub(r"\[\d+(?:[-,，]\d+)*\]","",text)
            if len(text)>=20:paragraphs.append(text)
    flush()
    if not sections:raise ValueError("页面没有可用正文段落")
    canonical=soup.select_one('link[rel="canonical"]')
    original=canonical.get("href") if canonical else url
    try:official_url(original)
    except ValueError:original=url
    return {"name":expected,"title":title,"source_name":"百度百科","url":url,"canonical_url":original,"retrieved_at":now(),"status":"fetched","html_sha256":hashlib.sha256(raw).hexdigest(),"sections":sections}

class BaikeReader:
    def __init__(self,cache,download):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True);self.download=download
    def read(self,name,url=None,aliases=(),prefer_public=False,max_age=30*86400):
        source=url or "https://baike.baidu.com/item/"+quote(name,safe="")
        official_url(source)
        key=hashlib.sha256(json.dumps([name,source],ensure_ascii=False).encode()).hexdigest()
        target=self.cache/(key+".json")
        if target.exists() and time.time()-target.stat().st_mtime<max_age:
            cached=json.loads(target.read_text(encoding="utf-8"))
            if cached.get("name")==name and cached.get("status")=="fetched":return cached
        raw,final=fetch_article_bytes(source,self.download,prefer_public)
        record=parse_article(raw,final,name,aliases)
        temp=target.with_suffix(".tmp");temp.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8");temp.replace(target)
        return record

CHAPTERS={
"基本概述":["基本概述"],"理化性质":["物理性质","物化性质","理化性质","性质","分子结构"],
"危险特性":["安全信息","危险性","化学性质","安全术语"],"健康危害":["毒理","毒性","健康危害"],
"生产与使用":["应用","用途","生产现状"],"储存要求":["储存","贮藏","操作处置"],
"运输与装卸":["运输"],"设备设施与自动化控制":["设备","装置"],"个体防护":["防护"],
"泄漏应急":["泄漏"],"火灾/爆炸处置":["消防","灭火"],"急救":["急救"],
"典型事故经验":["事故"],"相关标准法规":["标准","法规"],"检查要点":["注意事项"],
"适用范围与边界":["分类","定义"],"系统与适用边界":["分类","组成","适用","原理"],"风险与失效情景":["故障","风险","危险"],"设施与管理关联":["设备","装置","管理"],"核查项目":["检验","检查","维护"],"工作原理":["原理"],"风险与失效模式":["故障","风险"],
"预防与检查":["维护","检查"],"应急与异常处置":["应急"],"相关概念":["定义"],
"定义与适用范围":["基本概述","定义"],"核心原理":["原理"],"风险场景":["风险"],
"管理与检查":["管理","检查"],"关联设备与化学品":["组成","分类"],"事故阅读与复盘":["事故"]}

def chapter_source(record,title):
    result={"source_name":"百度百科","url":record["url"],"canonical_url":record.get("canonical_url"),"title":record["title"],"role":"reading_link","section":title}
    matches=[(max((len(k) for k in CHAPTERS.get(title,[]) if k in s["heading"]),default=0),s) for s in record["sections"]]
    matches=[(score,s) for score,s in matches if score]
    if matches:
        sec=max(matches,key=lambda x:x[0])[1];excerpt=sec["text"][:180]
        stop=max(excerpt.rfind("。"),excerpt.rfind("；"))
        if stop>70:excerpt=excerpt[:stop+1]
        result.update(role="excerpt",excerpt=excerpt,original_heading=sec["heading"],retrieved_at=record["retrieved_at"],external_source_id="baidu-"+hashlib.sha256((record["url"]+sec["heading"]+excerpt).encode()).hexdigest()[:24],language="zh")
    return result
