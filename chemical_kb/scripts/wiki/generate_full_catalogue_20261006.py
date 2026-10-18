"""Generate evidence-backed catalogue pages from a frozen names snapshot; no inference."""
import os,sys,json,re,copy,time,collections,sqlite3,hashlib
from pathlib import Path
from urllib.parse import quote
ROOT=Path(os.environ.get('CHEM_KB_BASE_DIR','/root/autodl-tmp/chemical_kb'));sys.path.insert(0,str(ROOT))
from core.wiki.service import WikiService
from core.wiki.repository import Conflict,NotFound,now
from core.wiki.citations import bind_sections,validate_revision,digest,evidence_id,SECTIONS,CITATION
BATCH='full_catalogue_20261006'
CHEM_NOTES={
'基本概述':'物质名称、商品名称与实际产品成分应分别记录；浓度与物态采用对应产品和原文资料的描述。',
'理化性质':'比较物性时，应同时记录物态、浓度、温度、压力及测试方法；混合物的组分变化会改变物性。',
'危险特性':'危险辨识应覆盖燃烧、分解、氧化还原、不相容物接触和容器受压等情景，具体危险类别采用对应产品资料。',
'健康危害':'暴露辨识需区分吸入、皮肤和眼睛接触，以及接触时间、物态和共存组分。',
'生产与使用':'用途、接触介质与作业环境共同决定安全控制边界；生产、储存、转移和使用环节分别记录。',
'储存要求':'储存检查包括容器完整性、介质相容性、环境条件、分区隔离和异常监测。',
'运输与装卸':'运输与装卸时核对实际组分、包装容器、装卸连接、现场隔离和适用的运输分类。',
'设备设施与自动化控制':'介质相容性、密封完整性、温压监测、异常报警与联锁应按设备工况配套考虑。',
'个体防护':'防护选择应对应实际接触途径、作业条件和材料耐受性；工程控制与个体防护分别落实。',
'泄漏应急':'泄漏场景的辨识对象包括释放位置、物态、扩散路径、点火源和人员暴露；现场处置依据对应介质的应急方案。',
'火灾/爆炸处置':'火灾场景应区分物质本身、包装容器和周围火源，并识别受热分解产物及可能的容器受压。',
'急救':'事故记录中的介质名称、浓度、接触途径、接触时间和症状有助于向专业救援与医疗人员准确交接信息。',
'典型事故经验':'事故复盘按时间线区分现场事实、报告认定原因、保护措施状态与整改记录。',
'常见事故原因':'失效分析分别考虑介质条件、设备完整性、作业活动、保护措施和管理要求之间的联系。',
'防范与整改措施':'整改措施应对应已识别的失效情景，并记录责任对象、验证方式和持续检查要求。',
'相关标准法规':'适用标准与法规按产品分类、设施用途、作业活动、版本日期和管辖范围分别核对。',
'知识总结':'安全核查围绕产品身份、物态与浓度、接触场景、设备边界、保护措施和异常处置记录展开。'}
KEYS={'理化性质':['物性','物理','沸点','熔点','浓度','温度','密度','溶解'],'危险特性':['危险','腐蚀','易燃','氧化','分解'],'健康危害':['中毒','毒性','窒息','接触','刺激'],'生产与使用':['生产','工艺','用途','原料'],'储存要求':['储存','贮存','仓库','储罐'],'运输与装卸':['运输','装卸','道路','槽车'],'设备设施与自动化控制':['设备','报警','联锁','装置'],'个体防护':['防护','呼吸','手套'],'泄漏应急':['泄漏','应急'],'火灾/爆炸处置':['火灾','爆炸','灭火','燃烧'],'急救':['救援','急救','医院'],'典型事故经验':['事故','调查'],'常见事故原因':['原因','隐患','违章'],'防范与整改措施':['整改','防范','措施','建议'],'相关标准法规':['标准','法规','规定','条例']}
NODE_NOTES={'基本概述':'名称、对象范围、相关设施和原文记录应结合具体场景阅读。','适用对象与边界':'区分生产、储存、运输、检维修等活动，按实际对象和工况划分评价边界。','设施与介质关联':'核对相关介质、设备、连接关系、作业活动及保护措施在现场的实际状态。','风险与异常情景':'风险情景分别记录触发条件、异常现象、可能后果与现有保护措施。','管理与核查':'检查记录包括适用依据、实际状态、异常发现、责任分工和整改验证。','原文与案例':'原文中的时间、地点、设备和作业条件用于界定事件或要求的具体范围。','防范与改进':'防范措施围绕风险辨识、设备完整性、作业许可、监护和异常响应持续核查。','关联阅读':'对照相关资料和主题，核对对象名称、适用条件与原文所述事实。'}
DOC_KEYS={'适用范围':['适用','范围','目的','本标准','本办法'],'关键条款与要求':['必须','应当','不得','禁止','应符合','应设置','条','职责'],'事故与异常记录':['事故','死亡','受伤','泄漏','爆炸','异常'],'防范措施与检查':['整改','建议','检查','防范','措施','检验','检测','管理']}

