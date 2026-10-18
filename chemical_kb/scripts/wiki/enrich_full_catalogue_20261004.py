import sys,json,copy,tarfile,shutil
from pathlib import Path
base=Path('/root/autodl-tmp/chemical_kb');sys.path[:0]=[str(base),str(base/'scripts/wiki')]
from core.wiki.service import WikiService
from core.wiki.citations import validate_revision,digest
from core.wiki.baike import chapter_source
from generate_wiki_catalogue_20261003 import wiki_material
out=base/'docs/wiki_full_catalogue_20261004';stage=out/'materials';stage.mkdir(exist_ok=True)
with tarfile.open('/root/autodl-tmp/wiki-full-materials-20261004.tgz') as t:
 for member in t.getmembers():
  target=(stage/member.name).resolve();assert target.is_relative_to(stage.resolve()) and not member.issym() and not member.islnk()
 t.extractall(stage)
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
wiki={r['name']:r for r in read(stage/'wikipedia_sections.json') if r.get('status')=='fetched'}
baidu={r['name']:r for r in read(out/'baidu_materials.json') if r.get('status')=='fetched'}
pub={r['name']:r for r in read(stage/'pubchem_metadata.json')}
s=WikiService(base/'data/wiki');report={'updated':[],'skipped':[],'errors':[],'wikipedia_articles':len(wiki),'baidu_articles':len(baidu),'structure_images':len(pub)}
bridge={'适用对象与边界':'系统与适用边界','设施与介质关联':'设施与管理关联','风险与异常情景':'风险与失效情景','管理与核查':'核查项目','原文与案例':'事故阅读与复盘','防范与改进':'预防与检查'}
for name in sorted(set(wiki)|set(baidu)|set(pub)):
 try:
  old=s.repo.read(name);assert old.get('catalogue_batch')=='full_catalogue_20261004';new=copy.deepcopy(old);titles=[v['section'] for v in new['sections']];sources=new['section_sources']
  if name in wiki:
   material=wiki_material(name,titles,wiki,english=pub.get(name,{}).get('english'))
   for title in titles:sources[title]=[v for v in sources[title] if v['source_name']!='Wikipedia']+[material[title][0]]
  if name in baidu:
   record=copy.deepcopy(baidu[name]);record['sections'].sort(key=lambda v:0 if any(k in v['heading'] for k in ['物理','理化','物化']) else 1)
   for title in titles:
    value=chapter_source(record,bridge.get(title,title));value['section']=title;sources[title]=[v for v in sources[title] if v['source_name']!='百度百科']+[value]
  new['external_sources']=[dict(v,summary=v.get('excerpt','')) for v in sources['基本概述']]
  if name in pub:
   p=pub[name];media=s.repo.root/'media';media.mkdir(exist_ok=True);shutil.copy2(stage/'pubchem_images'/p['image_file'],media/p['image_file'])
   new['illustration']={'url':'/api/wiki/platform/media/'+p['image_file'],'page_url':'https://pubchem.ncbi.nlm.nih.gov/compound/'+str(p['CID']),'caption':name+'化学结构示意','description':'化学结构示意','source_name':'PubChem','artist':'PubChem / CID '+str(p['CID']),'license':'PubChem来源与使用说明','license_url':'https://pubchem.ncbi.nlm.nih.gov/docs/copyright'}
   new['pubchem_reference']=p;new['chemical_profile']={'english':p['english'],'formula':p['MolecularFormula'],'scope':new.get('product_scope','')}
  signature=digest({'sources':sources,'pubchem':new.get('pubchem_reference')})
  if old.get('catalogue_material_hash')==signature:report['skipped'].append(name);continue
  check=validate_revision(new)
  if not check['ok']:raise ValueError(str(check))
  new['catalogue_material_hash']=signature
  s.repo.commit(name,new,old['revision_id'],reason='full_catalogue_materials_20261004',inherited=s.repo.reviews(old['revision_id']));report['updated'].append(name)
 except Exception as e:report['errors'].append({'entity':name,'error':str(e)})
(out/'enrichment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in report.items()},ensure_ascii=False))

