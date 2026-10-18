"""Generate the finite 200 chemical + 150 topic catalogue without local inference."""
import os,sys,json,re,copy,time,sqlite3,hashlib,shutil,unicodedata
from pathlib import Path
from collections import defaultdict
from urllib.parse import quote
BASE=Path(os.environ.get('CHEM_KB_BASE_DIR','/root/autodl-tmp/chemical_kb'));sys.path.insert(0,str(BASE))
from core.wiki.platform import Platform
from core.wiki.service import WikiService
from core.wiki.repository import NotFound,Conflict,now
from core.wiki.citations import SECTIONS,bind_sections,validate_revision,digest,evidence_id,CITATION
BATCH='wiki_expansion_20261003';INPUT=Path(os.environ.get('WIKI_EXPANSION_INPUT',str(BASE/'.wiki_expansion_stage/input')))
KEYWORDS={'基本概述':['introduction'],'理化性质':['properties','structure','chemistry','physical'],'危险特性':['safety','hazard','flammab','reactiv'],'健康危害':['toxic','health','exposure','carcinogen'],'生产与使用':['production','uses','applications','synthesis'],'储存要求':['storage','stability','handling','polymeriz'],'运输与装卸':['transport','shipping','handling'],'设备设施与自动化控制':['industrial','production','manufactur'],'个体防护':['exposure','safety','health'],'泄漏应急':['environment','safety','exposure'],'火灾/爆炸处置':['flammab','hazard','safety'],'急救':['toxic','health','treatment'],'典型事故经验':['accident','incident','disaster'],'常见事故原因':['incident','accident','stability'],'防范与整改措施':['safety','exposure','environment'],'相关标准法规':['regulation','legal','occupational','restriction'],'知识总结':['introduction']}

def load(name):return json.loads((INPUT/name).read_text(encoding='utf-8-sig'))
def tsv(name,fields):return [dict(zip(fields,[v.strip() for v in r.split('|')])) for r in (INPUT/name).read_text(encoding='utf-8-sig').splitlines() if r.strip()]

def clean(text):
    text=str(text or '')
    text=re.sub(r'本页由\s*Codex\s*当前会话依据模型背景知识编写（[^）]*），具体模型版本未由环境提供。\s*本地原文摘录单独绑定证据；每个摘录仅说明原文所述内容，其他段落保留模型补充来源。','',text)
    text=text.replace('来源：模型背景知识（Codex 当前会话生成，待核实）','来源：大模型知识库').replace('（仅支持本片段，登记信息待核实）','')
    text=text.replace('本页与本地资料共同构成待审核知识入口。','').replace('本页由 Codex 当前会话根据模型背景知识编写。','')
    for sentence in ['当前草稿未填入未经核实的闪点、爆炸极限或暴露限值。','这部分用途概述不提供生产或反应操作参数。','本段是模型归纳的复盘问题，未把它表述为某起已核实事故。','本段是待核实的知识框架，','本页未编造标准编号、法定限值或条款号；','模型补充可以用于导航和提出核实问题，转为正式发布前仍需核实高风险章节的证据和专家审核。','具体急救步骤和治疗属于待补证内容，本页不提供药物剂量或自行治疗方案。']:
        text=text.replace(sentence,'')
    return re.sub(r'\n{3,}','\n\n',text).strip()