def norm(text):return re.sub(r'[^\w]','',__import__('unicodedata').normalize('NFKC',str(text)).casefold())
def clean_quote(text):return str(text).strip()
def excerpt(row,terms=(),limit=520):
 text=clean_quote(row.get('text',''));pos=next((text.find(t) for t in terms if t and text.find(t)>=0),0);start=max(0,pos-90);q=text[start:start+limit].strip()
 q=max(re.split(r'[\x00-\x08\x0b\x0c\x0e-\x1f]',q),key=len).strip()
 return q if len(q)>=25 and not CITATION.search(q) and '\ufffd' not in q else ''
def original_section(title,pairs,note=None,links=None):
 blocks=[];chunks=[];content=[]
 if note:
  content.append(note);blocks.append({'text':note,'knowledge_source':'model_prior','evidence_ids':[]})
 for row,text in pairs:
  if not text:continue
  chunks.append({'metadata':row});n=len(chunks)
  piece='> '+text.replace('\n','\n> ')+'\n\n[Wiki证据'+str(n)+']'
  content.append(piece);blocks.append({'text':piece,'knowledge_source':'grounded','evidence_ids':[n]})
 if links:
  piece='相关条目：'+'、'.join('[['+n+']]' for n in links);content.append(piece);blocks.append({'text':piece,'knowledge_source':'model_prior','evidence_ids':[]})
 if not content:return None
 return {'section':title,'content':'\n\n'.join(content),'knowledge_blocks':blocks,'evidence':chunks,'_validated':True}

def source_links(name,titles):
 return {t:[{'source_name':'Wikipedia','title':name,'url':'https://en.wikipedia.org/w/index.php?search='+quote(name,safe=''),'section':t,'role':'reading_link'},{'source_name':'百度百科','title':name,'url':'https://bkso.baidu.com/item/'+quote(name,safe=''),'section':t,'role':'reading_link'}] for t in titles}

