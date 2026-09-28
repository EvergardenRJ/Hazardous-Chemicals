import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity, ArrowRight, BookOpen, Check, ChevronDown, CircleHelp, Command,
  Download, FileText, FlaskConical, GitMerge, LayoutDashboard, Maximize2, Network,
  Pause, Play, Search, Settings2, ShieldCheck, SlidersHorizontal, Sparkles,
  X, ZoomIn, ZoomOut, Sun, Moon
} from 'lucide-react';
import GraphCanvas, { TYPE_COLORS } from './GraphCanvas.jsx';
import { api, compactNumber, sourceLabel, today, validAt } from './api';
import {
  AskWorkspace, LibraryWorkspace, ResolutionWorkspace, ReviewWorkspace,
  WikiWorkspace, WorkspaceHeading
} from './Panels.jsx';

const NAV = [
  { id:'overview', label:'总览', hint:'Overview', icon:LayoutDashboard },
  { id:'graph', label:'图谱探索', hint:'Explorer', icon:Network },
  { id:'ask', label:'智能检索', hint:'Analyze', icon:Search },
  { id:'review', label:'断言审核', hint:'Review', icon:ShieldCheck },
  { id:'resolve', label:'实体与冲突', hint:'Resolution', icon:GitMerge },
  { id:'library', label:'文档库', hint:'Library', icon:FileText },
  { id:'wiki', label:'知识 Wiki', hint:'Wiki', icon:BookOpen }
];

const TYPE_LABEL = {
  accident:'事故', standard:'标准', regulation:'法规', chemical:'化学品',
  equipment:'设备', enterprise:'企业', causal_factor:'致因', requirement:'要求',
  clause:'条款', measure:'措施', process:'工艺', site:'场所',
  major_hazard_source:'危险源', entity:'实体'
};

function stateFromHash() {
  const id = window.location.hash.replace('#','');
  return NAV.some(item => item.id === id) ? id : 'overview';
}