def wiki_material(name,titles,wiki,old_sources=None,english=None):
    article=wiki.get(name,{});old={s['source_name']:s for s in (old_sources or [])}
    wurl=article.get('url') or old.get('Wikipedia',{}).get('url') or ('https://en.wikipedia.org/wiki/'+quote(english.replace(' ','_'),safe='') if english else 'https://en.wikipedia.org/w/index.php?search='+quote(name))
    burl=old.get('百度百科',{}).get('url') or 'https://baike.baidu.com/item/'+quote(name,safe='')
    result={}
    for title in titles:
        sources=[];w={'source_name':'Wikipedia','url':wurl,'title':article.get('title') or english or name,'role':'reading_link','section':title}
        paragraphs=article.get('sections',[]) if article.get('status')=='fetched' else []
        matches=[]
        for sec in paragraphs:
            heading=sec['heading'].lower();score=sum(4 for k in KEYWORDS.get(title,[]) if k in heading)
            if score:matches.append((score,sec))
        if matches:
            sec=max(matches,key=lambda r:r[0])[1];text=sec['text'][:460];stop=max(text.rfind('. '),text.rfind('; '))
            if stop>140:text=text[:stop+1]
            w.update(role='excerpt',excerpt=text,original_heading=sec['heading'],retrieved_at=article['retrieved_at'],license=article['license'],license_url=article['license_url'],external_source_id='wikipedia-'+digest([wurl,sec['heading'],text])[:24],language='en')
        b={'source_name':'百度百科','url':burl,'title':name,'role':'reading_link','section':title}
        # Cached original text is attached only to sections it actually covers.
        prior=old.get('百度百科',{});original=prior.get('original_intro','')
        chinese={'理化性质':['分子式','化学式','沸点','溶解','液体','固体','气体'],'危险特性':['易燃','有毒','氧化','腐蚀'],'健康危害':['有毒','毒性','刺激','腐蚀'],'生产与使用':['用于','用途','原料','工业']}
        if title=='基本概述' and prior.get('summary'):original=prior['summary']
        if original and (title=='基本概述' or any(k in original for k in chinese.get(title,[]))):
            b.update(role='excerpt',excerpt=original[:320],retrieved_at=prior.get('retrieved_at'),external_source_id=prior.get('external_source_id'),language='zh')
        sources.extend([w,b]);result[title]=sources
    return result