class CatalogueGenerator:
 def __init__(self,service,rows,plan,base=None):
  self.s=service;self.base=Path(base or ROOT);self.rows={str(r['chunk_id']):r for r in rows};self.plan=plan;self.by_doc=collections.defaultdict(list)
  for r in rows:self.by_doc[str(r['doc_id'])].append(r)
  self.old={e['entity']:e for e in service.repo.list()};self.doc_pages={};self.pages_by_doc=collections.defaultdict(set);self.labels_by_doc=collections.defaultdict(list)
  for e in self.old.values():
   p=service.repo.read(e['entity'])
   if p.get('source_doc_id'):self.doc_pages[p['source_doc_id']]=p['entity']
  for r in plan['coverage']:
   for doc in r['source_doc_ids']:
    self.labels_by_doc[doc].append(r)
    if r.get('page'):self.pages_by_doc[doc].add(r['page'])
  self.pdf_counts=collections.Counter(norm(f.stem) for f in (self.base/'data/pdf').rglob('*.pdf'))
  self.names=set(self.old)|{r['name'] for r in plan['new_pages']};self.report={'batch':BATCH,'before':len(self.old),'created':[],'source_updated':[],'skipped':[],'conflicts':[],'errors':[],'local_gpu':False}
  meta=self.base/'data/vector_store/index_metadata.json';self.stamp=digest([meta.stat().st_mtime_ns,meta.stat().st_size]) if meta.exists() else None
 def commit(self,name,sections,extra,expected=None):
  sections=[s for s in sections if s];bound,evidence,errors=bind_sections(sections)
  p={'schema_version':2,'sections':bound,'evidence':evidence,'binding_errors':errors,'source_stamp':self.stamp,'corpus_doc_ids':sorted(self.by_doc),**extra}
  p['validation']=validate_revision(p)
  if not p['validation']['ok']:raise ValueError('; '.join(p['validation']['errors']))
  return self.s.repo.commit(name,p,expected,BATCH,self.s.repo.reviews(expected) if expected else None)
 def choose(self,rows,keys=(),limit=3,terms=()):
  scored=sorted(enumerate(rows),key=lambda p:(-sum(k in p[1].get('text','') for k in keys),p[0]));out=[];used=set()
  for _,row in scored:
   if keys and not any(k in row.get('text','') for k in keys):continue
   q=excerpt(row,terms)
   if q and row['chunk_id'] not in used:out.append((row,q));used.add(row['chunk_id'])
   if len(out)>=limit:break
  return out
 def readings(self,rows):
  out=[];seen=set()
  for r in rows:
   if r['doc_id'] in seen or '事故' not in str(r.get('document_type','')):continue
   seen.add(r['doc_id']);out.append({'source_name':'本地事故调查报告','title':r['title'],'doc_id':r['doc_id'],'chunk_id':r['chunk_id'],'page':r.get('page_start'),'evidence_id':evidence_id({'metadata':r}),'excerpt':excerpt(r,(),220),'relation_type':'原文相关记录','reason':'报告原文包含本条目名称或对象记录，可按实际事件条件阅读。','pdf_available':any(self.pdf_counts[norm(r.get(k,''))]==1 for k in ('title','doc_id','code'))})
   if len(out)>=4:break
  return out
 def entity_page(self,item):
  name=item['name']
  if name in self.old:
   self.report['skipped'].append(name);return
  rows=[self.rows[c] for c in item['source_chunk_ids'] if c in self.rows];rows.sort(key=lambda r:(r['doc_id'],str(r.get('page_start')),r['chunk_id']))
  if not rows:raise ValueError('原文片段缺失')
  related=sorted({self.doc_pages[d] for d in item['source_doc_ids'] if d in self.doc_pages})[:8];peer=sorted({n for d in item['source_doc_ids'] for n in self.pages_by_doc[d] if n!=name and n in self.names})[:8]
  titles=SECTIONS if item['page_type']=='chemical' else list(NODE_NOTES)
  sections=[]
  for title in titles:
   keys=KEYS.get(title,[]) if item['page_type']=='chemical' else (['事故','调查'] if title=='原文与案例' else ['管理','检查','规定'] if title=='管理与核查' else [])
   pairs=self.choose(rows,keys,2 if item['page_type']=='chemical' else 3,item['aliases'])
   if title=='基本概述' or title=='原文与案例':pairs=self.choose(rows,(),3,item['aliases'])
   if title in ('知识总结','关联阅读'):pairs=[]
   note=CHEM_NOTES[title] if item['page_type']=='chemical' else NODE_NOTES[title]
   boundaries={'三氯化铁溶液':'本条目为三氯化铁溶液，浓度及杂质条件按实际产品区分。','二氯乙烷':'本条目保留原文中的二氯乙烷名称；1,1-与1,2-二氯乙烷分别识别，未明确异构体的记录不合并为某一异构体。','甲胺水溶液':'本条目为甲胺水溶液，与无水甲胺分别识别；浓度按实际产品区分。','钛硅分子筛催化剂':'本条目为催化剂材料；组成、载体、使用状态与夹带介质共同决定适用条件。'}
   if title=='基本概述' and name in boundaries:note=boundaries[name]+'\n\n'+note
   if 'enterprise' in item['entity_types']:
    note={'基本概述':'沿报告时间线分别记录单位名称、相关设施、涉事地点和经营活动。','适用对象与边界':'企业整体、涉事装置和具体作业地点应分别识别，事件记录按报告给出的范围阅读。','设施与介质关联':'对照报告中的设施、介质与作业活动，保留各项记录的来源文件和事件日期。','风险与异常情景':'异常现象、人员活动、设施状态与报告认定原因应分别记录。','管理与核查':'核查责任分工、作业管理、设备完整性及报告提出的整改事项。','原文与案例':'调查报告中的事件过程和处置记录可按原文时间线对照。','防范与改进':'改进事项应与报告所列问题和整改要求逐项对应。','关联阅读':'对照事故调查报告、涉及的介质与设备条目阅读。'}[title]
   sections.append(original_section(title,pairs,note,related+peer if title in ('知识总结','关联阅读') else None))
  extra={'page_type':item['page_type'],'entity_types':item['entity_types'],'entity_aliases':item['aliases'],'catalogue_batch':BATCH,'catalogue_item_hash':digest(item),'section_sources':source_links(name,titles),'accident_reading':self.readings([e['metadata'] for sec in sections for e in sec['evidence']]),'product_scope':name+'；涉及条件按所引用原文和具体产品、设施资料区分。','name_discovery':'原文中确认的名称；未采用候选关系作为事实'}
  page=self.commit(name,sections,extra);self.old[name]=self.s.repo.entry(name);self.report['created'].append({'entity':name,'revision':page['revision_id'],'page_type':item['page_type'],'sections':len(sections)})
 def source_page(self,name,docid):
  old=self.s.repo.read(name)
  if old['revision_id']!=self.old[name]['draft_revision']:raise Conflict('资料页在任务期间已由其他操作更新')
  rows=sorted(self.by_doc[docid],key=lambda r:(int(r.get('page_start') or 0),r['chunk_id']));context=self.labels_by_doc.get(docid,[])
  signature=digest([digest(rows),[{k:c.get(k) for k in ('name','page','coverage_mode','type','source_chunk_ids')} for c in context]])
  if old.get('catalogue_document_hash')==signature:self.report['skipped'].append(name);return
  first=next((r for r in rows if excerpt(r,(),420)),rows[0]);desc='资料名称：'+str(first.get('title') or docid)+'。\n\n资料类型：'+str(first.get('document_type') or '原文资料')+'；收录 '+str(len(rows))+' 个原文片段。'
  overview=original_section('资料概览',[(first,excerpt(first,(),420) or str(first.get('text') or first.get('title')).strip()[:420])],desc+' [Wiki证据1]')
  overview['knowledge_blocks'][0].update(knowledge_source='grounded',evidence_ids=[1])
  sections=[overview]
  for title,keys in DOC_KEYS.items():
   pairs=self.choose(rows,keys,6)
   if pairs:sections.append(original_section(title,pairs))
  # Named clauses/requirements remain scoped to their source document, including article numbers.
  scoped=[c for c in context if c['type'] in ('clause','requirement') or c['coverage_mode']=='document_context']
  pairs=[];seen=set()
  for c in scoped:
   for cid in c['source_chunk_ids']:
    row=self.rows.get(cid)
    if row and row['doc_id']==docid and cid not in seen:
     q=excerpt(row,[c['name']],600)
     if q:pairs.append((row,q));seen.add(cid)
     if len(pairs)>=12:break
   if len(pairs)>=12:break
  if pairs:sections.append(original_section('原文条款与现场记录',pairs))
  if not any(s and s['section']=='原文摘录' for s in sections):sections.append(original_section('原文摘录',self.choose(rows,(),4)))
  related=sorted(n for n in self.pages_by_doc[docid] if n in self.names)[:50]
  if context:
   table=[];index={};parts=[];blocks=[]
   for c in context:
    candidates=[self.rows[cid] for cid in c['source_chunk_ids'] if cid in self.rows and self.rows[cid]['doc_id']==docid]
    if not candidates:continue
    row=next((r for r in candidates if norm(c['name']) in norm(r.get('text','')+' '+r.get('title',''))),None)
    if not row:continue
    if row['chunk_id'] not in index:table.append({'metadata':row});index[row['chunk_id']]=len(table)
    n=index[row['chunk_id']];label=c['name'].replace('\n',' ')
    target=c.get('page');piece='- '+label+('（[['+target+']]）' if target and target!=name else '')+' [Wiki证据'+str(n)+']'
    parts.append(piece);blocks.append({'text':piece,'knowledge_source':'grounded','evidence_ids':[n]})
   if parts:sections.append({'section':'术语、条款与现场对象','content':'\n'.join(parts),'knowledge_blocks':blocks,'evidence':table,'_validated':True})
  titles=[s['section'] for s in sections if s]
  extra={k:copy.deepcopy(v) for k,v in old.items() if k not in ('sections','evidence','markdown','validation','binding_errors','revision_id','created_at','base_revision','wiki_id','entity')}
  extra.update(catalogue_batch=BATCH,catalogue_document_hash=signature,source_content_hash=digest(rows),section_sources=source_links(str(first.get('title') or docid),titles),product_scope=str(first.get('title') or docid),document_entities=[{'name':c['name'],'page':c.get('page'),'source_chunk_ids':[cid for cid in c['source_chunk_ids'] if cid in self.rows and self.rows[cid]['doc_id']==docid]} for c in context])
  page=self.commit(name,sections,extra,old['revision_id']);self.report['source_updated'].append({'entity':name,'revision':page['revision_id'],'doc_id':docid,'sections':len(titles),'named_records':len(context)})
 def run(self,progress=None):
  tasks=[('entity',item) for item in self.plan['new_pages']]+[('source',(name,doc)) for doc,name in sorted(self.doc_pages.items()) if doc in self.by_doc]
  self.report['total']=len(tasks)
  for i,(kind,value) in enumerate(tasks,1):
   try:self.entity_page(value) if kind=='entity' else self.source_page(*value)
   except Conflict:self.report['conflicts'].append(value['name'] if kind=='entity' else value[0])
   except Exception as e:self.report['errors'].append({'entity':value['name'] if kind=='entity' else value[0],'error':str(e)[:600]})
   self.report['processed']=i
   if progress and (i%25==0 or i==len(tasks)):
    temp=progress.with_suffix('.tmp');temp.write_text(json.dumps(self.report,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(progress)
    print(json.dumps({'processed':i,'total':len(tasks),'created':len(self.report['created']),'source_updated':len(self.report['source_updated']),'errors':len(self.report['errors']),'conflicts':len(self.report['conflicts'])}),flush=True)
   time.sleep(.012)
  return self.report

if __name__=='__main__':
 out=ROOT/'docs/wiki_full_catalogue_20261006';out.mkdir(parents=True,exist_ok=True)
 plan=json.loads((out/'generation_plan.json').read_text(encoding='utf-8'));rows=json.loads((ROOT/'data/vector_store/index_metadata.json').read_text(encoding='utf-8'))
 rows=[r for r in rows if str(r.get('status','')).lower() not in ('withdrawn','deleted','repealed','inactive','废止','撤回')]
 generator=CatalogueGenerator(WikiService(),rows,plan)
 report=generator.run(out/'generation.json');print(json.dumps({'complete':True,'created':len(report['created']),'source_updated':len(report['source_updated']),'errors':report['errors'],'conflicts':report['conflicts']},ensure_ascii=False),flush=True)
