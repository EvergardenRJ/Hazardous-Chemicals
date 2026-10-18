import sys,json,re,hashlib,subprocess,collections,urllib.request
from pathlib import Path
base=Path('/root/autodl-tmp/chemical_kb');sys.path.insert(0,str(base))
from core.wiki.service import WikiService
from core.wiki.citations import validate_revision
s=WikiService(base/'data/wiki');out=base/'docs/wiki_full_catalogue_20261004';plan=json.loads((out/'generation_plan.json').read_text());pages={e['entity']:s.repo.read(e['entity']) for e in s.repo.list()};docs={p.get('source_doc_id'):p for p in pages.values() if p.get('source_doc_id')};new=[pages[r['name']] for r in plan['new_pages']]
report={'entries':len(pages),'types':dict(collections.Counter(p.get('page_type','chemical') for p in pages.values())),'new_pages':len(new),'source_pages_enriched':sum(bool(p.get('catalogue_document_hash')) for p in docs.values()),'invalid':[],'missing_sources':[],'uncovered_names':[],'missing_links':[],'quote_errors':[],'model_citation_errors':[]}
for p in pages.values():
 if not validate_revision(p)['ok']:report['invalid'].append(p['entity'])
report['unwanted_body']=[p['entity'] for p in pages.values() if any(v in p['markdown'] for v in ['Codex 当前会话','仅支持本片段，登记信息待核实','待审核'])]
for p in new+list(docs.values()):
 ev={e['evidence_id']:e['metadata'] for e in p['evidence']}
 for sec in p['sections']:
  if {v['source_name'] for v in p.get('section_sources',{}).get(sec['section'],[])}!={'Wikipedia','百度百科'}:report['missing_sources'].append([p['entity'],sec['section']])
  for b in sec['knowledge_blocks']:
   if b['knowledge_source']=='model_prior' and b['evidence_ids']:report['model_citation_errors'].append(p['entity'])
   for quote in re.findall(r'(?m)^>[^\n]*(?:\n>[^\n]*)*',b['text']):
    raw='\n'.join(v[2:] if v.startswith('> ') else v[1:] for v in quote.split('\n'))
    if not any(raw in p['evidence'][int(i)-1]['metadata'].get('text','') for i in b['evidence_ids'] if 0<int(i)<=len(p['evidence'])):report['quote_errors'].append([p['entity'],sec['section']])
 for target in re.findall(r'\[\[([^\]\n]+)\]\]',p['markdown']):
  if target not in pages:report['missing_links'].append([p['entity'],target])
 for rec in p.get('accident_reading',[]):assert rec['evidence_id'] in ev,p['entity']
for item in plan['coverage']:
 if item.get('page') in pages:continue
 matches=[d for d in item['source_doc_ids'] if d in docs and any(r['name']==item['name'] and set(r['source_chunk_ids'])&set(item['source_chunk_ids']) for r in docs[d].get('document_entities',[]))]
 if not matches:report['uncovered_names'].append([item['type'],item['name']])
report['snapshot_names']=len(plan['coverage']);report['new_section_counts']=dict(collections.Counter(len(p['sections']) for p in new))
report['encyclopedia_excerpts']={name:sum(v.get('role')=='excerpt' for p in pages.values() for values in p.get('section_sources',{}).values() for v in values if v['source_name']==name) for name in ('Wikipedia','百度百科')}
report['new_encyclopedia_excerpts']={name:sum(v.get('role')=='excerpt' for p in new for values in p.get('section_sources',{}).values() for v in values if v['source_name']==name) for name in ('Wikipedia','百度百科')}
report['illustrated_pages']=sum(bool(p.get('illustration')) for p in pages.values());report['new_illustrated_pages']=sum(bool(p.get('illustration')) for p in new);report['new_accident_readings']=sum(len(p.get('accident_reading',[])) for p in new)
report['metadata_sha256']=hashlib.sha256((base/'data/vector_store/index_metadata.json').read_bytes()).hexdigest();report['metadata_unchanged']=report['metadata_sha256']=='20c56b69f21fd92c15bf562230dbdb042d6dc82eda2cea9b07846ba4a2b11af6'
report['kg_process']=subprocess.check_output(['ps','-o','pid,ni,args','-p','5132'],text=True);report['gpu_processes']=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader'],text=True)
with urllib.request.urlopen('http://127.0.0.1:8503/api/wiki/platform',timeout=120) as r:report['live_summary']=json.load(r)
errors=['invalid','missing_sources','uncovered_names','missing_links','quote_errors','model_citation_errors','unwanted_body'];report['passed']=report['entries']==2128 and report['source_pages_enriched']==1061 and report['metadata_unchanged'] and not any(report[k] for k in errors)
(out/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in report.items() if k!='live_summary'},ensure_ascii=False));assert report['passed']
