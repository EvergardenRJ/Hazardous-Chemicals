import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BookOpen, Check, ChevronLeft, ChevronRight, Copy, FileText, History, LoaderCircle, Maximize2, Minimize2, PanelRightClose, PanelRightOpen, RefreshCw, Search, Settings2, Star, X } from 'lucide-react';
import { api, post } from './api';
import './wiki.css';
import WikiCatalog, { normalizeQuery, readLocalList, saveLocalList } from './WikiCatalog';
import WikiTools,{WikiPageExtras} from './WikiTools';

const STATE = { pending:'', approved:'已通过', modified:'修改后通过', rejected:'已拒绝', queued:'已排队', analyzing:'分析证据', generating:'生成章节', validating:'校验引用', ready_for_review:'已生成', failed:'生成失败', cancelled:'已取消' };
const SOURCE = { grounded:'文档证据', model_prior:'大模型知识库', external:'百科来源', mixed:'混合来源', unknown:'来源待核实' };
const FRESH = { fresh:'来源未检测到变化', stale:'来源已变化', needs_check:'新增来源待核实' };
const esc = encodeURIComponent;

function WikiMedia({media}) {
  const [failed,setFailed]=useState(false),[expanded,setExpanded]=useState(false);
  const dialogRef=useRef(null);
  useEffect(()=>{if(expanded)dialogRef.current?.showModal();else dialogRef.current?.close()},[expanded]);
  if(!media)return null;
  return <figure className="wiki-illustration">
    {failed?<a className="wiki-image-fallback" href={media.page_url} target="_blank" rel="noopener noreferrer">配图暂未载入，查看原图</a>:
      <button type="button" className="wiki-image-open" aria-label="放大配图" onClick={()=>setExpanded(true)}><img src={media.url} alt={media.description||media.caption} referrerPolicy="no-referrer" onError={()=>setFailed(true)}/><span><Maximize2 size={12}/>放大配图</span></button>}
    <figcaption>{media.caption}<details><summary>图片来源与许可</summary><a href={media.page_url} target="_blank" rel="noopener noreferrer">{media.source_name}</a><span>{media.artist}</span><a href={media.license_url||media.page_url} target="_blank" rel="noopener noreferrer">{media.license}</a></details></figcaption>
    <dialog className="wiki-image-dialog" ref={dialogRef} aria-label="Wiki 配图预览" onClose={()=>setExpanded(false)} onClick={e=>{if(e.target===e.currentTarget)setExpanded(false)}}><div><button className="wiki-image-close" onClick={()=>setExpanded(false)} aria-label="关闭配图预览"><X size={20}/></button>{expanded&&<img src={media.url} alt={media.description||media.caption} referrerPolicy="no-referrer"/>}<p>{media.caption}</p><a href={media.page_url} target="_blank" rel="noopener noreferrer">查看原图与许可</a></div></dialog>
  </figure>;
}
function publicBaikeLink(source){
 if(source.source_name==='百度百科'&&source.url?.startsWith('https://baike.baidu.com/item/'))return {...source,url:source.url.replace('https://baike.baidu.com/','https://bkso.baidu.com/')};
 return source;
}
function chapterSources(detail,section){
 const stored=detail.section_sources?.[section?.section];if(stored)return stored.map(publicBaikeLink);
 const all=detail.external_sources||[];
 return ['Wikipedia','百度百科'].map(name=>{const source=all.find(s=>s.source_name===name);return{source_name:name,title:detail.entity,role:'reading_link',url:publicBaikeLink(source||{}).url||(name==='Wikipedia'?'https://en.wikipedia.org/w/index.php?search='+encodeURIComponent(detail.chemical_profile?.english||detail.entity):'https://bkso.baidu.com/item/'+encodeURIComponent(detail.entity))}});
}
function ChapterSourceBar({detail,section}){
 const blocks=section.knowledge_blocks||[];
 const model=blocks.some(b=>['model_prior','mixed'].includes(b.knowledge_source));const local=blocks.some(b=>['grounded','mixed'].includes(b.knowledge_source));
 return <div className="wiki-chapter-sources" aria-label="本章来源"><span className="wiki-source-caption">来源</span>{model&&<span className="wiki-origin-tag">大模型知识库</span>}{local&&<span className="wiki-origin-tag">本地文档原文摘录</span>}<span className="wiki-source-divider"/>{chapterSources(detail,section).map(source=><a className="wiki-origin-link" key={source.source_name} href={source.url} target="_blank" rel="noopener noreferrer" title={source.role==='excerpt'?'本章有相关原文':'百科阅读入口'}>{source.source_name}<span aria-hidden="true">↗</span></a>)}</div>;
}
function ChapterMaterials({detail,section}){
 const materials=chapterSources(detail,section).filter(s=>s.role==='excerpt'&&s.excerpt);
 if(!materials.length)return null;
 return <div className="wiki-chapter-materials">{materials.map(source=><article className="wiki-material" key={source.source_name} aria-label={source.source_name+'相关内容'}><div className="wiki-material-heading"><strong>{source.source_name}</strong><span>{source.original_heading||'相关内容'}</span></div><blockquote lang={source.language||'zh'}>{source.excerpt}</blockquote><div className="wiki-material-meta"><a href={source.url} target="_blank" rel="noopener noreferrer">阅读完整词条</a>{source.license&&<a href={source.license_url} target="_blank" rel="noopener noreferrer">{source.license}</a>}</div></article>)}</div>;
}
function EncyclopediaSources({detail,section}) {
  const sources=chapterSources(detail,section);
  if(!sources.length)return null;
  return <section className="panel wiki-source-panel"><h2><BookOpen size={17}/>百科资料</h2>
    {sources.map(source=><div className="wiki-source-card" key={source.external_source_id||source.url}>
      <div className="wiki-source-line"><span className={'wiki-source-mark '+(source.source_name==='Wikipedia'?'wikipedia':'baidu')}>{source.source_name==='Wikipedia'?'W':'百'}</span><strong>{source.source_name}</strong></div>
      {source.scope_note&&<small>{source.scope_note}</small>}
      <div className="wiki-source-meta">{source.retrieved_at?'获取：'+source.retrieved_at.slice(0,10):'阅读入口'}{source.revision&&<span>词条版本 {source.revision}</span>}</div>
      <a href={source.url} target="_blank" rel="noopener noreferrer">阅读 {source.title}<ChevronRight size={13}/></a>
      {source.license&&<a className="wiki-license" href={source.license_url} target="_blank" rel="noopener noreferrer">{source.license}</a>}
    </div>)}
  </section>;
}
function AccidentReading({detail,entity}) {
  const readings=detail.accident_reading||[];
  if(!readings.length)return null;
  return <section className="panel wiki-accidents"><h2><FileText size={17}/>事故阅读推荐</h2>
    {readings.map((rec,i)=>{const href=rec.url||('/api/wiki/'+encodeURIComponent(entity)+'/evidence/'+encodeURIComponent(rec.evidence_id)+'/pdf?revision='+encodeURIComponent(detail.revision_id)+'#page='+Math.max(1,Number(rec.page)||1));
      return <div className="wiki-accident-card" key={rec.url||rec.evidence_id||i}>
        <small>{rec.source_name} · {rec.relation_type}</small><h3>{rec.title}</h3><p>{rec.reason}</p>
        {rec.excerpt&&<details><summary>阅读相关原文{rec.page?'（第 '+rec.page+' 页）':''}</summary><blockquote>{rec.excerpt}</blockquote></details>}
        {(rec.url||rec.pdf_available!==false)&&<a href={href} target="_blank" rel="noopener noreferrer">{rec.url?'阅读调查报告':'打开本地报告 PDF'}<ChevronRight size={13}/></a>}
      </div>;
    })}
  </section>;
}

