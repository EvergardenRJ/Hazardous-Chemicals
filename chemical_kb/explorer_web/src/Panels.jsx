import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowRight, BookOpen, Check, ChevronRight, Download, FileText, Filter,
  GitMerge, LoaderCircle, Search, ShieldCheck, UploadCloud, X
} from 'lucide-react';
import { api, post, compactNumber, sourceLabel, today } from './api';

export function WorkspaceHeading({ kicker, title, description, action }) {
  return <div className="workspace-heading">
    <div><div className="eyebrow">{kicker}</div><h1>{title}</h1><p>{description}</p></div>
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
  const [question, setQuestion] = useState(seedQuestion || '');
  const [answer, setAnswer] = useState(null);
  const [quick, setQuick] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (seedQuestion) setQuestion(seedQuestion); }, [seedQuestion]);
  const prompts = ['液氯泄漏后应如何应急处置？', '储存甲醇有哪些安全要求？', '压力容器事故有哪些常见原因？'];
  async function ask() {
    if (!question.trim()) return;
    setBusy(true); setError(''); setAnswer(null);
    try { setAnswer(await post('/api/ask', { question: question.trim(), as_of: asOf })); }
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
      description="在关键词、语义向量与人工审核图谱之间追踪答案的证据路径。"
      action={<DateFilter value={asOf} onChange={setAsOf}/>}/>
    <div className="ask-layout">
      <div className="panel ask-compose">
        <div className="panel-header"><div><div className="eyebrow">QUERY CONSOLE</div><h2>向知识库提问</h2></div><span className="live-dot">RRF FUSION</span></div>
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
          <div className="pipeline-step"><span>01</span><div><strong>多路召回</strong><small>关键词 · 向量 · 图谱</small></div></div>
          <div className="pipeline-step"><span>02</span><div><strong>RRF 融合</strong><small>合并同一来源片段</small></div></div>
          <div className="pipeline-step"><span>03</span><div><strong>证据验证</strong><small>重排 · 来源 · 时点</small></div></div>
        </div>
      </aside>
    </div>
    {error && <Notice tone="error">{error}</Notice>}
    {answer && <div className="results-layout">
      <section className="panel answer-panel"><div className="panel-header"><div><div className="eyebrow">GROUNDED RESPONSE</div><h2>回答</h2></div><span className="count-badge">{answer.evidence?.length || 0} 条证据</span></div>
        <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{answer.answer || '没有足够可靠的证据生成回答。'}</ReactMarkdown></div>
      </section>
      <section className="evidence-stack"><div className="section-label">证据链 / SOURCES</div>
        {(answer.evidence || []).map((item, index) => <article className="panel evidence-item" key={index}>
          <div className="evidence-top"><span className="evidence-index">{String(index+1).padStart(2,'0')}</span>
            <span className="status-pill status-pill--blue">{(item.routes || ['vector']).join(' + ')}</span></div>
          <h3>{item.metadata?.title || '未命名来源'}</h3><div className="subtle">{sourceLabel(item.metadata || {})}</div>
          <p>{item.metadata?.text || ''}</p>
          <div className="evidence-foot">RRF {Number(item.rrf_score || 0).toFixed(4)} · Rerank {Number(item.rerank_score || 0).toFixed(2)}</div>
        </article>)}
      </section>
    </div>}
    {quick && <section className="panel quick-results"><div className="panel-header"><div><div className="eyebrow">INSTANT EVIDENCE</div><h2>片段预览</h2></div><span className="count-badge">{quick.evidence?.length || 0} 条</span></div>
      {(quick.evidence || []).map((item, index) => <div className="quick-row" key={index}><strong>{item.metadata?.title || '片段'}</strong><span>{sourceLabel(item.metadata || {})}</span><p>{item.metadata?.text?.slice(0, 240)}</p></div>)}
    </section>}
  </section>;
}