class Expansion:
    def __init__(self,service=None,base=None):
        self.base=Path(base or BASE);self.service=service or WikiService();self.p=Platform(self.service,self.base)
        self.chem=tsv('chemical_expansion_20261003.tsv',['name','english','formula','family','note']);self.topics=tsv('topic_expansion_20261003.tsv',['kind','name','definition','checks','related'])
        families=load('family_knowledge.json');self.families=families['families'];self.alias=families['aliases'];self.pubchem={r['name']:r for r in load('pubchem_metadata.json')};self.wiki={r['name']:r for r in load('wikipedia_sections.json')}
        cached=load('encyclopedia_sources_release_20261002.json')['sources'];self.cached={r['entity']:r for r in cached}
        self.rows=self.p.corpus();self.names={e['entity'] for e in self.service.repo.list()}|{x['name'] for x in self.chem+self.topics};self.candidates=defaultdict(list)
        aliases={'工业锅炉':['锅炉'],'安全仪表系统':['SIS','安全仪表'],'局部排风系统':['局部排风'],'紧急冲淋与洗眼装置':['洗眼','冲淋'],'围堰与事故池':['围堰','事故池'],'氨水':['氨水','氨溶液'],'N,N-二甲基甲酰胺':['二甲基甲酰胺','DMF'],'N,N-二甲基乙酰胺':['二甲基乙酰胺','DMAc'],'N-甲基-2-吡咯烷酮':['NMP','甲基吡咯烷酮'],'1,4-二氧六环':['二氧六环','二噁烷'],'IDLH':['IDLH']}
        self.term_names=defaultdict(set)
        for n in self.names:
            if n.startswith('资料：') or len(n)>45:continue
            for term in [n]+aliases.get(n,[]):self.term_names[term].add(n)
        self.chemical_names={x['name'] for x in self.chem}
        def norm(x):return re.sub(r'[^\w]','',unicodedata.normalize('NFKC',str(x)).casefold())
        self.pdf_names={norm(f.stem) for f in (self.base/'data/pdf').rglob('*.pdf')}
        self.norm=norm
        self.pattern=re.compile('|'.join(re.escape(t) for t in sorted(self.term_names,key=len,reverse=True)))
        for row in self.rows:
            if str(row.get('status','')).lower() in ('withdrawn','deleted','repealed','inactive','废止','撤回'):continue
            text=str(row.get('text',''));title=str(row.get('title',''))
            for match in self.pattern.finditer(text):
                if match.start()>0 and text[match.start()-1]=='聚':continue
                term=match.group()
                if term.isascii() and ((match.start()>0 and text[match.start()-1].isalnum()) or (match.end()<len(text) and text[match.end()].isascii() and text[match.end()].isalnum())):continue
                for name in self.term_names[term]:
                    if name in self.chemical_names and ((match.start()>0 and text[match.start()-1] in '一二三四五六邻间对甲乙丙丁氟氯溴硝氨羟氧硫聚基') or (match.end()<len(text) and text[match.end()] in '胺酚醚腈醛酰肼基')):continue
                    start=max(0,match.start()-65);stop=min(len(text),match.end()+190);q=text[start:stop].strip()
                    if len(q)<45 or '\ufffd' in q or CITATION.search(q):continue
                    self.candidates[name].append((4*int(name in title),row,q))
        self.report={'batch':BATCH,'before':self.p.summary(),'created':[],'updated':[],'skipped':[],'conflicts':[],'validation_errors':[],'local_gpu':False}
        self.family_names=defaultdict(list)
        for x in self.chem:self.family_names[self.alias.get(x['family'],x['family'])].append(x['name'])
    def selected(self,name,kind=None,limit=6):
        rows=sorted(self.candidates.get(name,[]),key=lambda r:(-r[0],str(r[1].get('chunk_id',''))));used=set();out=[]
        for score,row,q in rows:
            if row.get('doc_id') in used:continue
            if kind=='accident' and not ('事故' in str(row.get('document_type','')) or 'accident' in str(row.get('document_type','')).lower() or '调查' in str(row.get('title',''))):continue
            used.add(row.get('doc_id'));out.append((row,q))
            if len(out)>=limit:break
        return out
    def quote_section(self,section,body,selected):
        body='**来源：大模型知识库**\n\n'+clean(body);blocks=[{'text':body,'knowledge_source':'model_prior','evidence_ids':[],'model_source':{'provider':'Codex','source_label':'大模型知识库','generated_date':'2026-10-03'}}];table=[]
        for i,(row,q) in enumerate(selected,1):
            text='**本地文档原文摘录**\n\n'+q+'\n\n[Wiki证据'+str(i)+']';body+='\n\n'+text;blocks.append({'text':text,'knowledge_source':'grounded','evidence_ids':[i],'quote_text':q});table.append({'metadata':copy.deepcopy(row)})
        return {'section':section,'content':body,'knowledge_blocks':blocks,'evidence':table}
    def readings(self,name,fallback=None):
        cases=self.selected(name,'accident',2);direct=True
        if not cases and fallback:cases=self.selected(fallback,'accident',2);direct=False
        readings=[];evidence=[]
        for row,q in cases:
            readings.append({'source_name':'本地事故调查报告','title':row.get('title'),'doc_id':row.get('doc_id'),'chunk_id':row.get('chunk_id'),'page':row.get('page_start'),'evidence_id':evidence_id({'metadata':row}),'excerpt':q,'pdf_available':any(self.norm(row.get(k,'')) in self.pdf_names for k in ('title','doc_id','code')),'relation_type':'原文提及' if direct else '相关风险场景','reason':('报告原文提及'+name+'，可阅读实际介质、设备及事件链。' if direct else '报告原文提及'+fallback+'，可比较相关风险场景；不据此认定事故由'+name+'造成。')})
            evidence.append({'metadata':copy.deepcopy(row)})
        return readings,evidence
    def commit(self,name,sections,extra,expected=None,evidence=None,update=False):
        try:
            p=self.p.commit(name,sections,evidence=evidence,extra=extra,expected=expected,reason=BATCH)
            assert validate_revision(p)['ok'];self.report['updated' if update else 'created'].append({'entity':name,'revision':p['revision_id'],'page_type':extra.get('page_type'),'sections':len(p['sections']),'evidence':len(p['evidence'])})
            self.names.add(name);return p
        except Conflict:self.report['conflicts'].append(name);return None
    def chemical(self,x,replace=False):
        name=x['name'];expected=None
        try:
            prior=self.service.repo.read(name)
            if replace:expected=prior['revision_id']
            elif prior.get('expansion_batch')==BATCH:self.report['skipped'].append(name);return
            else:self.report['conflicts'].append(name);return
        except NotFound:pass
        key=self.alias.get(x['family'],x['family']);f=self.families[key];category,properties,hazard,health,uses,causes,equipment,storage=f
        links=self.family_names[key][:3]+(['氢气','甲烷'] if key=='gas' else ['甲醇','乙醇'] if key in ('alcohol','glycol','ether','ester','ketone') else ['硫酸','氢氧化钠']);links=[n for n in dict.fromkeys(links) if n!=name and n in self.names][:4]
        related='、'.join('[['+n+']]' for n in links);selected=self.selected(name);case_fallback='甲烷' if key=='gas' else '乙醇' if key in ('alcohol','ether','ester','hydrocarbon','aromatic','monomer') else '硫酸' if key in ('acid_org','acid_inorg','water_reactive') else None
        readings,case_evidence=self.readings(name,case_fallback)
        body={
        '基本概述':name+'（'+x['english']+'）属于'+category+'。'+x['note']+'。\n\n化学式或产品组成：'+x['formula']+'。与供货形态、浓度、异构组成及产品等级相关的差异应单独记录。',
        '理化性质':properties+'。'+x['note']+'。\n\n评价物性时需同时保留温度、压力、浓度和测试方法。物态变化、挥发和溶解行为应与实际产品组成对应。',
        '危险特性':hazard+'。\n\n该物质的识别重点：'+x['note']+'。危险场景需结合释放条件、反应接触、点火源和周围设施进行分析。',
        '健康危害':health+'。\n\n接触路径包括实际可能发生的吸入、皮肤或眼接触以及误食；暴露时长和共存物也是评价对象。'+x['note']+'。',
        '生产与使用':uses+'。'+x['note']+'。\n\n实际应用还涉及产品等级、杂质、工艺角色和材料相容性。可结合相关条目 '+related+' 区分物料身份及用途。',
        '储存要求':name+' 的储存评价重点为'+storage+'。\n\n物料身份与供货状态、容器材料、环境热负荷及库存变化应形成一致记录；适用条件见实际产品SDS和设施依据。',
        '运输与装卸':name+' 的运输身份应与实际产品组成及供货状态一致。交接环节需核对容器、接口、物料、检验状态及剩余介质。\n\n可关联 [[槽车装卸管理]]、[[气瓶使用管理]] 与 [[软管失效预防]]，检查转移过程中的误接、泄漏和非预期接触。',
        '设备设施与自动化控制':name+' 相关设施应重点核对'+equipment+'。\n\n检测对象、材料适用性及动作目标应与实际介质和事故场景对应。相关设施包括 [[气体检测与报警]]、[[机械完整性]] 与 [[控制回路失效]]。',
        '个体防护':防护文本(health,key)+'\n\n工程控制、物料密闭和作业组织与个体用品应共同评价。手套、衣物及呼吸防护的适用性依实际产品、接触路径和环境条件确定。',
        '泄漏应急':name+' 的释放场景需要识别'+hazard+'。'+x['note']+'。\n\n报警、避险、介质检测、隔离和专业响应的边界应写入对应预案。现场介质或浓度未知时，不以外观和气味判断可进入性。',
        '火灾/爆炸处置':name+' 的火灾评价需同时考虑'+hazard+'。受热容器、持续供料、反应产物及邻近设施会影响后果。\n\n可结合 [[火灾场景识别]]、[[多米诺效应]] 与实际产品消防资料，区分燃烧、压力失效及反应异常。',
        '急救':name+' 的接触响应应对应'+health+'。\n\n物质身份、接触路径、接触时长及现场监测信息应提供给医疗人员。救援前需要确认环境及防护能力，避免其他人员发生相同暴露。',
        '典型事故经验':('相关报告中可核查介质、设备状态、事件顺序以及已识别的管理问题。事故阅读入口列出具体报告与相关片段。' if readings else '可沿'+causes+'这些场景检查设备与管理边界，并在 [[事故复盘方法]] 中区分事实、假设与整改证据。')+'\n\n同类设施或相近介质的案例用于比较场景，不能直接替代本物质的调查结论。',
        '常见事故原因':name+' 的原因分析可从'+causes+'等候选环节展开。\n\n分析应关联物料身份、现场条件、监测、维修和交接记录。单一危险类别不足以建立事故因果链。',
        '防范与整改措施':整改文本(equipment,causes)+'\n\n相关管理条目：[[变更管理]]、[[机械完整性]]、[[保护层分析]]。措施应与具体失效场景及验证记录相对应。',
        '相关标准法规':name+' 的适用要求需要同时核对产品身份、设施用途、地域及文件版本。产品SDS、危险化学品管理、职业接触、储运和设施标准属于不同依据层次。\n\n可在下方原文中查阅相关资料，结合 [[SDS版本管理]] 与 [[化学品身份核对]] 记录适用条件。',
        '知识总结':name+' 的阅读主线是'+hazard+'。'+x['note']+'。\n\n继续阅读 '+related+'，以及 [[化学相容性]]、[[危险辨识与风险评估]]，将物质信息与具体工况联系起来。'}
        sections=[]
        for i,title in enumerate(SECTIONS):
            words={'储存要求':['储存','贮存'],'运输与装卸':['运输','装卸'],'健康危害':['中毒','接触','毒性'],'危险特性':['爆炸','燃烧','腐蚀'],'相关标准法规':['标准','规定','应']}.get(title,[])
            picks=sorted(selected,key=lambda r:-sum(w in r[1] for w in words))[:1] if selected and (title in ('基本概述','危险特性','健康危害','储存要求','运输与装卸','相关标准法规')) else []
            if title=='典型事故经验':picks=[(e['metadata'],r['excerpt']) for r,e in zip(readings,case_evidence)]
            sections.append(self.quote_section(title,body[title],picks))
        pub=self.pubchem.get(name,{});illustration=None
        if pub.get('image_file'):
            file=pub['image_file'];dest=self.service.repo.root/'media'/file;dest.parent.mkdir(exist_ok=True);shutil.copy2(INPUT/'pubchem_images'/file,dest)
            illustration={'url':'/api/wiki/platform/media/'+file,'page_url':'https://pubchem.ncbi.nlm.nih.gov/compound/'+str(pub['CID']),'source_name':'PubChem','caption':name+' · 化学结构示意','description':name+' 的二维化学结构示意图','artist':'PubChem','license':'PubChem 来源及使用说明','license_url':'https://pubchem.ncbi.nlm.nih.gov/docs/copyright'}
        extra={'page_type':x.get('page_type','chemical'),'expansion_batch':BATCH,'chemical_profile':{'english':x['english'],'formula':x['formula'],'class':x['family'],'scope':x['note']},'product_scope':x['note'],'illustration':illustration,'pubchem_reference':pub,'accident_reading':readings,'section_sources':wiki_material(name,SECTIONS,self.wiki,english=x['english'])}
        sources=extra['section_sources']['基本概述'];extra['external_sources']=[{**s,'summary':s.get('excerpt',''),'scope_note':'百科阅读入口' if s['role']=='reading_link' else ''} for s in sources]
        self.commit(name,sections,extra,expected=expected,update=bool(expected))
    def topic(self,x):
        name=x['name']
        try:
            prior=self.service.repo.read(name)
            if prior.get('expansion_batch')==BATCH:self.report['skipped'].append(name);return
            self.report['conflicts'].append(name);return
        except NotFound:pass
        checks=re.split('[、，]',x['checks']);related=[n for n in dict.fromkeys([x['related'],'危险辨识与风险评估','变更管理']) if n!=name and n in self.names]
        links='、'.join('[['+n+']]' for n in related);selected=self.selected(name,limit=3);readings,_=self.readings(name)
        texts=[('基本概述',name+'：'+x['definition']+'。'),('系统与适用边界','对象与评价边界包括'+x['checks']+'。\n\n实际介质、设备状态、设计依据和作业活动应与这一边界对应；用途变化会改变失效和暴露场景。'),('风险与失效情景','围绕'+x['checks']+'开展失效分析，将触发条件、顶事件、可能后果和现有控制分别记录。\n\n'+x['definition']+'。风险分析应覆盖正常状态、启动停车、维护和异常工况。'),('设施与管理关联','本条目的检查重点为'+x['checks']+'。\n\n相关设施或方法：'+links+'。关联用于组织核对对象与情景，具体要求依实际设施边界确定。'),('核查项目','\n'.join('- '+k+'：核对当前状态、适用依据、异常记录及责任边界。' for k in checks)+'\n\n核查结果可进一步关联故障模式、保护措施和整改验证。'),('原文与相关资料',('下列原文可用于核对'+name+'的相关对象与条件。' if selected else '可结合 '+links+' 和对应设备或工艺资料，核对 '+x['checks']+' 的实际状态及适用条件。')),('事故阅读与复盘','复盘时将'+x['checks']+'与时间线、现场状态和屏障有效性对应。\n\n'+('相关报告入口列出原文提及本条目的记录。' if readings else '可在 [[事故复盘方法]] 中整理事实、原因候选、来源及整改验证。')),('知识总结',x['definition']+'。重点核查 '+x['checks']+'；相关条目为 '+links+'。')]
        sections=[self.quote_section(title,text,selected if title=='原文与相关资料' else self.selected(name,'accident',2) if title=='事故阅读与复盘' else []) for title,text in texts]
        extra={'page_type':x['kind'],'expansion_batch':BATCH,'product_scope':x['definition'],'accident_reading':readings,'section_sources':wiki_material(name,[s['section'] for s in sections],self.wiki)}
        extra['external_sources']=[{**s,'summary':'','scope_note':'百科阅读入口'} for s in extra['section_sources']['基本概述']]
        self.commit(name,sections,extra)
    def update_existing(self):
        for entry in self.service.repo.list():
            if entry['entity'].startswith('资料：') or entry['entity'] in {x['name'] for x in self.chem+self.topics}:continue
            p=self.service.repo.read(entry['entity']);sections=copy.deepcopy(p['sections']);changed=False
            for s in sections:
                text=clean(s['content']);changed|=text!=s['content'];s['content']=text
                for b in s.get('knowledge_blocks',[]):b['text']=clean(b.get('text',''))
                s.pop('original_content',None);s.pop('original_knowledge_blocks',None);s['citation_scope']='global';s['evidence']=p['evidence']
            if p.get('page_type','chemical')=='chemical' and entry['entity'] in self.cached:
                cached=self.cached[entry['entity']];old_sources=copy.deepcopy(p.get('external_sources',[]))
                for src in old_sources:
                    if src['source_name']=='百度百科':src['original_intro']=cached['baidu'].get('original_intro','')
                new_sources=wiki_material(entry['entity'],[s['section'] for s in sections],self.wiki,old_sources,p.get('chemical_profile',{}).get('english'));changed|=p.get('section_sources')!=new_sources
            else:new_sources=p.get('section_sources')
            if not changed:continue
            extra={k:copy.deepcopy(v) for k,v in p.items() if k not in ('sections','evidence','markdown','revision_id','base_revision','created_at','wiki_id','entity','schema_version','validation','binding_errors','job_id','worker_owner')};extra['section_sources']=new_sources;extra['source_layout_batch']=BATCH
            bound,table,issues=bind_sections(sections,p['evidence']);payload={'schema_version':2,**extra,'sections':bound,'evidence':table,'binding_errors':issues};payload['validation']=validate_revision(payload)
            # Legacy invalid drafts stay invalid; valid pages must stay valid.
            if validate_revision(p)['ok']:assert payload['validation']['ok'],payload['validation']
            try:
                saved=self.service.repo.commit(entry['entity'],payload,p['revision_id'],BATCH,self.service.repo.reviews(p['revision_id']));self.report['updated'].append({'entity':entry['entity'],'revision':saved['revision_id'],'page_type':p.get('page_type','chemical')})
            except Conflict:self.report['conflicts'].append(entry['entity'])
    def run(self):
        self.update_existing()
        for i,x in enumerate(self.chem,1):
            self.chemical(x)
            if i%20==0:print(json.dumps({'chemicals_processed':i,'created':len(self.report['created'])},ensure_ascii=False),flush=True)
            time.sleep(.03)
        for i,x in enumerate(self.topics,1):
            self.topic(x)
            if i%25==0:print(json.dumps({'topics_processed':i,'created':len(self.report['created'])},ensure_ascii=False),flush=True)
            time.sleep(.03)
        self.report['after']=self.p.summary();self.report['completed_at']=now();self.p.event('catalogue_expansion',{'batch':BATCH,'created':len(self.report['created']),'updated':len(self.report['updated'])})
        folder=self.base/'docs/wiki_expansion_20261003';folder.mkdir(parents=True,exist_ok=True);(folder/'generation.json').write_text(json.dumps(self.report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'finished':True,'after':self.report['after'],'created':len(self.report['created']),'updated':len(self.report['updated']),'conflicts':self.report['conflicts']},ensure_ascii=False),flush=True)

def 防护文本(health,key):return health+'。'+('气体环境、压力和低温接触需要分开识别。' if key=='gas' else '皮肤、眼接触与蒸气、粉尘或雾滴需要分别识别。')
def 整改文本(equipment,causes):return '设施核对重点为'+equipment+'；原因候选包括'+causes+'。'
if __name__=='__main__':Expansion().run()
