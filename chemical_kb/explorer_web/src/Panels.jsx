import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Tab, Tabs } from '@mui/material';
import { useUI, useDirtyDraft, EvidenceAdapter } from './components/WorkspaceUI';
import { relationLabels } from './theme/tokens';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowRight, Check, Download, FileText, Filter,
  GitMerge, LoaderCircle, Search, ShieldCheck, X
} from 'lucide-react';
import { api, post, sourceLabel, today } from './api';
import {PageQuote} from './components/PageQuote';
import './wiki-tools.css';

export function WorkspaceHeading({ kicker, title, description, action }) {
  return <div className="workspace-heading">
    <div><div className="eyebrow">{kicker}</div><h1>{title}</h1><PageQuote/><p className="workspace-heading-note">{description}</p></div>
    {action && <div className="heading-action">{action}</div>}
  </div>;
}

function Notice({ children, tone = 'info' }) {
  return <div className={`notice notice--${tone}`}>{children}</div>;
}

function Empty({ title, detail, icon: Icon = FileText }) {
  return <div className="empty-state"><Icon size={26}/><strong>{title}</strong><span>{detail}</span></div>;
}

function DateFilter({ value, onChange }) {
  return <label className="date-control"><span>生效时点</span><input type="date" value={value} onChange={e => onChange(e.target.value)}/></label>;
}