export function ReviewWorkspace({ onGraphRefresh, summary }) {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [decision, setDecision] = useState('modified');
  const [reviewer, setReviewer] = useState('adamin');
  const [comment, setComment] = useState('');
  const [errorType, setErrorType] = useState('');
  const [corrected, setCorrected] = useState({});
  const [source, setSource] = useState(null);
  const [history, setHistory] = useState(null);
  const [schema, setSchema] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const load = () => api('/api/reviews').then(d => setItems(d.items || [])).catch(e => setError(e.message));
  useEffect(() => { load(); api('/api/schema').then(setSchema).catch(() => {}); }, []);
  const current = items.find(item => item.assertion_id === selected) || items[0];
  useEffect(() => {
    if (!current) return;
    setSelected(current.assertion_id);
    setCorrected({ ...current.assertion });
    setDecision(current.status === 'pending' ? 'approved' : 'modified');
    setComment(''); setMessage('');
    const id = encodeURIComponent(current.assertion_id);
    api('/api/reviews/' + id + '/source').then(setSource).catch(() => setSource(null));
    api('/api/reviews/' + id + '/history').then(setHistory).catch(() => setHistory(null));
  }, [current?.assertion_id, current?.review_id]);
  const counts = {
    all: items.length,
    active: items.filter(x => ['approved','modified'].includes(x.status)).length,
    pending: items.filter(x => x.status === 'pending').length,
    rejected: items.filter(x => x.status === 'rejected').length
  };
  const visible = items.filter(item => {
    if (filter === 'active' && !['approved','modified'].includes(item.status)) return false;
    if (filter !== 'all' && filter !== 'active' && item.status !== filter) return false;
    if (!query.trim()) return true;
    const a = item.assertion;
    return [item.assertion_id, a.subject_label, a.predicate, a.object_label,
      a.source_doc_id, a.source_text_quote].some(x => String(x || '').toLowerCase().includes(query.trim().toLowerCase()));
  });
  const update = (key, value) => setCorrected(a => ({...a, [key]: value}));
  const textField = (label, key) => <label key={key}>{label}<input value={corrected[key] ?? ''}
    onChange={e => update(key, e.target.value)}/></label>;
  const relationTypes = schema?.relation_types?.map(r => r.id) || [];
  const entityTypes = schema?.entity_types?.map(e => e.id) || [];
  const attrs = schema?.entity_types?.find(e => e.id === corrected.subject_type)?.attributes?.map(a => a.name) || [];
  async function submit() {
    if (!current) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await post('/api/reviews/' + encodeURIComponent(current.assertion_id), {
        decision, reviewer: reviewer.trim() || 'adamin', comment: comment.trim(),
        error_type: errorType.trim(), expected_review_id: current.review_id,
        corrected: decision === 'modified' ? corrected : null
      });
      setMessage('审核版本已保存；图谱与导出会使用最新版本。');
      await load(); onGraphRefresh?.();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  const a = current?.assertion;
  const statusText = {approved:'已通过',modified:'已修订',pending:'待审核',rejected:'已撤销'};
  return <section className="workspace-scroll">
    <WorkspaceHeading kicker="GOVERNANCE / RELATION CATALOG" title="断言审核"
      description={`当前仅 ${summary?.relation_source_docs ?? 0} / ${summary?.documents ?? 0} 份文档进入关系候选流程。这里列出已抽取的关系与属性，可沿来源片段核实并修订。`}/>
    <div className="review-summary">
      <div><strong>{counts.all}</strong><span>全部断言</span></div>
      <div><strong>{counts.active}</strong><span>有效断言</span></div>
      <div><strong>{counts.pending}</strong><span>待审核</span></div>
      <div><strong>{counts.rejected}</strong><span>已撤销</span></div>
    </div>
    <div className="review-console">
      <aside className="panel relation-catalog">
        <div className="panel-header"><div><div className="eyebrow">ALL RELATIONS</div><h2>关系列表</h2></div><span className="count-badge">{visible.length}</span></div>
        <div className="search-field"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索实体、关系或来源…" aria-label="搜索全部关系"/></div>
        <div className="relation-filters">{[['all','全部'],['active','有效'],['pending','待审'],['rejected','撤销']].map(([id,label]) =>
          <button key={id} className={filter===id?'active':''} onClick={()=>setFilter(id)}>{label}<span>{counts[id]}</span></button>)}</div>
        <div className="relation-list">{visible.map(item => <button key={item.assertion_id}
          className={'relation-item '+(current?.assertion_id===item.assertion_id?'is-active':'')}
          onClick={()=>setSelected(item.assertion_id)}>
          <div><span className={'relation-status relation-status--'+item.status}>{statusText[item.status]||item.status}</span>
            <small>{item.assertion.source_doc_id}</small></div>
          <strong>{item.assertion.subject_label || item.assertion.subject_id}</strong>
          <span className="relation-predicate">{item.assertion.predicate} → {item.assertion.object_label || item.assertion.object_id}</span>
          <code>{item.assertion_id}</code>
        </button>)}</div>
      </aside>
      {a ? <div className="relation-detail">
        <div className="panel relation-evidence">
          <div className="panel-header"><div><div className="eyebrow">KNOWLEDGE ↔ CHUNK</div><h2>来源与证据</h2></div>
            <span className={'relation-status relation-status--'+current.status}>{statusText[current.status]||current.status}</span></div>
          <div className="relation-triple"><strong>{a.subject_label}</strong><span>{a.predicate}</span><strong>{a.object_label}</strong></div>
          <div className="provenance-meta"><span>文档 {a.source_doc_id}</span><span>片段 {a.source_chunk_id}</span><span>页码 {a.page_start || '—'}</span></div>
          <blockquote>{a.source_text_quote || '当前断言没有来源引文。'}</blockquote>
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
          <button className="button button--primary" onClick={submit} disabled={busy || (decision!=='approved'&&!comment.trim())}>
            {busy?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>}保存审核版本</button>
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
export function ResolutionWorkspace({ asOf, onGraphRefresh }) {
  const [audit, setAudit] = useState(null);
  const [candidateIndex, setCandidateIndex] = useState(0);
  const [aliasId, setAliasId] = useState('');
  const [canonicalId, setCanonicalId] = useState('');
  const [reviewer, setReviewer] = useState('');
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
    setError(''); setMessage('');
    try {
      await post('/api/entities/alias', { alias_id: alias, canonical_id: canonical, reviewer, action });
      setMessage(action === 'merge' ? '全局别名已记录，原始断言保持不变。' : '别名合并已撤销。');
      await reload(); onGraphRefresh?.();
    } catch (e) { setError(e.message); }
  }
  return <section className="workspace-scroll">
    <WorkspaceHeading kicker="ENRICH / RESOLVE" title="实体与冲突"
      description="跨来源核查、人工确认别名，并导出可追溯图谱。"/>
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
          <button className="button button--primary" onClick={() => merge()} disabled={!reviewer.trim() || aliasId===canonicalId}><Check size={16}/>确认实体合并</button>
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

export function LibraryWorkspace() {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api(`/api/documents?q=${encodeURIComponent(query)}&page=${page}&size=25`)
      .then(v => { if(active) setData(v); }).catch(e=>{ if(active) setError(e.message); });
    return () => { active = false; };
  }, [query,page]);
  async function upload() {
    if (!file) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const body = new FormData(); body.append('file', file);
      const result = await api('/api/documents/upload', { method:'POST', body });
      setMessage(`${result.filename} 已保存到待处理目录。`); setFile(null);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <section className="workspace-scroll">
    <WorkspaceHeading kicker="LIBRARY / SOURCES" title="文档库"
      description="浏览现有标准、法规与事故报告；上传 PDF 进入原有待处理目录。"/>
    <div className="library-layout">
      <div className="panel library-panel"><div className="panel-header"><div><div className="eyebrow">SOURCE INVENTORY</div><h2>文档目录</h2></div><span className="count-badge">{compactNumber(data?.total)}</span></div>
        <div className="search-field"><Search size={17}/><input value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}} placeholder="搜索标题、标准号或文档 ID"/></div>
        <div className="document-list">{(data?.items || []).map(item=><div className="document-row" key={item.doc_id}>
          <span className="doc-icon"><FileText size={18}/></span><div><strong>{item.title}</strong><small>{item.code || item.doc_id}</small></div>
          <span className="doc-meta">{item.document_type || '文档'} · {item.chunks} 片段</span>
        </div>)}</div>
        {!data?.items?.length && <Empty title="没有匹配文档" detail="换个关键词再试。"/>}
        <div className="pager"><button disabled={page<=1} onClick={()=>setPage(page-1)}>上一页</button><span>{page} / {Math.max(1,Math.ceil((data?.total||0)/25))}</span><button disabled={page*25>=(data?.total||0)} onClick={()=>setPage(page+1)}>下一页</button></div>
      </div>
      <aside className="panel upload-panel"><div className="eyebrow">INGESTION / PDF</div><h2>上传新文档</h2>
        <p>文件先保存到原项目的待处理目录，之后再按现有解析与索引流程入库。</p>
        <label className="dropzone"><UploadCloud size={30}/><strong>{file?.name || '选择 PDF 文件'}</strong><span>最大 50 MB · 仅 PDF</span>
          <input type="file" accept=".pdf,application/pdf" onChange={e=>setFile(e.target.files?.[0] || null)}/></label>
        <button className="button button--primary" onClick={upload} disabled={!file || busy}>{busy?<LoaderCircle className="spin" size={16}/>:<UploadCloud size={16}/>}保存文档</button>
        {message && <Notice tone="success">{message}</Notice>}{error && <Notice tone="error">{error}</Notice>}
      </aside>
    </div>
  </section>;
}

