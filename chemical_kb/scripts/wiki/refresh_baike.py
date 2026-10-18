import sys,json,time,copy,traceback
from pathlib import Path
sys.path.insert(0,'/root/autodl-tmp/chemical_kb')
from core.wiki.service import WikiService
from core.wiki.platform import _fetch_direct
from core.wiki.baike import BaikeReader,chapter_source
from core.wiki.citations import validate_revision
from core.wiki.repository import Conflict,now
BASE=Path('/root/autodl-tmp/chemical_kb');out=BASE/'docs/wiki_baike_20261004';out.mkdir(parents=True,exist_ok=True)
service=WikiService();reader=BaikeReader(service.repo.root/'encyclopedia_cache/baidu',_fetch_direct)
pages=[service.repo.read(e['entity']) for e in service.repo.list() if e.get('entity')]
pages=[p for p in pages if p.get('page_type') in ('chemical','equipment','concept','topic')]
retry='--retry' in sys.argv
if retry:
 failed={x['entity'] for x in json.loads((out/'refresh.json').read_text(encoding='utf-8'))['unavailable']}
 pages=[p for p in pages if p['entity'] in failed]
report_file='retry.json' if retry else 'refresh.json'
report={'started_at':now(),'total':len(pages),'fetched':[],'unavailable':[],'updated':[],'conflicts':[],'local_gpu':False}
aliases={'氨':['氨气'],'水合肼':['水合联氨'],'保险粉':['连二亚硫酸钠'],'氨水':['氢氧化铵'],'工业锅炉':['锅炉'],'液氯':['氯气','氯'],'丙醇':['1-丙醇','正丙醇'],'异丙醇':['2-丙醇'],'纯碱':['碳酸钠'],'烧碱':['氢氧化钠'],'1,4-二氧六环':['1,4-二噁烷','二氧六环'],'局部排风系统':['局部排风'],'安全仪表系统':['SIS']}
aliases.update({'FMEA': ['失效模式分析'], 'HAZOP': ['危险与可操作性分析'], 'IDLH': ['立即威胁生命和健康浓度'], 'N-甲基-2-吡咯烷酮': ['N-甲基吡咯烷酮'], '丁烷': ['丁烷气'], '丁酮': ['甲基乙基酮'], '乙酸丁酯': ['乙酸正丁酯'], '乙酸异丙酯': ['醋酸异丙酯'], '乙醇胺': ['2-羟基乙胺'], '二丁醚': ['丁醚'], '仲丁醇': ['2-丁醇'], '叔丁醇': ['2-甲基-2-丙醇'], '对甲酚': ['对甲苯酚'], '异丁烯': ['2-甲基丙烯'], '异丙醚': ['二异丙基醚'], '正戊醇': ['1-戊醇'], '氯二氟甲烷': ['二氟一氯甲烷'], '球罐': ['球形容器'], '甲胺': ['一甲胺'], '相对密度': ['比重'], '硫酰氯': ['磺酰氯'], '羰基硫': ['硫化羰'], '自燃温度': ['引燃温度'], '苄醇': ['苯甲醇'], '调节阀': ['控制阀'], '邻甲酚': ['邻甲基苯酚'], '闪点': ['闪火点'], '间甲酚': ['间甲基苯酚'], 'SDS': ['化学品安全技术说明书', '安全技术说明书'], 'LOPA': ['保护层分析']})
url_overrides={'二甲基亚砜': 'https://bkso.baidu.com/item/%E4%BA%8C%E7%94%B2%E5%9F%BA%E4%BA%9A%E7%A0%9C/789855', '硝基苯': 'https://bkso.baidu.com/item/%E7%A1%9D%E5%9F%BA%E8%8B%AF/1551470', '苯胺': 'https://bkso.baidu.com/item/%E8%8B%AF%E8%83%BA/1466870', 'SDS': 'https://bkso.baidu.com/item/%E5%8C%96%E5%AD%A6%E5%93%81%E5%AE%89%E5%85%A8%E6%8A%80%E6%9C%AF%E8%AF%B4%E6%98%8E%E4%B9%A6', 'LOPA': 'https://bkso.baidu.com/item/%E4%BF%9D%E6%8A%A4%E5%B1%82%E5%88%86%E6%9E%90'}
if retry:pages=[p for p in pages if p["entity"] in aliases or p["entity"] in url_overrides]
report["total"]=len(pages)
for i,p in enumerate(pages,1):
 name=p['entity'];existing=next((s for s in p.get('external_sources',[]) if s.get('source_name')=='百度百科'),{})
 try:
  record=reader.read(name,url_overrides.get(name) or existing.get('url'),aliases.get(name,[]),prefer_public=True)
  report['fetched'].append({'entity':name,'title':record['title'],'url':record['url'],'sections':len(record['sections'])})
  current=service.repo.read(name);rid=current['revision_id']
  if rid!=p['revision_id']:report['conflicts'].append(name);continue
  new=copy.deepcopy(current)
  section_sources=new.setdefault('section_sources',{})
  for section in new['sections']:
   title=section['section'];sources=section_sources.setdefault(title,[])
   sources[:]=[s for s in sources if s.get('source_name')!='百度百科']+[chapter_source(record,title)]
  new['external_sources']=[s for s in new.get('external_sources',[]) if s.get('source_name')!='百度百科']
  summary=chapter_source(record,'基本概述');summary['summary']=summary.get('excerpt','')
  new['external_sources'].append(summary)
  new['baike_refresh']={'retrieved_at':record['retrieved_at'],'url':record['url'],'html_sha256':record['html_sha256']}
  if not validate_revision(new)['ok']:raise ValueError('版本校验失败')
  result=service.repo.commit(name,new,rid,'baike_official_public_refresh',service.repo.reviews(rid))
  report['updated'].append({'entity':name,'revision':result['revision_id'],'excerpts':sum(s.get('role')=='excerpt' and s.get('source_name')=='百度百科' for values in section_sources.values() for s in values)})
 except Conflict:report['conflicts'].append(name)
 except Exception as e:
  report['unavailable'].append({'entity':name,'error':str(e)[:240]})
  response=getattr(e,'response',None)
  if getattr(response,'status_code',None) in (403,429) or '安全验证' in str(e):
   report['blocked']={'entity':name,'error':str(e)[:240]};report['processed']=i
   (out/report_file).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
   print(json.dumps({'blocked':True,'processed':i}),flush=True);break
 report['processed']=i
 temp=out/'refresh.tmp';temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(out/report_file)
 if i%25==0:print(json.dumps({'processed':i,'fetched':len(report['fetched']),'unavailable':len(report['unavailable']),'conflicts':len(report['conflicts'])}),flush=True)
 time.sleep(.6)
report['completed_at']=now();(out/report_file).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'complete':True,'processed':report.get('processed',0),'fetched':len(report['fetched']),'unavailable':len(report['unavailable']),'conflicts':len(report['conflicts'])}),flush=True)