export default function WikiWorkspace() {
  const [entries,setEntries]=useState([]),[jobs,setJobs]=useState([]),[schemaSections,setSchemaSections]=useState([]);
  const [detail,setDetail]=useState(null),[entity,setEntity]=useState(''),[input,setInput]=useState(()=>new URLSearchParams(location.search).get('chemical')||'');
  const [selected,setSelected]=useState(''),[view,setView]=useState('draft');
  const [edited,setEdited]=useState(''),[comment,setComment]=useState('');
  const [reviewer,setReviewer]=useState(()=>localStorage.getItem('wiki-reviewer')||'');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [pageType,setPageType]=useState('all');
  const [favorites,setFavorites]=useState(()=>readLocalList('wiki-favorites')),[recent,setRecent]=useState(()=>readLocalList('wiki-recent'));
  const [showTools,setShowTools]=useState(false),[readingFocus,setReadingFocus]=useState(false),[resourcesOpen,setResourcesOpen]=useState(true),[opening,setOpening]=useState(false);
  const readerRef=useRef(null),openController=useRef(null);
  const [filter,setFilter]=useState('all'),[evidenceFocus,setEvidenceFocus]=useState(null);
  const [comparison,setComparison]=useState(null),[history,setHistory]=useState(null),[findings,setFindings]=useState(null),[searchHits,setSearchHits]=useState(null);
  const requestSeq=useRef(0),detailRef=useRef(null),dirtyRef=useRef(false),initialOpen=useRef(false);
  const section=detail?.sections?.find(s=>s.section_id===selected);
  const dirty=!!section&&edited.trim()!==(section.candidate_content||section.content||'').trim();
  useEffect(()=>{dirtyRef.current=dirty;detailRef.current=detail;},[dirty,detail]);
  useEffect(()=>{localStorage.setItem('wiki-reviewer',reviewer);},[reviewer]);
  async function loadRegistry() {
    const d=await api('/api/wiki');setEntries(d.entries||[]);
  }
  async function loadJobs() { const d=await api('/api/wiki/jobs');setJobs(d.jobs||[]); }
  useEffect(()=>{
    let alive=true;
    async function poll() {
      try { const [r,j]=await Promise.all([api('/api/wiki'),api('/api/wiki/jobs')]);if(alive){setEntries(r.entries||[]);setJobs(j.jobs||[]);setSchemaSections(r.sections||[]);} }
      catch(e){if(alive)setError(e.message);}
    }
    poll();const id=setInterval(()=>{if(document.visibilityState==='visible')poll()},20000);
    return ()=>{alive=false;clearInterval(id);requestSeq.current++;openController.current?.abort();};
  },[]);
  useEffect(()=>{setEdited(section?.candidate_content||section?.content||'');setComment('');},[selected,detail?.revision_id]);
  function canLeave() { return !dirtyRef.current||window.confirm('本节有未保存修改，放弃修改并切换？'); }
  function writeLocation(name,chapter,newView='draft',revision=null,replace=false) {
    const url=new URL(window.location.href);url.hash='wiki';url.searchParams.set('wiki',name);
    if(chapter)url.searchParams.set('section',chapter);else url.searchParams.delete('section');
    if(newView!=='draft')url.searchParams.set('view',newView);else url.searchParams.delete('view');
    if(revision&&newView==='history')url.searchParams.set('revision',revision);else url.searchParams.delete('revision');
    if(url.href!==window.location.href)window.history[replace?'replaceState':'pushState']({},'',url);
  }
  function chooseSection(id) {
    if(!canLeave())return;
    const next=detail.sections.find(s=>s.section_id===id);if(!next)return;
    setSelected(id);setEvidenceFocus(null);writeLocation(entity,next.section,view,detail.revision_id);
    requestAnimationFrame(()=>readerRef.current?.scrollIntoView({block:'start',behavior:'auto'}));
  }
  async function open(name,newView='draft',revision=null,force=false,options={}) {
    if(!force&&!canLeave())return false;
    const seq=++requestSeq.current;openController.current?.abort();const controller=new AbortController();openController.current=controller;
    setOpening(true);setError('');setEvidenceFocus(null);setHistory(null);setComparison(null);
    try {
      const d=await api('/api/wiki/'+esc(name)+'?view='+newView+(revision?'&revision='+esc(revision):''),{signal:controller.signal});
      if(seq!==requestSeq.current)return false;
      const preferred=options.section||(detailRef.current?.entity===name?detailRef.current?.sections?.find(s=>s.section_id===selected)?.section:null);
      const chapter=d.sections?.find(s=>s.section===preferred||s.section_id===preferred)||d.sections?.[0];
      setDetail(d);setEntity(name);setView(d.view);setSelected(chapter?.section_id||'');
      setRecent(current=>{const next=[name,...current.filter(v=>v!==name)].slice(0,30);saveLocalList('wiki-recent',next);return next});
      if(options.location!==false)writeLocation(name,chapter?.section,d.view,d.revision_id,!!options.replace);
      return true;
    } catch(e){if(seq===requestSeq.current&&e.name!=='AbortError')setError(e.message);return false;}
    finally {if(seq===requestSeq.current)setOpening(false);}
  }
  useEffect(()=>{
    if(initialOpen.current||!entries.length)return;
    initialOpen.current=true;
    const params=new URLSearchParams(window.location.search),wanted=params.get('wiki')||localStorage.getItem('wiki-last-entity')||'氢氟酸';
    const entry=entries.find(e=>e.entity===wanted)||entries[0];
    open(entry.entity,params.get('view')||(entry.published_revision?'published':'draft'),params.get('revision'),false,{section:params.get('section'),replace:true});
  },[entries]);
  useEffect(()=>{
    function navigateToLocation() {
      if(window.location.hash!=='#wiki')return;
      const params=new URLSearchParams(window.location.search),name=params.get('wiki');if(!name)return;
      if(dirtyRef.current&&!canLeave()){const d=detailRef.current;writeLocation(d.entity,d.sections.find(s=>s.section_id===selected)?.section,d.view,d.revision_id,true);return;}
      open(name,params.get('view')||'draft',params.get('revision'),true,{section:params.get('section'),location:false});
    }
    window.addEventListener('popstate',navigateToLocation);window.addEventListener('wiki:navigate',navigateToLocation);
    return()=>{window.removeEventListener('popstate',navigateToLocation);window.removeEventListener('wiki:navigate',navigateToLocation)};
  },[selected]);
  useEffect(()=>{if(entity){try{localStorage.setItem('wiki-last-entity',entity)}catch{}}},[entity]);
  useEffect(()=>{
    function storage(e){if(e.key==='wiki-favorites')setFavorites(readLocalList('wiki-favorites'));if(e.key==='wiki-recent')setRecent(readLocalList('wiki-recent'))}
    window.addEventListener('storage',storage);return()=>window.removeEventListener('storage',storage);
  },[]);
  function toggleFavorite() {
    setFavorites(current=>{const next=current.includes(entity)?current.filter(v=>v!==entity):[entity,...current].slice(0,200);saveLocalList('wiki-favorites',next);return next});
  }
  async function copyChapterLink() {
    writeLocation(entity,section?.section,view,detail.revision_id,true);
    try {await navigator.clipboard.writeText(window.location.href);setMessage('本章节链接已复制。')}catch{setMessage('请从浏览器地址栏复制本章节链接。')}
  }
  async function action(fn) {
    setBusy(true);setError('');setMessage('');
    try { await fn(); } catch(e){setError(e.message);}
    finally {setBusy(false);}
  }
  async function generate(refresh=false,full=false) {
    const name=refresh?entity:input.trim();if(!name)return;
    await action(async()=>{
      const body=refresh?{sections:full?schemaSections:[section.section],mode:full?'replace_page':'refresh',base_revision:detail.revision_id}:{};
      const d=await post('/api/wiki/'+esc(name)+(refresh?'/refresh':'/generate'),body);
      await loadJobs();setMessage(d.job.block_reason||'任务已保存，完成后可打开草稿审核。');
    });
  }
  async function review(status) {
    if(!section)return;
    await action(async()=>{
      await post('/api/wiki/'+esc(entity)+'/review',{
        section_id:section.section_id,section:section.section,expected_revision:detail.revision_id,
        content_hash:section.content_hash,review_status:status,reviewed_content:status==='modified'?edited:section.content,
        review_comment:comment,error_type:status==='approved'?'':'content_review',reviewer
      });
      const sectionId=section.section_id;
      await open(entity,'draft',null,true);setSelected(sectionId);await loadRegistry();
      setMessage(status==='modified'?'修改已保存到新草稿版本，并记录审核。':'审核已记录。');setComment('');
    });
  }
  async function publish() {
    await action(async()=>{
      await post('/api/wiki/'+esc(entity)+'/publish',{expected_revision:detail.revision_id,reviewer});
      await loadRegistry();await open(entity,'published',null,true);setMessage('当前版本已发布，可在历史中回查。');
    });
  }
  async function showHistory() {
    await action(async()=>{setHistory(await api('/api/wiki/'+esc(entity)+'/history'));});
  }
  async function jobAction(job,act) {
    await action(async()=>{await post('/api/wiki/jobs/'+esc(job.job_id)+'/'+act,{});await loadJobs();});
  }
  const activeJobs=jobs.filter(j=>['queued','analyzing','generating','validating'].includes(j.state)||showTools&&['failed','cancelled'].includes(j.state));
  const chapterIndex=detail?.sections?.findIndex(s=>s.section_id===selected)??0;
  const record=detail?.reviews?.[section?.section]||{};
  const currentDraft=detail?.revision_id===detail?.entry?.draft_revision;
  function markdown(text) {
    return (text||'').replace(/本页由\s*Codex\s*当前会话依据模型背景知识编写（[^）]*），具体模型版本未由环境提供。\s*本地原文摘录单独绑定证据；每个摘录仅说明原文所述内容，其他段落保留模型补充来源。/g,'').replace(/（仅支持本片段，登记信息待核实）/g,'').replace(/^\*\*(?:来源：[^*\n]+|本地文档原文摘录(?:（[^）]*）)?|本地调查报告摘录(?:（[^）]*）)?)\*\*\s*$/gm,'').replace(/\[\[([^\]\n]+)\]\]/g,(_,name)=>'['+name+'](#wiki-page-'+encodeURIComponent(name)+')').replaceAll('来源：模型背景知识（Codex 当前会话生成，待核实）','来源：大模型知识库').replace(/\[Wiki证据(\d+)\]/g,(whole,n)=>{
      const e=detail?.evidence?.[Number(n)-1];
      return e?'['+whole+'](#wiki-evidence-'+e.evidence_id+')':whole;
    });
  }
  const renderer={a:({href,children})=>{
    if(href?.startsWith('#wiki-page-'))return <button className="wiki-inline-link" onClick={()=>open(decodeURIComponent(href.slice(11)))}>{children}</button>;
    if(href?.startsWith('#wiki-evidence-'))return <button className="wiki-citation" onClick={()=>setEvidenceFocus(href.slice(15))}>{children}</button>;
    return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  }};
  const evidence=detail?.evidence||[];
  const focused=evidence.find(e=>e.evidence_id===evidenceFocus);
  const shownEvidence=focused?[focused]:evidence.filter(e=>!section?.evidence_refs?.length||section.evidence_refs.includes(e.evidence_id));
  return <section className={'workspace-scroll wiki-v2 wiki-refresh '+(readingFocus?'wiki-focus ':'')+(!resourcesOpen?'wiki-resources-hidden':'')}>
    <header className="workspace-heading"><div><h1>知识 Wiki <span className="wiki-total">{entries.length.toLocaleString('zh-CN')} 项</span></h1><p>查找化学品、设备与安全专题，沿来源继续阅读。</p></div>
      <div className="wiki-workspace-actions"><button className="button button--quiet" aria-expanded={showTools} onClick={()=>setShowTools(v=>!v)}><Settings2 size={16}/>{showTools?'收起维护工具':'维护与扩展'}</button><button className="button button--quiet" onClick={()=>action(async()=>{const d=await api('/api/wiki/lint');setFindings(d.findings);})}><Search size={16}/>维护检查</button></div></header>
    {showTools&&<WikiTools onOpen={name=>open(name)} onChanged={loadRegistry}/>}
    {opening&&detail&&<div className="wiki-loading" role="status"><LoaderCircle size={15} className="spin"/>正在打开条目…</div>}
    {error&&<div className="notice notice--error" role="alert">{error}</div>}{message&&<div className="notice" role="status">{message}</div>}
    {findings&&<details className="panel wiki-maintenance" open><summary>待维护项（{findings.length}）</summary><button className="wiki-close" onClick={()=>setFindings(null)} aria-label="关闭检查"><X size={16}/></button>
      {findings.slice(0,80).map((f,i)=><button key={i} onClick={()=>open(f.entity)}>{f.entity}：{f.message}</button>)}</details>}
    {searchHits&&<div className="panel wiki-maintenance"><strong>已发布检索结果（{searchHits.length}）</strong><button className="wiki-close" onClick={()=>setSearchHits(null)} aria-label="关闭检索"><X size={16}/></button>
      {!searchHits.length&&<p>暂无匹配的已发布知识。草稿不会作为已审核内容参与此检索。</p>}
      {searchHits.map(h=><button key={h.entity+h.section} onClick={()=>open(h.entity,'published')}>{h.entity} / {h.section}</button>)}</div>}
    {activeJobs.length>0&&<details className="panel wiki-jobs"><summary>生成任务（{activeJobs.length}）</summary>{activeJobs.slice(0,5).map(j=><div className="wiki-job" key={j.job_id}>
      <div><strong>{j.entity}</strong><span>{STATE[j.state]||j.state}，{j.progress.completed}/{j.progress.total} 节</span>
      <small>{j.block_reason||j.error||'已保存进度，关闭页面不会取消任务。'}</small></div>
      {['failed','cancelled'].includes(j.state)?<button className="button button--quiet" onClick={()=>jobAction(j,'retry')} disabled={busy}>恢复任务</button>:<button className="button button--quiet" onClick={()=>jobAction(j,'cancel')} disabled={busy}>取消</button>}
    </div>)}</details>}
    {jobs.some(j=>j.state==='ready_for_review')&&<div className="wiki-ready">{jobs.filter(j=>j.state==='ready_for_review').slice(0,3).map(j=><button key={j.job_id} onClick={()=>open(j.entity)}>打开新草稿：{j.entity}</button>)}</div>}
    <div className="wiki-desk">
      <WikiCatalog entries={entries} entity={entity} input={input} setInput={setInput} pageType={pageType} setPageType={setPageType} filter={filter} setFilter={setFilter} favorites={favorites} recent={recent} onOpen={open} onGenerate={generate} busy={busy||opening} onSearch={()=>action(async()=>{const d=await api('/api/wiki/search?q='+esc(input));setSearchHits(d.results)})}/>
      {detail?<main className="wiki-document" aria-busy={opening}>
        <div className="panel wiki-page-head"><div><h2>{entity}<span className="wiki-formula">{detail.chemical_profile?.formula||""}</span></h2>{detail.chemical_profile?.english&&<p className="wiki-english">{detail.chemical_profile.english}</p>}<div className="wiki-state"><span>{detail.is_published?'已发布版本':view==='history'?'历史版本':'未发布草稿'}</span><span>{FRESH[detail.freshness||detail.entry.freshness]||'来源待核实'}</span><span>{detail.sections.length} 节 / {evidence.length} 条证据</span></div></div>
          <div className="wiki-head-actions"><button className={'button button--quiet wiki-bookmark '+(favorites.includes(entity)?'is-saved':'')} aria-pressed={favorites.includes(entity)} onClick={toggleFavorite}><Star size={15}/>{favorites.includes(entity)?'已收藏':'收藏'}</button><button className="button button--quiet" disabled={view==='draft'&&!detail.entry.published_revision} title={view==='draft'&&!detail.entry.published_revision?'此条目暂无发布版':undefined} onClick={()=>open(entity,view==='draft'?'published':'draft')}>{view==='draft'?'阅读发布版':'审核当前草稿'}</button>
          <button className="button button--quiet" onClick={showHistory}><History size={16}/>版本历史</button>
          <a className="button button--quiet" href={'/api/wiki/'+esc(entity)+'/export?view='+view+'&revision='+esc(detail.revision_id)}>导出正文</a></div></div>
        {!detail.validation.ok&&<div className="notice notice--error"><strong>此草稿尚有校验问题，不可直接发布。</strong><details><summary>查看 {detail.validation.errors.length} 项问题</summary>{detail.validation.errors.map((e,i)=><p key={i}>{e}</p>)}</details></div>}
        <details className="wiki-crossrefs"><summary>相关页面与来源操作</summary><WikiPageExtras detail={detail} onOpen={name=>open(name)} onChanged={loadRegistry}/></details>
        <div className="wiki-page-overview">
          <div><div className="wiki-source-tags">
            {detail.sections.some(s=>s.knowledge_blocks?.some(b=>b.knowledge_source==='model_prior'))&&<span>大模型知识库</span>}
            {(detail.external_sources||[]).map(source=><a key={source.external_source_id||source.url} href={publicBaikeLink(source).url} target="_blank" rel="noopener noreferrer">{source.source_name}</a>)}
            {!!detail.evidence.length&&<span>本地文档</span>}
          </div><p>{detail.product_scope||detail.chemical_profile?.scope||'逐节阅读资料，查看原文与审核记录。'}</p>
          
          </div><WikiMedia key={detail.illustration?.url||entity} media={detail.illustration}/>
        </div>
        <div className="wiki-reader-toolbar"><label className="wiki-chapter-select"><BookOpen size={15}/><select value={selected} onChange={e=>chooseSection(e.target.value)} aria-label="跳转 Wiki 章节">{detail.sections.map((s,i)=><option key={s.section_id} value={s.section_id}>{i+1}. {s.section}</option>)}</select></label><span className="wiki-chapter-position">{chapterIndex+1} / {detail.sections.length} 节</span><div className="wiki-reader-actions"><button className="button button--quiet" onClick={copyChapterLink} title="复制本章节链接"><Copy size={14}/><span>复制链接</span></button><button className="button button--quiet" aria-pressed={!resourcesOpen} onClick={()=>setResourcesOpen(v=>!v)} title={resourcesOpen?'收起参考资料':'展开参考资料'}>{resourcesOpen?<PanelRightClose size={15}/>:<PanelRightOpen size={15}/>}<span>{resourcesOpen?'收起资料':'展开资料'}</span></button><button className="button button--quiet" aria-pressed={readingFocus} onClick={()=>setReadingFocus(v=>!v)}>{readingFocus?<Minimize2 size={15}/>:<Maximize2 size={15}/>}<span>{readingFocus?'退出专注':'专注阅读'}</span></button></div></div>
        <nav className="wiki-section-nav" aria-label="Wiki 章节">{detail.sections.map(s=><button className={selected===s.section_id?'active':''} aria-current={selected===s.section_id?'true':undefined} key={s.section_id} onClick={()=>chooseSection(s.section_id)}>{s.section}</button>)}</nav>
        {section&&<div className="wiki-reading-layout">
          <article className="panel wiki-reading" ref={readerRef} id="wiki-reader" tabIndex={-1}><div className="wiki-reading-title"><h2>{section.section}</h2></div><ChapterSourceBar detail={detail} section={section}/>
            <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]} components={renderer}>{markdown(section.content)}</ReactMarkdown></div><ChapterMaterials detail={detail} section={section}/>
            <nav className="wiki-chapter-pager" aria-label="相邻章节"><button disabled={chapterIndex<=0} onClick={()=>chooseSection(detail.sections[chapterIndex-1].section_id)}><ChevronLeft size={16}/><span><small>上一节</small>{detail.sections[chapterIndex-1]?.section}</span></button><button disabled={chapterIndex>=detail.sections.length-1} onClick={()=>chooseSection(detail.sections[chapterIndex+1].section_id)}><span><small>下一节</small>{detail.sections[chapterIndex+1]?.section}</span><ChevronRight size={16}/></button></nav>
            {currentDraft&&view==='draft'&&<details className="wiki-review-form"><summary>审核此章节</summary><h3>核对正文后记录审核</h3><label>候选正文<textarea value={edited} onChange={e=>setEdited(e.target.value)} aria-label="候选正文"/></label>
              <div className="form-grid"><label>审核人<input value={reviewer} onChange={e=>setReviewer(e.target.value)} placeholder="姓名或工号"/></label><label>审核意见<input value={comment} onChange={e=>setComment(e.target.value)} placeholder="修改或拒绝时必填"/></label></div>
              {record.reviewer&&<p className="wiki-review-note">上次记录：{record.reviewer}，{record.reviewed_at}，{STATE[record.review_status]}</p>}
              <div className="compose-actions"><button className="button button--primary" disabled={busy||!reviewer.trim()||dirty} onClick={()=>review('approved')}><Check size={16}/>通过</button>
              <button className="button button--quiet" disabled={busy||!reviewer.trim()||!comment.trim()||!edited.trim()} onClick={()=>review('modified')}>修改并通过</button>
              <button className="button button--danger" disabled={busy||!reviewer.trim()||!comment.trim()} onClick={()=>review('rejected')}>拒绝</button>
              <button className="button button--quiet" disabled={busy||dirty||!schemaSections.includes(section.section)} onClick={()=>generate(true)}><RefreshCw size={16}/>重新生成本节</button></div>
              {dirty&&<small>正文有修改，请使用“修改并通过”保存新版本。</small>}
            </details>}
          </article>
          <div className="wiki-resources" hidden={readingFocus||!resourcesOpen}><EncyclopediaSources detail={detail} section={section}/><AccidentReading detail={detail} entity={entity}/>
          <aside className="panel wiki-evidence"><h2><FileText size={17}/>本节证据 {focused&&<button onClick={()=>setEvidenceFocus(null)}>查看全部</button>}</h2>
            {!shownEvidence.length&&<p>本节暂无可核查的文档证据，需补充资料。</p>}
            {shownEvidence.map(e=>{const m=e.metadata||{};return <details open={!!focused} key={e.evidence_id}><summary><strong>[Wiki证据{evidence.indexOf(e)+1}] {m.title||m.code||'来源标题缺失'}</strong></summary>
              <p>编号 {m.code||'未标注'}<br/>页码 {m.page_start||'未知'}—{m.page_end||m.page_start||'未知'}<br/>片段 {m.chunk_id||'未知'}<br/>状态 {m.status||'未知'} / 版本 {m.source_revision||m.version||'未标注'}</p>
              <a className="button button--quiet" target="_blank" rel="noopener noreferrer" href={'/api/wiki/'+esc(entity)+'/evidence/'+esc(e.evidence_id)+'/pdf?revision='+esc(detail.revision_id)+'#page='+Math.max(1,Number(m.page_start)||1)}>打开原 PDF 页</a><blockquote>{m.text||'原文缺失'}</blockquote><small>{e.evidence_id}</small></details>;})}
          </aside></div>
        </div>}
        {currentDraft&&view==='draft'&&<div className="panel wiki-publish"><div><h3>发布当前版本</h3><p>所有章节需在当前内容版本完成审核。高风险内容还须有文档证据，发布前由服务端再次校验。</p></div><div><button className="button button--quiet" disabled={busy||dirty||!schemaSections.length} onClick={()=>generate(true,true)}>生成完整新草稿</button>
        <button className="button button--primary" disabled={busy||!reviewer.trim()||dirty} onClick={publish}>发布审核版</button></div></div>}
        {history&&<div className="panel wiki-history"><h2>版本历史</h2><button className="wiki-close" onClick={()=>setHistory(null)} aria-label="关闭历史"><X size={16}/></button>
          {history.revisions.map(r=><div key={r.revision_id}><span>{r.created_at} / {r.reason}<small>{r.revision_id}</small></span><button className="button button--quiet" onClick={()=>open(entity,'history',r.revision_id)}>查看此版</button>
          <button className="button button--quiet" onClick={()=>action(async()=>setComparison(await api('/api/wiki/'+esc(entity)+'/compare?before='+esc(r.revision_id)+'&after='+esc(detail.entry.draft_revision))))}>与当前草稿比较</button>
          {history.events.some(e=>e.action==='publish'&&e.revision_id===r.revision_id)&&<button className="button button--quiet" disabled={busy||!reviewer.trim()} onClick={()=>action(async()=>{await post('/api/wiki/'+esc(entity)+'/rollback',{revision_id:r.revision_id,reviewer});await open(entity,'published',null,true);await loadRegistry();setMessage('已回滚发布指针，其他版本保留。');})}>回滚发布至此版</button>}</div>)}</div>}
        {comparison&&<div className="panel wiki-history"><h2>版本差异</h2><button className="wiki-close" onClick={()=>setComparison(null)} aria-label="关闭差异"><X size={16}/></button><p>变化章节：{comparison.changed_sections.join('、')||'无正文变化'}</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{comparison.diff||'正文一致'}</pre></div>}
        {detail.related?.length>0&&<div className="panel wiki-related"><h3>相关条目</h3><p>以下关联用于导航，不代表两条知识相互证明。</p>{detail.related.map(r=><button key={r.entity} onClick={()=>open(r.entity)}><BookOpen size={15}/>{r.entity}<small>{r.reason}</small></button>)}</div>}
      </main>:<div className="panel wiki-empty"><BookOpen size={34}/><h2>选择一篇 Wiki</h2><p>{opening?'正在载入条目正文与来源…':'从目录选择条目，或按 / 搜索名称。'}</p></div>}
    </div>
  </section>;
}