export function WikiWorkspace() {
  const [entities, setEntities] = useState([]);
  const [entity, setEntity] = useState('');
  const [input, setInput] = useState('');
  const [detail, setDetail] = useState(null);
  const [selectedSection, setSelectedSection] = useState('');
  const [edited, setEdited] = useState('');
  const [comment, setComment] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const loadList = () => api('/api/wiki').then(d=>setEntities(d.entities||[])).catch(e=>setError(e.message));
  const loadDetail = (name) => api('/api/wiki/' + encodeURIComponent(name)).then(d=>{setDetail(d);setEntity(name);setSelectedSection(d.sections?.[0]?.section||'');}).catch(e=>setError(e.message));
  useEffect(()=>{loadList();},[]);
  const section = detail?.sections?.find(s=>s.section===selectedSection);
  useEffect(()=>{setEdited(section?.content || '');},[selectedSection,detail]);
  async function generate() {
    if(!input.trim()) return; setBusy(true);setError('');setMessage('');
    try { await post('/api/wiki/' + encodeURIComponent(input.trim()) + '/generate', {});
      await loadList(); await loadDetail(input.trim()); setMessage('Wiki 已生成。');
    } catch(e){setError(e.message);} finally{setBusy(false);}
  }
  async function review(status) {
    if(!section) return; setBusy(true);setError('');setMessage('');
    try { await post('/api/wiki/' + encodeURIComponent(entity) + '/review', {
      section:section.section,review_status:status,reviewed_content:status==='modified'?edited:section.content,
      review_comment:comment,error_type:status==='approved'?'':'content_review',reviewer
    }); await loadDetail(entity); setMessage('Section 审核已记录。'); setComment('');
    } catch(e){setError(e.message);} finally{setBusy(false);}
  }
  return <section className="workspace-scroll">
    <WorkspaceHeading kicker="KNOWLEDGE / WIKI" title="化学品 Wiki"
      description="生成、阅读并逐节审核安全知识，保留每节的证据来源。"/>
    <div className="wiki-search"><div className="search-field"><Search size={18}/><input value={input} onChange={e=>setInput(e.target.value)} placeholder="输入化学品名称，例如 液氯、氨"/></div>
      <button className="button button--primary" onClick={()=>{ if(entities.includes(input.trim())) loadDetail(input.trim()); else generate(); }} disabled={!input.trim()||busy}>
        {busy?<LoaderCircle className="spin" size={16}/>:<ArrowRight size={16}/>}打开或生成</button></div>
    {error && <Notice tone="error">{error}</Notice>}{message && <Notice tone="success">{message}</Notice>}
    <div className="wiki-layout">
      <aside className="panel wiki-nav"><div className="panel-header"><div><div className="eyebrow">WIKI REGISTRY</div><h2>已有条目</h2></div><span className="count-badge">{entities.length}</span></div>
        {entities.map(name=><button className={entity===name?'is-active':''} key={name} onClick={()=>loadDetail(name)}><BookOpen size={15}/>{name}<ChevronRight size={14}/></button>)}
      </aside>
      {detail ? <div className="wiki-main">
        <div className="panel wiki-content"><div className="panel-header"><div><div className="eyebrow">CHEMICAL DOSSIER</div><h2>{entity}</h2></div><span className="status-pill status-pill--blue">{detail.sections?.length||0} SECTIONS</span></div>
          <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.markdown}</ReactMarkdown></div></div>
        <div className="panel wiki-review"><div className="panel-header"><div><div className="eyebrow">SECTION REVIEW</div><h2>逐节审核</h2></div></div>
          <div className="section-tabs">{detail.sections?.map(s=><button className={selectedSection===s.section?'active':''} onClick={()=>setSelectedSection(s.section)} key={s.section}>{s.section}</button>)}</div>
          {section && <><div className="section-meta"><span className="status-pill status-pill--blue">{section.knowledge_source}</span><span>{detail.reviews?.[section.section]?.review_status||'pending'}</span></div>
            <textarea className="section-editor" value={edited} onChange={e=>setEdited(e.target.value)} aria-label="Wiki节内容"/>
            <div className="form-grid"><label>审核人<input value={reviewer} onChange={e=>setReviewer(e.target.value)} placeholder="姓名或工号"/></label>
              <label>审核意见<input value={comment} onChange={e=>setComment(e.target.value)} placeholder="修改/拒绝时必填"/></label></div>
            <div className="compose-actions"><button className="button button--primary" onClick={()=>review('approved')} disabled={busy||!reviewer.trim()}><Check size={15}/>通过</button>
              <button className="button button--quiet" onClick={()=>review('modified')} disabled={busy||!reviewer.trim()||!comment.trim()}>修改并通过</button>
              <button className="button button--danger" onClick={()=>review('rejected')} disabled={busy||!reviewer.trim()||!comment.trim()}>拒绝</button></div></>}
        </div>
      </div> : <Empty title="选择一个 Wiki 条目" detail="从左侧列表打开，或输入新化学品名称生成。" icon={BookOpen}/>}
    </div>
  </section>;
}