export function AskWorkspace({ asOf, setAsOf, seedQuestion }) {
  const ui = useUI();
  const [question, setQuestion] = useState(seedQuestion || '');
  const [answer, setAnswer] = useState(null);
  const [sessions,setSessions]=useState([]),[session,setSession]=useState(()=>new URLSearchParams(location.search).get('conversation_id')||''),[history,setHistory]=useState([]),[drafts,setDrafts]=useState(false),[mode,setMode]=useState('wiki'),[archiveTitle,setArchiveTitle]=useState(''),[saved,setSaved]=useState('');
  const loadSessions=()=>api('/api/wiki/platform/conversations').then(d=>setSessions(d.conversations||[]));
  useEffect(()=>{loadSessions().catch(()=>{});},[]);
  useEffect(()=>{if(session)chooseSession(session)},[]);
  async function chooseSession(id){setSession(id);setSaved('');const u=new URL(location.href);id?u.searchParams.set('conversation_id',id):u.searchParams.delete('conversation_id');historyReplace(u);if(!id){setHistory([]);setAnswer(null);return;}try{const d=await api('/api/wiki/platform/conversations/'+id);setHistory(d.answers||[]);setAnswer(d.answers?.at(-1)||null);setQuestion(d.answers?.at(-1)?.question||'');}catch(e){setError(e.message);}}
  function historyReplace(u){window.history.replaceState({},'',u);window.dispatchEvent(new Event('workspace:navigate'));}
  async function renameSession(){const title=await ui.request({kind:'text',title:'重命名对话',label:'对话名称',value:sessions.find(c=>c.id===session)?.title||'',submitLabel:'保存名称'});if(!title)return;try{await post('/api/wiki/platform/conversations/'+session,{action:'rename',title});await loadSessions();ui.notify('对话名称已保存')}catch(e){setError(e.message)}}
  async function deleteSession(){if(!await ui.request({title:'删除此对话？',description:'此对话及其回答记录将被删除；已经归档的 Wiki 页面会保留。',danger:true,submitLabel:'删除对话'}))return;try{await post('/api/wiki/platform/conversations/'+session,{action:'delete'});await chooseSession('');await loadSessions();ui.notify('对话已删除')}catch(e){setError(e.message)}}
  async function archiveAnswer(){setBusy(true);try{const d=await post('/api/wiki/platform/answers/'+answer.answer_id+'/archive',{title:archiveTitle||answer.question});setSaved(d.entity);}catch(e){setError(e.message);}finally{setBusy(false);}}
  const wikiHref=name=>'/?wiki='+encodeURIComponent(name)+'#wiki';
  const [quick, setQuick] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (seedQuestion) setQuestion(seedQuestion); }, [seedQuestion]);
  const prompts = ['液氯泄漏后应如何应急处置？', '储存甲醇有哪些安全要求？', '压力容器事故有哪些常见原因？'];
  async function ask() {
    if (!question.trim()) return;
    setBusy(true); setError('');
    try { const d=await post('/api/ask',{question:question.trim(),as_of:asOf,conversation_id:session||undefined,include_drafts:drafts,mode});setAnswer(d);setSession(d.conversation_id);const u=new URL(location.href);u.searchParams.set('conversation_id',d.conversation_id);historyReplace(u);setHistory(h=>[...h,d]);setArchiveTitle((d.question||question).slice(0,70));setSaved('');loadSessions().catch(()=>ui.notify('答案已生成，对话列表暂未刷新','warning')); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function searchEvidence() {
    if (!question.trim()) return;
    setBusy(true); setError('');
    try { setQuick(await api('/api/search?q=' + encodeURIComponent(question.trim()))); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <section className="workspace-scroll">
    <WorkspaceHeading kicker="ANALYZE / EVIDENCE" title="智能检索"
      description="查询 Wiki 与原文资料，保留对话并将有价值的回答归档为 Wiki。"
      action={<DateFilter value={asOf} onChange={setAsOf}/>}/>
    <div className="ask-layout">
      <div className="panel ask-compose">
        <div className="panel-header"><div><div className="eyebrow">QUERY CONSOLE</div><h2>向知识库提问</h2></div><span className="live-dot">WIKI QUERY</span></div>
        <div className="ask-session-actions"><select aria-label="对话历史" value={session} onChange={e=>chooseSession(e.target.value)}><option value="">新对话</option>{sessions.map(c=><option value={c.id} key={c.id}>{c.title}{c.updated_at?' · '+c.updated_at.slice(0,10):''}</option>)}</select><button className="button button--quiet" onClick={()=>chooseSession('')}>新建对话</button>{session&&<><button className="button button--quiet" disabled={busy} onClick={renameSession}>重命名</button><button className="button button--quiet" disabled={busy} onClick={deleteSession}>删除对话</button></>}</div>
        {history.length>1&&<details><summary>本次对话 {history.length} 条回答</summary><div className="ask-history-list">{history.map(a=><button key={a.answer_id} onClick={()=>{setAnswer(a);setQuestion(a.question)}}>{a.question}</button>)}</div></details>}
        <div className="ask-mode"><label><input type="checkbox" checked={drafts} onChange={e=>setDrafts(e.target.checked)}/>参考草稿 Wiki</label><label>检索范围 <select aria-label="问答资料范围" value={mode} onChange={e=>setMode(e.target.value)}><option value="wiki">已发布 Wiki 与原文</option><option value="sources">只读原文</option></select></label></div>
        <textarea className="question-box" value={question} onChange={e => setQuestion(e.target.value)}
          placeholder="输入事故、化学品、标准条款或应急处置问题…" aria-label="知识库问题"/>
        <div className="compose-actions">
          <button className="button button--primary" onClick={ask} disabled={busy || !question.trim()}>
            {busy ? <LoaderCircle className="spin" size={16}/> : <ArrowRight size={16}/>}生成证据答案
          </button>
          <button className="button button--quiet" onClick={searchEvidence} disabled={busy || !question.trim()}>
            <Search size={16}/>快速查找片段
          </button>
        </div>
        <div className="suggestion-row"><span>试试：</span>{prompts.map(p =>
          <button key={p} onClick={() => setQuestion(p)}>{p}</button>)}</div>
      </div>
      <aside className="insight-aside">
        <div className="panel insight-card"><div className="eyebrow">RETRIEVAL PIPELINE</div>
          <div className="pipeline-step"><span>01</span><div><strong>资料召回</strong><small>Wiki · 原文；外部向量按配置启用</small></div></div>
          <div className="pipeline-step"><span>02</span><div><strong>组织资料</strong><small>正文链接 · 引用去重</small></div></div>
          <div className="pipeline-step"><span>03</span><div><strong>证据验证</strong><small>来源 · 时点 · 发布状态</small></div></div>
        </div>
      </aside>
    </div>
    {busy&&<Alert severity="info">正在读取并组织资料，结果返回后会显示。关闭页面不代表取消服务器处理。</Alert>}
    {drafts&&<Alert severity="warning" sx={{my:2}}>当前范围包含未审核草稿，回答仍需对照原文核实。</Alert>}
    {error && <Notice tone="error">{error}　<button className="button button--quiet" onClick={searchEvidence} disabled={busy}>仅查原文片段</button></Notice>}
    {answer && <div className="results-layout">
      <section className="panel answer-panel"><div className="panel-header"><div><div className="eyebrow">GROUNDED RESPONSE</div><h2>回答</h2></div><span className="count-badge">{answer.evidence?.length || 0} 条证据</span></div>
        <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{(answer.answer || '没有足够可靠的证据生成回答。').replace(/\[\[([^\]\n]+)\]\]/g,(_,name)=>'['+name+']('+wikiHref(name)+')')}</ReactMarkdown></div>
        <p className="subtle">{answer.resource_note}</p>{answer.wiki_refs?.length>0&&<p>参考 Wiki：{answer.wiki_refs.map((r,i)=><a className="wiki-inline-link" key={i} href={wikiHref(r.entity)}>{r.entity} / {r.section}</a>)}</p>}
        <div className="ask-archive"><input aria-label="归档 Wiki 标题" value={archiveTitle} onChange={e=>setArchiveTitle(e.target.value)} placeholder="专题标题"/><button className="button button--primary" disabled={busy||!answer.answer_id} onClick={archiveAnswer}>保存为 Wiki 草稿</button><button className="button button--quiet" disabled={busy} onClick={ask}>重新生成</button>{saved&&<a className="wiki-inline-link" href={wikiHref(saved)}>打开归档：{saved}</a>}</div>
      </section>
      <section className="evidence-stack"><div className="section-label">证据链 / SOURCES</div>
        {(answer.evidence || []).map((item, index) => <article className="panel evidence-item" key={index}>
          <div className="evidence-top"><span className="evidence-index">{String(index+1).padStart(2,'0')}</span>
            <span className="status-pill status-pill--blue">{(item.routes || ['vector']).join(' + ')}</span></div>
          <h3>{item.metadata?.title || '未命名来源'}</h3><div className="subtle">{sourceLabel(item.metadata || {})}</div>
          <p>{item.metadata?.text || ''}</p>
          <Button size="small" onClick={()=>ui.openEvidence(EvidenceAdapter(item))}>核对原文与来源</Button><details className="evidence-foot"><summary>检索技术详情</summary>{item.rrf_score!=null&&<>RRF {Number(item.rrf_score).toFixed(4)}</>}{item.rerank_score!=null&&<> · Rerank {Number(item.rerank_score).toFixed(2)}</>}</details>
        </article>)}
      </section>
    </div>}
    {quick && <section className="panel quick-results"><div className="panel-header"><div><div className="eyebrow">INSTANT EVIDENCE</div><h2>片段预览</h2></div><span className="count-badge">{quick.evidence?.length || 0} 条</span></div>
      {(quick.evidence || []).map((item, index) => <div className="quick-row" key={index}><strong>{item.metadata?.title || '片段'}</strong><span>{sourceLabel(item.metadata || {})}</span><p>{item.metadata?.text?.slice(0, 240)}</p></div>)}
    </section>}
  </section>;
}

export function ReviewWorkspace({ onGraphRefresh, summary, embedded = false }) {
  const ui=useUI();
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(()=>new URLSearchParams(location.search).get('assertion_id')||'');
  const [query, setQuery] = useState(()=>new URLSearchParams(location.search).get('chemical')||'');
  const [filter, setFilter] = useState('all');
  const [decision, setDecision] = useState('modified');
  const [reviewer, setReviewer] = useState(()=>{try{return localStorage.getItem('ui-reviewer')||''}catch{return ''}});
  const [comment, setComment] = useState('');
  const [errorType, setErrorType] = useState('');
  const [corrected, setCorrected] = useState({});
  const [source, setSource] = useState(null);
  const [history, setHistory] = useState(null);
  const [schema, setSchema] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [conflict,setConflict]=useState(false),[formId,setFormId]=useState(''),[sourceError,setSourceError]=useState('');
  const load = () => api('/api/reviews').then(d => setItems(d.items || [])).catch(e => setError(e.message));
  useEffect(() => { load(); api('/api/schema').then(setSchema).catch(() => {}); }, []);
  const visible = items.filter(item => {
    if(filter==='active'&&!['approved','modified'].includes(item.status))return false;
    if(filter!=='all'&&filter!=='active'&&item.status!==filter)return false;
    const a=item.assertion;return !query.trim()||[item.assertion_id,a.subject_label,a.predicate,a.object_label,a.source_doc_id,a.source_text_quote].some(x=>String(x||'').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  });
  const current = visible.find(item => item.assertion_id === selected) || visible[0];
  const dirty=!!current&&formId===current.assertion_id&&(JSON.stringify(corrected)!==JSON.stringify(current.assertion)||!!comment||!!errorType||decision!==(current.status==='pending'?'approved':'modified'));
  const draft=useDirtyDraft({id:'review:'+current?.assertion_id,dirty,baseVersion:current?.review_id||'initial',content:{corrected,comment,errorType,decision},title:'这条断言有未保存的审核修改',onRestore:v=>{setCorrected(v.corrected);setComment(v.comment);setErrorType(v.errorType);setDecision(v.decision)},onDiscard:()=>{setCorrected({...current?.assertion});setComment('');setErrorType('');setDecision(current?.status==='pending'?'approved':'modified')}});
  useEffect(() => {
    if (!current) return;
    setSelected(current.assertion_id);
    setCorrected({ ...current.assertion });
    setDecision(current.status === 'pending' ? 'approved' : 'modified');
    setComment(''); setErrorType('');setMessage('');setConflict(false);setFormId(current.assertion_id);setSource(null);setHistory(null);setSourceError('');
    const id = encodeURIComponent(current.assertion_id);
    const controller=new AbortController();
    api('/api/reviews/' + id + '/source',{signal:controller.signal}).then(d=>{if(!controller.signal.aborted)setSource(d)}).catch(e=>{if(e.name!=='AbortError')setSourceError('来源暂未读取：'+e.message)});
    api('/api/reviews/' + id + '/history',{signal:controller.signal}).then(d=>{if(!controller.signal.aborted)setHistory(d)}).catch(()=>{});
    return()=>controller.abort();
  }, [current?.assertion_id, current?.review_id]);
  const counts = {
    all: items.length,
    active: items.filter(x => ['approved','modified'].includes(x.status)).length,
    pending: items.filter(x => x.status === 'pending').length,
    rejected: items.filter(x => x.status === 'rejected').length
  };
  const update = (key, value) => setCorrected(a => ({...a, [key]: value}));
  const textField = (label, key) => <label key={key}>{label}<input value={corrected[key] ?? ''}
    onChange={e => update(key, e.target.value)}/></label>;
  const relationTypes = schema?.relation_types?.map(r => r.id) || [];
  const entityTypes = schema?.entity_types?.map(e => e.id) || [];
  const attrs = schema?.entity_types?.find(e => e.id === corrected.subject_type)?.attributes?.map(a => a.name) || [];
  async function submit() {
    if (!current || busy) return;
    if(!reviewer.trim()){setError('请填写审核人姓名或工号。');return;}
    setBusy(true); setError(''); setMessage('');
    try {
      await post('/api/reviews/' + encodeURIComponent(current.assertion_id), {
        decision, reviewer: reviewer.trim(), comment: comment.trim(),
        error_type: errorType.trim(), expected_review_id: current.review_id,
        corrected: decision === 'modified' ? corrected : null
      });
      setMessage('审核版本已保存；图谱与导出会使用最新版本。');
      draft.clear();try{localStorage.setItem('ui-reviewer',reviewer.trim())}catch{}setComment('');setErrorType('');
      await load(); onGraphRefresh?.();
    } catch (e) { setError(e.status===409?'记录已被其他操作更新。你的修改仍然保留，请暂存并读取最新版本后重新核对。':e.message);setConflict(e.status===409); }
    finally { setBusy(false); }
  }
  const a = current?.assertion;
  const statusText = {approved:'已通过',modified:'已修订',pending:'待审核',rejected:'已撤销'};
  return <section className={embedded ? 'governance-pane' : 'workspace-scroll'}>
    {!embedded && <WorkspaceHeading kicker="GOVERNANCE / RELATION CATALOG" title="断言审核"
      description={`当前仅 ${summary?.relation_source_docs ?? 0} / ${summary?.documents ?? 0} 份文档进入关系候选流程。这里列出已抽取的关系与属性，可沿来源片段核实并修订。`}/>}
    {embedded && <p className="governance-context">已进入关系候选流程的文档：{summary?.relation_source_docs ?? 0} / {summary?.documents ?? 0} 份。逐条核对原文后保存审核版本。</p>}
    <div className="review-summary">
      <div><strong>{counts.all}</strong><span>全部断言</span></div>
      <div><strong>{counts.active}</strong><span>有效断言</span></div>
      <div><strong>{counts.pending}</strong><span>待审核</span></div>
      <div><strong>{counts.rejected}</strong><span>已撤销</span></div>
    </div>
    <div className="review-console">
      <aside className="panel relation-catalog">
        <div className="panel-header"><div><div className="eyebrow">ALL RELATIONS</div><h2>关系列表</h2></div><span className="count-badge">{visible.length}</span></div>
        <div className="search-field"><Search size={15}/><input value={query} onChange={e=>{const v=e.target.value;ui.guardNavigation(()=>setQuery(v))}} placeholder="搜索实体、关系或来源…" aria-label="搜索全部关系"/></div>
        <div className="relation-filters">{[['all','全部'],['active','有效'],['pending','待审'],['rejected','撤销']].map(([id,label]) =>
          <button key={id} className={filter===id?'active':''} onClick={()=>ui.guardNavigation(()=>setFilter(id))}>{label}<span>{counts[id]}</span></button>)}</div>
        <div className="relation-list">{visible.map(item => <button key={item.assertion_id}
          className={'relation-item '+(current?.assertion_id===item.assertion_id?'is-active':'')}
          onClick={()=>ui.guardNavigation(()=>setSelected(item.assertion_id))}>
          <div><span className={'relation-status relation-status--'+item.status}>{statusText[item.status]||item.status}</span>
            <small>{item.assertion.source_doc_id}</small></div>
          <strong>{item.assertion.subject_label || item.assertion.subject_id}</strong>
          <span className="relation-predicate">{relationLabels[item.assertion.predicate]||item.assertion.predicate} → {item.assertion.object_label || item.assertion.object_id}</span>
          <code>{item.assertion_id}</code>
        </button>)}</div>
      </aside>
      {a ? <div className="relation-detail">
        {draft.recovery}
        {sourceError&&<Alert severity="warning">{sourceError}</Alert>}
        {conflict&&<Alert severity="warning" action={<Button onClick={async()=>{draft.stash();setFormId('');await load()}}>暂存并读取最新版</Button>}>服务器版本已变化；先保留本地修改，再与最新版本比较。</Alert>}
        <div className="panel relation-evidence">
          <div className="panel-header"><div><div className="eyebrow">KNOWLEDGE ↔ CHUNK</div><h2>来源与证据</h2></div>
            <span className={'relation-status relation-status--'+current.status}>{statusText[current.status]||current.status}</span></div>
          <div className="relation-triple"><strong>{a.subject_label}</strong><span>{a.predicate}</span><strong>{a.object_label}</strong></div>
          <div className="provenance-meta"><span>文档 {a.source_doc_id}</span><span>片段 {a.source_chunk_id}</span><span>页码 {a.page_start || '—'}</span></div>
          <blockquote>{a.source_text_quote || '当前断言没有来源引文。'}</blockquote>
          <Button onClick={()=>ui.openEvidence(EvidenceAdapter(a,{title:source?.chunk?.title||a.source_doc_id,quote:source?.chunk?.text||a.source_text_quote,reviewStatus:current.status,knowledgeRevision:current.review_id,reviewUrl:'/?assertion_id='+encodeURIComponent(current.assertion_id)+'#review'}))}>在证据面板核对</Button>
          {source?.chunk?.text && <details className="source-context"><summary>查看完整来源片段 · {source.chunk.title || source.chunk.doc_id}</summary>
            <p>{source.chunk.text}</p></details>}
          <div className="related-chunks">同一片段关联 {source?.related_assertion_ids?.length || 0} 条断言 · 历史审核 {current.revision_count} 次</div>
        </div>
        <div className="panel relation-editor">
          <div className="panel-header"><div><div className="eyebrow">SCHEMA-CONSTRAINED EDITOR</div><h2>审核与修订</h2></div><ShieldCheck size={18}/></div>
          <div className="segment">{[['approved','确认有效'],['modified','修改并保存'],['rejected','撤销关系']].map(([id,label]) =>
            <button key={id} className={decision===id?'active':''} onClick={()=>setDecision(id)}>{label}</button>)}</div>
          {decision === 'modified' && <div className="relation-fields">
            <div className="form-grid">{textField('主体名称','subject_label')}{textField('主体 ID','subject_id')}</div>
            <div className="form-grid"><label>主体类型<input list="entity-types" value={corrected.subject_type||''} onChange={e=>update('subject_type',e.target.value)}/></label>
              <label>关系 / 属性<input list="predicate-types" value={corrected.predicate||''} onChange={e=>update('predicate',e.target.value)}/></label></div>
            <div className="form-grid">{textField('客体名称或值','object_label')}{textField('客体 ID 或值','object_id')}</div>
            <div className="form-grid"><label>客体类型<input list="entity-types" value={corrected.object_type||''} onChange={e=>update('object_type',e.target.value)}/></label>
              <label>客体种类<select value={corrected.object_kind||'entity'} onChange={e=>update('object_kind',e.target.value)}>
                <option value="entity">实体</option><option value="literal">属性值</option></select></label></div>
            <div className="form-grid"><label>生效日期<input type="date" value={corrected.valid_from?.slice(0,10)||''} onChange={e=>update('valid_from',e.target.value)}/></label>
              <label>失效日期<input type="date" value={corrected.valid_to?.slice(0,10)||''} onChange={e=>update('valid_to',e.target.value)}/></label></div>
            <datalist id="entity-types">{entityTypes.map(t=><option value={t} key={t}/>)}</datalist>
            <datalist id="predicate-types">{[...new Set([...relationTypes,...attrs])].map(t=><option value={t} key={t}/>)}</datalist>
          </div>}
          <div className="form-grid"><label>审核人<input value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label>
            {decision !== 'approved' && <label>问题类型<input value={errorType} onChange={e=>setErrorType(e.target.value)} placeholder="例如 relation_type_error"/></label>}</div>
          <label className="relation-comment">审核意见<textarea value={comment} onChange={e=>setComment(e.target.value)}
            placeholder={decision==='approved'?'可选；请确认已核对来源':'说明修订或撤销原因'} /></label>
          {decision === 'approved' && <p className="edit-note">确认有效会保存当前内容；修改字段请选择“修改并保存”。</p>}
          {dirty&&<details className="ui-review-diff"><summary>查看本次字段修改</summary>{Object.entries(corrected).filter(([key,value])=>JSON.stringify(value)!==JSON.stringify(a[key])).map(([key,value])=><p key={key}><strong>{key}</strong><br/>原值：{String(a[key]??'未记录')}<br/>修改：{String(value??'未记录')}</p>)}</details>}
          <div className="ui-review-actions"><Button onClick={draft.stash} disabled={!dirty||busy}>暂存本机</Button><button className="button button--primary" onClick={submit} disabled={busy || !reviewer.trim() || conflict || (decision!=='approved'&&!comment.trim())}>
            {busy?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>}保存审核版本</button></div>
          {message && <Notice tone="success">{message}</Notice>}{error && <Notice tone="error">{error}</Notice>}
        </div>
        <div className="panel relation-history"><div className="eyebrow">REVIEW HISTORY</div>
          {(history?.reviews||[]).slice().reverse().map((r,i)=><div key={r.review_id||i}>
            <strong>{statusText[r.decision]||r.decision}</strong><span>{r.reviewed_by||'—'} · {r.reviewed_at||'—'}</span>
            {r.review_comment && <p>{r.review_comment}</p>}</div>)}
        </div>
      </div> : <Empty title="没有关系记录" detail="当前知识库尚无可审核断言。" icon={GitMerge}/>}
    </div>
  </section>;
}
export function ResolutionWorkspace({ asOf, onGraphRefresh, embedded = false }) {
  const ui=useUI();
  const [audit, setAudit] = useState(null);
  const [candidateIndex, setCandidateIndex] = useState(0);
  const [aliasId, setAliasId] = useState('');
  const [canonicalId, setCanonicalId] = useState('');
  const [reviewer, setReviewer] = useState(()=>{try{return localStorage.getItem('ui-reviewer')||''}catch{return ''}});
  const [busy,setBusy]=useState(false);
  const [format, setFormat] = useState('jsonld');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const reload = () => api('/api/audit').then(setAudit).catch(e => setError(e.message));
  useEffect(() => { reload(); }, []);
  const candidate = audit?.entity_candidates?.[candidateIndex];
  useEffect(() => {
    if (candidate) { setAliasId(candidate.canonical_ids[0] || ''); setCanonicalId(candidate.canonical_ids[1] || ''); }
  }, [candidateIndex, audit]);
  async function merge(action = 'merge', alias = aliasId, canonical = canonicalId) {
    if(busy||!reviewer.trim())return;
    if(!await ui.request({title:action==='merge'?'确认实体合并':'撤销实体合并',description:action==='merge'?`将别名 ${alias} 关联到 ${canonical}。原始断言保留，别名合并可撤销。`:`解除 ${alias} 到 ${canonical} 的别名关联，保留审核历史。`,submitLabel:action==='merge'?'确认合并':'撤销合并',danger:action!=='merge'}))return;
    setBusy(true);
    setError(''); setMessage('');
    try {
      await post('/api/entities/alias', { alias_id: alias, canonical_id: canonical, reviewer, action });
      setMessage(action === 'merge' ? '全局别名已记录，原始断言保持不变。' : '别名合并已撤销。');
      await reload(); onGraphRefresh?.();
    } catch (e) { setError(e.message); } finally {setBusy(false)}
  }
  return <section className={embedded ? 'governance-pane' : 'workspace-scroll'}>
    {!embedded && <WorkspaceHeading kicker="ENRICH / RESOLVE" title="实体与冲突"
      description="跨来源核查、确认别名，并导出可追溯图谱。"/>}
    {embedded && <p className="governance-context">核对同名实体和跨来源差异；确认合并后仍保留原始断言及审核历史。</p>}
    <div className="stats-strip">
      <div><strong>{audit?.entity_candidates?.length ?? '—'}</strong><span>重复实体候选</span></div>
      <div><strong>{audit?.conflicts?.length ?? '—'}</strong><span>跨来源冲突</span></div>
      <div><strong>{Object.keys(audit?.aliases || {}).length}</strong><span>已确认别名</span></div>
    </div>
    {error && <Notice tone="error">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
    <div className="resolution-grid">
      <div className="panel resolution-panel"><div className="panel-header"><div><div className="eyebrow">ENTITY RESOLUTION</div><h2>全局实体去重</h2></div><GitMerge size={18}/></div>
        <p className="panel-intro">同类型且规范化名称一致的 ID 进入候选队列。合并由审核人决定，可随时撤销。</p>
        {candidate ? <>
          <div className="candidate-tabs">{audit.entity_candidates.map((c,i) => <button className={i===candidateIndex?'active':''} onClick={() => setCandidateIndex(i)} key={i}>{c.normalized_label}</button>)}</div>
          <div className="candidate-card"><div className="eyebrow">{candidate.entity_type} / {candidate.source_doc_ids?.length || 0} SOURCES</div>
            <h3>{candidate.normalized_label}</h3><div className="id-list">{candidate.canonical_ids.map(id => <code key={id}>{id}</code>)}</div></div>
          <div className="form-grid"><label>合并的别名<select value={aliasId} onChange={e=>setAliasId(e.target.value)}>{candidate.canonical_ids.map(id=><option key={id}>{id}</option>)}</select></label>
            <label>保留的全局 ID<select value={canonicalId} onChange={e=>setCanonicalId(e.target.value)}>{candidate.canonical_ids.map(id=><option key={id}>{id}</option>)}</select></label></div>
          <label>审核人<input value={reviewer} onChange={e=>setReviewer(e.target.value)} placeholder="姓名或工号"/></label>
          <button className="button button--primary" onClick={() => merge()} disabled={busy || !reviewer.trim() || aliasId===canonicalId}><Check size={16}/>{busy?'正在保存…':'确认实体合并'}</button>
        </> : <Empty title="没有重复候选" detail="当前已审核和待审核断言未发现同名同类的不同 ID。" icon={GitMerge}/>}
        {Object.entries(audit?.aliases || {}).length > 0 && <div className="alias-log"><div className="eyebrow">ACTIVE ALIASES</div>
          {Object.entries(audit.aliases).map(([alias,canonical])=><div key={alias}><code>{alias}</code><ArrowRight size={13}/><code>{canonical}</code><button onClick={()=>merge('revoke',alias,canonical)} disabled={!reviewer.trim()} title="撤销合并"><X size={14}/></button></div>)}</div>}
      </div>
      <div className="side-stack">
        <div className="panel resolution-panel"><div className="panel-header"><div><div className="eyebrow">SOURCE RECONCILIATION</div><h2>冲突核查</h2></div><Filter size={18}/></div>
          <p className="panel-intro">同一主体和关系在重叠生效期内指向不同对象时，列为待人工核实。</p>
          {(audit?.conflicts || []).length ? audit.conflicts.map((c,i)=><div className="conflict-card" key={i}>
            <strong>{c.subject_id}</strong><span>{c.predicate}</span>
            <div>{c.object_ids?.join(' ↔ ')}</div><small>{c.source_doc_ids?.join(' · ')}</small>
          </div>) : <Empty title="暂无规则冲突" detail="这不代表来源间完全一致；当前规则没有发现候选冲突。" icon={ShieldCheck}/>}
        </div>
        <div className="panel resolution-panel"><div className="panel-header"><div><div className="eyebrow">PROVENANCE / PROV-O</div><h2>图谱导出</h2></div><Download size={18}/></div>
          <p className="panel-intro">仅包含人工审核通过的断言。可按当前生效时点导出。</p>
          <div className="form-grid"><label>格式<select value={format} onChange={e=>setFormat(e.target.value)}><option value="jsonld">PROV-O · JSON-LD</option><option value="turtle">PROV-O · Turtle</option><option value="graphml">GraphML</option><option value="csv">CSV</option></select></label>
            <label>生效时点<input type="date" value={asOf || today()} readOnly/></label></div>
          <a className="button button--quiet" href={`/api/export?format=${format}&as_of=${encodeURIComponent(asOf || '')}`}><Download size={16}/>下载文件</a>
        </div>
      </div>
    </div>
  </section>;
}

export function GovernanceWorkspace({ tab = 'assertions', setTab, summary, asOf, onGraphRefresh }) {
  return <section className="workspace-scroll governance-workspace">
    <WorkspaceHeading kicker="GOVERNANCE / EVIDENCE" title="知识治理"
      description="在同一处核对断言原文、修订关系、确认实体别名，并检查跨来源冲突与导出图谱。"/>
    <Tabs value={tab} onChange={(_,v)=>setTab(v)} aria-label="知识治理内容" sx={{mb:2,borderBottom:1,borderColor:'divider'}}><Tab value="assertions" label="断言审核" icon={<ShieldCheck size={17}/>} iconPosition="start"/><Tab value="entities" label="实体与冲突" icon={<GitMerge size={17}/>} iconPosition="start"/></Tabs>
    {tab==='entities'
      ? <ResolutionWorkspace embedded asOf={asOf} onGraphRefresh={onGraphRefresh}/>
      : <ReviewWorkspace embedded summary={summary} onGraphRefresh={onGraphRefresh}/>}
  </section>;
}