function StatusChip({ children, tone='blue' }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

function Metric({ label, value, icon: Icon, tone='blue' }) {
  return <div className="metric-tile" data-tone={tone}><div className="metric-icon"><Icon size={18}/></div>
    <strong>{compactNumber(value)}</strong><span>{label}</span></div>;
}

function Welcome({ summary, onNavigate }) {
  const cards = [
    { id:'graph', eyebrow:'PRIMARY WORKSPACE', title:'知识图谱探索', text:'在可交互关系网络里聚焦实体、追踪路径与来源。', icon:Network, primary:true },
    { id:'ask', eyebrow:'ANALYZE', title:'智能检索', text:'将关键词、语义向量与图谱证据融合为答案。', icon:Search },
    { id:'review', eyebrow:'GOVERNANCE', title:'断言审核', text:'核对来源原文，决定知识是否进入生产图谱。', icon:ShieldCheck },
    { id:'resolve', eyebrow:'ENRICH', title:'实体与冲突', text:'跨来源去重、冲突核查与 PROV-O 导出。', icon:GitMerge },
    { id:'library', eyebrow:'SOURCES', title:'文档库', text:'浏览标准法规、事故报告与来源片段。', icon:FileText },
    { id:'wiki', eyebrow:'DOSSIERS', title:'化学品 Wiki', text:'阅读并逐节审核安全知识专辑。', icon:BookOpen }
  ];
  return <main className="welcome-page workspace-scroll">
    <div className="hero">
      <div className="hero-copy"><div className="hero-kicker"><span className="pulse-dot"/> CHEMICAL KNOWLEDGE INTELLIGENCE</div>
        <h1>让每一条知识<br/><em>都能追溯来源。</em></h1>
        <p>以图谱为中心，连接化学品、事故、法规和安全措施。沿关系探索，按生效时点检索，在证据链中做决定。</p>
        <div className="hero-actions"><button className="button button--primary button--large" onClick={()=>onNavigate('graph')}>进入图谱探索 <ArrowRight size={18}/></button>
          <button className="button button--ghost button--large" onClick={()=>onNavigate('ask')}>开始检索</button></div>
        <div className="hero-caption"><span className="hero-caption-line"/> LIVE DATASET · NO SIMULATED FACTS</div>
      </div>
      <div className="hero-visual" aria-hidden="true">
        <div className="visual-topbar"><span/><span/><span/><div>KNOWLEDGE / NETWORK</div></div>
        <svg viewBox="0 0 600 420" preserveAspectRatio="xMidYMid meet">
          <defs><radialGradient id="hGlow"><stop stopColor="#4aa3ff" stopOpacity=".35"/><stop offset="1" stopColor="#4aa3ff" stopOpacity="0"/></radialGradient></defs>
          <circle cx="300" cy="215" r="170" fill="url(#hGlow)"/>
          <g className="hero-grid-lines"><path d="M0 110H600M0 210H600M0 310H600M100 0V420M200 0V420M300 0V420M400 0V420M500 0V420"/></g>
          <g className="hero-relations">
            <path d="M300 205L160 112M300 205L433 118M300 205L463 285M300 205L170 312M160 112L116 215M433 118L509 195M170 312L294 357M463 285L294 357"/>
          </g>
          <g className="hero-nodes">
            <circle cx="300" cy="205" r="19" className="hero-node hero-node--core"/><circle cx="160" cy="112" r="10" className="hero-node hero-node--cyan"/>
            <circle cx="433" cy="118" r="12" className="hero-node hero-node--mint"/><circle cx="463" cy="285" r="10" className="hero-node hero-node--amber"/>
            <circle cx="170" cy="312" r="11" className="hero-node hero-node--rose"/><circle cx="116" cy="215" r="6" className="hero-node hero-node--muted"/>
            <circle cx="509" cy="195" r="7" className="hero-node hero-node--muted"/><circle cx="294" cy="357" r="8" className="hero-node hero-node--muted"/>
          </g>
          <g className="hero-labels"><text x="327" y="199">KNOWLEDGE CORE</text><text x="86" y="96">STANDARDS</text>
            <text x="443" y="110">CHEMICALS</text><text x="475" y="309">RISK</text><text x="91" y="338">INCIDENTS</text></g>
        </svg>
        <div className="floating-card floating-card--top"><Sparkles size={14}/><div><strong>Evidence connected</strong><small>Traceable by source</small></div></div>
        <div className="floating-card floating-card--bottom"><Activity size={14}/><div><strong>Temporal graph</strong><small>Explore valid-time context</small></div></div>
      </div>
    </div>
    <div className="overview-metrics">
      <Metric label="知识片段" value={summary?.chunks} icon={FileText}/>
      <Metric label="已审核实体" value={summary?.nodes} icon={Network} tone="mint"/>
      <Metric label="已审核关系" value={summary?.edges} icon={GitMerge} tone="amber"/>
      <Metric label="待审断言" value={summary?.pending} icon={ShieldCheck} tone="rose"/>
    </div>
    <div className="coverage-note"><ShieldCheck size={17}/><span>关系抽取覆盖 <strong>{summary?.relation_source_docs ?? 0} / {compactNumber(summary?.documents)} 文档</strong>、<strong>{summary?.relation_source_chunks ?? 0} / {compactNumber(summary?.chunks)} 片段</strong>。当前关系来自已处理的来源片段，其余文档尚待抽取。{summary?.batch_extraction && <small>全库批处理已完成 {(summary.batch_extraction.chunks.done||0)+(summary.batch_extraction.chunks.empty||0)} / {compactNumber(summary.chunks)} 片段，暂存候选 {compactNumber(summary.batch_extraction.staged_candidates)} 条。</small>}</span></div>
    <div className="section-heading"><div><span className="eyebrow">WORKSPACES</span><h2>进入工作区</h2></div><div className="section-heading-line"/></div>
    <div className="workspace-cards">{cards.map(({id,eyebrow,title,text,icon:Icon,primary})=>
      <button key={id} className={`workspace-card ${primary?'workspace-card--primary':''}`} onClick={()=>onNavigate(id)}>
        <div className="card-top"><span>{eyebrow}</span><Icon size={primary?26:20}/></div>
        <div><h3>{title}</h3><p>{text}</p></div><ArrowRight className="card-arrow" size={19}/></button>)}</div>
    <div className="capability-band"><strong>INTELLIGENCE LAYER</strong><span>混合检索 / RRF</span><span>时态证据</span><span>全局实体归一</span><span>跨来源冲突</span><span>PROV-O 溯源</span></div>
  </main>;
}

function buildPath(nodes, edges, start, end) {
  if (!start || !end || start === end) return null;
  const adjacent = new Map(nodes.map(n=>[n.id,[]]));
  edges.forEach(e=>{adjacent.get(e.source)?.push([e.target,e.id]); adjacent.get(e.target)?.push([e.source,e.id]);});
  const queue=[start], previous=new Map([[start,null]]);
  for (let i=0;i<queue.length;i++) {
    const current=queue[i]; if (current===end) break;
    for (const [next,edgeId] of adjacent.get(current)||[]) {
      if (!previous.has(next)) {previous.set(next,[current,edgeId]);queue.push(next);}
    }
  }
  if (!previous.has(end)) return null;
  const pathNodes=[],pathEdges=[]; let at=end;
  while(at!==start) {pathNodes.push(at); const step=previous.get(at);pathEdges.push(step[1]);at=step[0];}
  pathNodes.push(start);pathNodes.reverse();pathEdges.reverse();
  return {nodes:pathNodes,edges:pathEdges};
}

function GraphDesk({ raw, loading, error, mode, setMode, asOf, setAsOf, onAsk, onResolve, externalFocusId, theme, summary }) {
  const canvasRef = useRef(null);
  const [selection, setSelection] = useState(null);
  const [focusId, setFocusId] = useState('');
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [relationFilter, setRelationFilter] = useState('');
  const [pathStart, setPathStart] = useState('');
  const [pathEnd, setPathEnd] = useState('');
  const [path, setPath] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [pathAttempted, setPathAttempted] = useState(false);
  useEffect(()=>{ if(externalFocusId && raw?.nodes?.some(n=>n.id===externalFocusId)) { setSelection({kind:'node',id:externalFocusId}); setFocusId(externalFocusId); } },[externalFocusId,raw]);
  const dateBounds = useMemo(()=>[...new Set((raw?.edges||[]).flatMap(e=>[e.valid_from?.slice(0,10),e.valid_to?.slice(0,10)]).filter(Boolean))].sort(),[raw]);
  const fullDates = useMemo(()=>[...new Set([...dateBounds,today()])].sort(),[dateBounds]);
  const dateIndex = Math.max(0,fullDates.indexOf(asOf));
  useEffect(()=>{
    if(!playing || dateBounds.length===0) return;
    const id=setInterval(()=>setAsOf(current=>{
      const at=fullDates.indexOf(current);return fullDates[(at+1+fullDates.length)%fullDates.length];
    }),1100);
    return ()=>clearInterval(id);
  },[playing,fullDates,setAsOf,dateBounds.length]);
  const filtered = useMemo(()=>{
    const allEdges=(raw?.edges||[]).filter(e=>validAt(e,asOf));
    const ids=new Set(allEdges.flatMap(e=>[e.source,e.target]));
    const allNodes=(raw?.nodes||[]).filter(n=>ids.has(n.id));
    const nodes=typeFilter?allNodes.filter(n=>n.type===typeFilter):allNodes;
    const nodeIds=new Set(nodes.map(n=>n.id));
    const edges=allEdges.filter(e=>nodeIds.has(e.source)&&nodeIds.has(e.target)&&(!relationFilter||e.predicate===relationFilter));
    const visibleIds=new Set(edges.flatMap(e=>[e.source,e.target]));
    return {nodes:nodes.filter(n=>visibleIds.has(n.id)),edges};
  },[raw,asOf,typeFilter,relationFilter]);
  const types = useMemo(()=>[...new Set((raw?.nodes||[]).map(n=>n.type))].sort(),[raw]);
  const relations = useMemo(()=>[...new Set((raw?.edges||[]).map(e=>e.predicate))].sort(),[raw]);
  const suggestions=useMemo(()=>search.trim()?filtered.nodes.filter(n=>(n.label+' '+n.id).toLowerCase().includes(search.trim().toLowerCase())).slice(0,7):[],[search,filtered.nodes]);
  const selectedNode=selection?.kind==='node'?filtered.nodes.find(n=>n.id===selection.id):null;
  const selectedEdge=selection?.kind==='edge'?filtered.edges.find(e=>e.id===selection.id):null;
  const neighbors=selectedNode?filtered.edges.filter(e=>e.source===selectedNode.id||e.target===selectedNode.id):[];
  const pathLabels=path?.nodes.map(id=>filtered.nodes.find(n=>n.id===id)?.label||id);
  function focusNode(id) {setSelection({kind:'node',id});setFocusId(id);setSearch('');}
  function tracePath() {setPath(buildPath(filtered.nodes,filtered.edges,pathStart,pathEnd));setPathAttempted(true);}
  return <section className="graph-page">
    <div className="graph-head"><div className="graph-title"><div className="eyebrow">EXPLORER / GRAPH STUDIO</div><h1>知识图谱 <span>Explorer</span></h1>
      <p>拖动旋转空间网络；当前图上有 {summary?.entity_relations ?? 0} 条实体关系，另有 {summary?.literal_attributes ?? 0} 条属性见断言审核。关系来源覆盖 {summary?.relation_source_docs ?? 0} / {summary?.documents ?? 0} 文档。</p></div>
      <div className="graph-head-actions"><StatusChip tone="mint"><span className="tiny-dot"/> LIVE DATA</StatusChip>
        <button className="button button--quiet" onClick={()=>onResolve()}><GitMerge size={15}/>治理与导出</button></div></div>
    <div className="graph-toolbar">
      <div className="graph-search"><Search size={18}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索实体名称或 ID…" aria-label="搜索图谱实体"/>
        {search && <button className="clear-icon" onClick={()=>setSearch('')} aria-label="清除搜索"><X size={14}/></button>}
        {suggestions.length>0 && <div className="graph-suggestions">{suggestions.map(n=><button key={n.id} onClick={()=>focusNode(n.id)}>
          <span className="node-dot" style={{background:TYPE_COLORS[n.type]||TYPE_COLORS.entity}}/><strong>{n.label}</strong><small>{TYPE_LABEL[n.type]||n.type}</small></button>)}</div>}
      </div>
      <div className="segment" role="group" aria-label="图谱视图">
        {[['all','全部'],['approved','已审核']].map(([id,label])=><button className={mode===id?'active':''} key={id} onClick={()=>setMode(id)}>{label}</button>)}
      </div>
      <div className="tool-divider"/>
      <label className="toolbar-select"><SlidersHorizontal size={15}/><select value={relationFilter} onChange={e=>setRelationFilter(e.target.value)} aria-label="关系类型过滤">
        <option value="">全部关系</option>{relations.map(r=><option key={r}>{r}</option>)}</select><ChevronDown size={13}/></label>
      <label className="toolbar-select"><select value={typeFilter} onChange={e=>setTypeFilter(e.target.value)} aria-label="实体类型过滤">
        <option value="">全部实体</option>{types.map(t=><option value={t} key={t}>{TYPE_LABEL[t]||t}</option>)}</select><ChevronDown size={13}/></label>
    </div>
    <div className="graph-stage">
      <aside className="graph-sidebar">
        <div className="sidebar-section"><div className="sidebar-section-title"><span>ENTITY INDEX</span><strong>{filtered.nodes.length}</strong></div>
          <div className="entity-list">{filtered.nodes.slice(0,100).map(n=><button key={n.id} className={selection?.id===n.id?'is-active':''} onClick={()=>focusNode(n.id)}>
            <span className="node-dot" style={{background:TYPE_COLORS[n.type]||TYPE_COLORS.entity}}/>
            <span><strong>{n.label}</strong><small>{TYPE_LABEL[n.type]||n.type}</small></span><ArrowRight size={13}/></button>)}</div></div>
        <div className="sidebar-footer"><span>DATA SOURCE</span><small>{raw?.source||'审核记录'}</small></div>
      </aside>
      <div className="graph-viewport">
        <div className="canvas-pattern"/>
        {loading ? <div className="canvas-message"><Activity className="spin" size={24}/><strong>正在加载知识网络</strong></div>
          : error ? <div className="canvas-message"><CircleHelp size={24}/><strong>图谱加载失败</strong><small>{error}</small></div>
          : filtered.nodes.length ? <GraphCanvas ref={canvasRef} nodes={filtered.nodes} edges={filtered.edges}
              selection={selection} focusId={focusId} highlighted={path} onSelect={setSelection} theme={theme}/>
          : <div className="canvas-message"><Network size={30}/><strong>当前视图没有关系</strong><small>切换审核状态或生效时点查看。</small></div>}
        <div className="canvas-overlay canvas-overlay--left"><span className="eyebrow">3D / ORBIT VIEW</span><strong>{filtered.nodes.length} 节点 <span>·</span> {filtered.edges.length} 关系</strong></div>
        <div className="canvas-controls"><button onClick={()=>canvasRef.current?.zoomIn()} title="放大"><ZoomIn size={17}/></button>
          <button onClick={()=>canvasRef.current?.zoomOut()} title="缩小"><ZoomOut size={17}/></button>
          <button onClick={()=>canvasRef.current?.fit()} title="适应画布"><Maximize2 size={17}/></button></div>
        <div className="canvas-legend">{types.slice(0,6).map(t=><span key={t}><i style={{background:TYPE_COLORS[t]||TYPE_COLORS.entity}}/>{TYPE_LABEL[t]||t}</span>)}</div>
      </div>
      <aside className={`inspector ${selection ? 'has-selection' : ''}`}>
        <div className="inspector-header"><div className="eyebrow">PROVENANCE DOSSIER</div><h2>实体检视器</h2><button className="inspector-mobile-close" onClick={()=>setSelection(null)} aria-label="关闭实体详情"><X size={15}/></button></div>
        {selectedNode ? <>
          <div className="inspector-identity"><span className="inspector-symbol" style={{color:TYPE_COLORS[selectedNode.type]||TYPE_COLORS.entity}}><Network size={24}/></span>
            <span className="status-pill status-pill--blue">{TYPE_LABEL[selectedNode.type]||selectedNode.type}</span><h3>{selectedNode.label}</h3><code>{selectedNode.id}</code></div>
          <div className="inspector-stat"><span>关联关系</span><strong>{neighbors.length}</strong></div>
          <div className="inspector-section-title">关系与证据</div>
          <div className="inspector-links">{neighbors.map(e=><button key={e.id} onClick={()=>setSelection({kind:'edge',id:e.id})}>
            <small>{e.predicate}</small><strong>{filtered.nodes.find(n=>n.id===(e.source===selectedNode.id?e.target:e.source))?.label||'关联实体'}</strong>
            <span>{sourceLabel(e)}</span></button>)}</div>
        </> : selectedEdge ? <>
          <div className="inspector-identity"><span className="inspector-symbol"><GitMerge size={24}/></span><StatusChip tone={selectedEdge.status==='approved'?'mint':'amber'}>{selectedEdge.status}</StatusChip>
            <h3>{selectedEdge.predicate}</h3><code>{selectedEdge.id}</code></div>
          <div className="relation-chain"><strong>{filtered.nodes.find(n=>n.id===selectedEdge.source)?.label}</strong><ArrowRight size={16}/><strong>{filtered.nodes.find(n=>n.id===selectedEdge.target)?.label}</strong></div>
          <div className="inspector-section-title">来源证据</div><div className="inspector-quote">{selectedEdge.source_text_quote||'没有可显示的原文引句。'}</div>
          <div className="inspector-meta"><span>文档</span><strong>{selectedEdge.source_doc_id||'—'}</strong><span>页码</span><strong>{selectedEdge.page_start||'—'}</strong>
            <span>生效</span><strong>{selectedEdge.valid_from||'未标注'}</strong><span>失效</span><strong>{selectedEdge.valid_to||'持续 / 未标注'}</strong></div>
          <button className="button button--quiet" onClick={()=>onAsk(`${filtered.nodes.find(n=>n.id===selectedEdge.source)?.label||''} ${selectedEdge.predicate} ${filtered.nodes.find(n=>n.id===selectedEdge.target)?.label||''}`)}><Search size={15}/>用此关系提问</button>
        </> : <div className="inspector-empty"><Network size={27}/><strong>选择一个节点或关系</strong><p>点击画布中的实体，查看相邻关系、原文证据与生效区间。</p></div>}
      </aside>
    </div>
    <div className="timeline-panel">
      <div className="timeline-leading"><button className="play-button" disabled={!dateBounds.length} onClick={()=>setPlaying(!playing)} title={playing?'暂停时间轴':'播放时间轴'}>{playing?<Pause size={16}/>:<Play size={16}/>}</button>
        <div><strong>TEMPORAL EVIDENCE</strong><span>{dateBounds.length?asOf:'旧断言尚未标注生效日期'}</span></div></div>
      <div className="timeline-main"><div className="timeline-track"><input type="range" min="0" max={Math.max(0,fullDates.length-1)} value={dateIndex} disabled={!dateBounds.length}
          onChange={e=>setAsOf(fullDates[Number(e.target.value)])} aria-label="历史生效时点"/>
        <div className="timeline-markers">{fullDates.slice(0,8).map(d=><span key={d}>{d}</span>)}</div></div></div>
      <label className="timeline-date">AS OF <input type="date" value={asOf} onChange={e=>setAsOf(e.target.value)}/></label>
    </div>
    <div className="path-bar"><div className="eyebrow">PATH TRACE</div><select value={pathStart} onChange={e=>setPathStart(e.target.value)} aria-label="路径起点"><option value="">选择起点</option>{filtered.nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select>
      <ArrowRight size={15}/><select value={pathEnd} onChange={e=>setPathEnd(e.target.value)} aria-label="路径终点"><option value="">选择终点</option>{filtered.nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select>
      <button className="button button--quiet" onClick={tracePath} disabled={!pathStart||!pathEnd}>追踪路径</button>
      {path && <span className="path-result">{pathLabels?.join(' → ')}</span>}
      {!path && pathStart && pathEnd && <span className="path-hint">{pathAttempted?'当前筛选条件下未找到关系路径':'选择起点与终点，查看最短关系链'}</span>}
      {path && <button className="icon-button" onClick={()=>setPath(null)} title="清除路径"><X size={15}/></button>}</div>
  </section>;
}

function CommandPalette({ close, navigate, focusGraph }) {
  const [query,setQuery]=useState('');
  const [nodes,setNodes]=useState([]);
  const inputRef=useRef(null);
  useEffect(()=>{inputRef.current?.focus();},[]);
  useEffect(()=>{
    if(!query.trim()){setNodes([]);return;}
    const timer=setTimeout(()=>api('/api/search?q='+encodeURIComponent(query)).then(d=>setNodes(d.nodes||[])).catch(()=>setNodes([])),180);
    return ()=>clearTimeout(timer);
  },[query]);
  const matches=NAV.filter(n=>(n.label+' '+n.hint).toLowerCase().includes(query.toLowerCase()));
  return <div className="palette-backdrop" onMouseDown={close}><div className="palette" role="dialog" aria-modal="true" aria-label="命令搜索" onMouseDown={e=>e.stopPropagation()}>
    <div className="palette-input"><Search size={20}/><input ref={inputRef} value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')close();if(e.key==='Enter'&&matches[0])navigate(matches[0].id);}} placeholder="搜索工作区或图谱实体…"/><kbd>ESC</kbd></div>
    <div className="palette-results"><div className="eyebrow">WORKSPACES</div>{matches.map(({id,label,hint,icon:Icon})=><button key={id} onClick={()=>navigate(id)}><Icon size={17}/><strong>{label}</strong><small>{hint}</small><ArrowRight size={14}/></button>)}
      {nodes.length>0 && <><div className="eyebrow">GRAPH ENTITIES</div>{nodes.map(n=><button key={n.id} onClick={()=>focusGraph(n.id)}><span className="node-dot" style={{background:TYPE_COLORS[n.type]||TYPE_COLORS.entity}}/><strong>{n.label}</strong><small>{TYPE_LABEL[n.type]||n.type}</small><ArrowRight size={14}/></button>)}</>}</div>
    <div className="palette-foot"><span>ENTER 打开</span><span>⌘ K 快速唤起</span></div>
  </div></div>;
}

export default function App() {
  const [page,setPage]=useState(stateFromHash);
  const [summary,setSummary]=useState(null);
  const [graph,setGraph]=useState(null);
  const [graphError,setGraphError]=useState('');
  const [graphLoading,setGraphLoading]=useState(false);
  const [graphRefresh,setGraphRefresh]=useState(0);
  const [mode,setMode]=useState('all');
  const [asOf,setAsOf]=useState(today);
  const [paletteOpen,setPaletteOpen]=useState(false);
  const [seedQuestion,setSeedQuestion]=useState('');
  const [graphFocus,setGraphFocus]=useState('');
  const [theme,setTheme]=useState(()=>{
    try { return localStorage.getItem('alpha-theme') || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'); }
    catch { return 'dark'; }
  });
  useEffect(()=>{
    document.documentElement.dataset.theme=theme;
    try { localStorage.setItem('alpha-theme',theme); } catch { /* Storage can be disabled. */ }
  },[theme]);
  useEffect(()=>{
    const refresh=()=>api('/api/summary').then(setSummary).catch(()=>{});
    refresh(); const timer=setInterval(refresh,30000);
    return ()=>clearInterval(timer);
  },[graphRefresh]);
  useEffect(()=>{
    if(page!=='graph')return;
    let active=true;setGraphLoading(true);setGraphError('');
    api('/api/graph?mode='+mode).then(data=>{if(active)setGraph(data);}).catch(e=>{if(active)setGraphError(e.message);})
      .finally(()=>{if(active)setGraphLoading(false);});
    return ()=>{active=false;};
  },[page,mode,graphRefresh]);
  useEffect(()=>{
    const onHash=()=>setPage(stateFromHash());
    const onKey=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setPaletteOpen(v=>!v);}
      if(e.key==='Escape')setPaletteOpen(false);};
    window.addEventListener('hashchange',onHash);window.addEventListener('keydown',onKey);
    return ()=>{window.removeEventListener('hashchange',onHash);window.removeEventListener('keydown',onKey);};
  },[]);
  const navigate=useCallback(id=>{window.location.hash=id;setPage(id);setPaletteOpen(false);},[]);
  const askFromGraph=useCallback(question=>{setSeedQuestion(question);navigate('ask');},[navigate]);
  const focusGraph=useCallback(id=>{setGraphFocus(id);navigate('graph');},[navigate]);
  return <div className="app-shell">
    <aside className="app-rail"><button className="brand" onClick={()=>navigate('overview')} title="Alpha 首页"><span className="brand-glyph"><FlaskConical size={21}/></span><span>Alpha</span></button>
      <div className="rail-section-label">WORKSPACE</div><nav aria-label="主导航">{NAV.map(({id,label,hint,icon:Icon})=><button key={id} className={`rail-link ${page===id?'is-active':''}`} onClick={()=>navigate(id)} title={hint}>
        <Icon size={18}/><span>{label}</span>{page===id&&<i/>}</button>)}</nav>
      <div className="rail-bottom"><div className="rail-status"><span className="pulse-dot"/><div><strong>KNOWLEDGE ENGINE</strong><small>{summary?'连接正常':'正在连接'}</small></div></div>
        <div className="rail-version">CHEMICAL SAFETY / v1.0</div></div>
    </aside>
    <div className="app-main"><header className="app-topbar"><div className="breadcrumb"><span>WORKSPACE</span><ArrowRight size={13}/><strong>{NAV.find(n=>n.id===page)?.label||'总览'}</strong></div>
      <button className="command-trigger" onClick={()=>setPaletteOpen(true)}><Search size={16}/><span>搜索实体、来源或工作区</span><kbd>⌘ K</kbd></button>
      <div className="topbar-right"><div className="theme-switch" role="group" aria-label="页面外观">
        <button type="button" className={theme==='light'?'active':''} aria-pressed={theme==='light'} onClick={()=>setTheme('light')}><Sun size={14}/> Light</button>
        <button type="button" className={theme==='dark'?'active':''} aria-pressed={theme==='dark'} onClick={()=>setTheme('dark')}><Moon size={14}/> Dark</button>
      </div><span className="topbar-date">{new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'short',day:'numeric'})}</span><div className="topbar-avatar">CA</div></div>
    </header>
      {page==='overview'&&<Welcome summary={summary} onNavigate={navigate}/>}
      {page==='graph'&&<GraphDesk raw={graph} loading={graphLoading} error={graphError} mode={mode} setMode={setMode} asOf={asOf} setAsOf={setAsOf} onAsk={askFromGraph} onResolve={()=>navigate('resolve')} externalFocusId={graphFocus} theme={theme} summary={summary}/>}
      {page==='ask'&&<AskWorkspace asOf={asOf} setAsOf={setAsOf} seedQuestion={seedQuestion}/>}
      {page==='review'&&<ReviewWorkspace summary={summary} onGraphRefresh={()=>setGraphRefresh(n=>n+1)}/>}
      {page==='resolve'&&<ResolutionWorkspace asOf={asOf} onGraphRefresh={()=>setGraphRefresh(n=>n+1)}/>}
      {page==='library'&&<LibraryWorkspace/>}
      {page==='wiki'&&<WikiWorkspace/>}
    </div>
    {paletteOpen&&<CommandPalette close={()=>setPaletteOpen(false)} navigate={navigate} focusGraph={focusGraph}/>}
  </div>;
}




