import {Suspense,lazy,useEffect,useMemo,useRef,useState} from 'react';
import {Activity,ArrowRight,ChevronDown,CircleHelp,GitMerge,Maximize2,Network,Pause,Play,Search,SlidersHorizontal,X,ZoomIn,ZoomOut} from 'lucide-react';
import {api,sourceLabel,today,validAt} from './api';
import {TYPE_COLORS} from './graph-theme';
import {typeLabels as TYPE_LABEL,relationLabels} from './theme/tokens';
import {useUI,EvidenceAdapter} from './components/WorkspaceUI';
import {PageQuote} from './components/PageQuote';
import {Autocomplete,Button,TextField,ToggleButton,ToggleButtonGroup} from '@mui/material';
const GraphCanvas=lazy(()=>import('./GraphCanvas.jsx'));
function StatusChip({children,tone='blue'}){return <span className={'status-pill status-pill--'+tone}>{children}</span>}
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

export default function GraphDesk({ raw, loading, error, mode, setMode, asOf, setAsOf, onAsk, onResolve, externalFocusId, theme, summary }) {
  const ui=useUI();
  const [listPage,setListPage]=useState(0),[display,setDisplay]=useState(()=>window.matchMedia('(max-width:767px)').matches?'list':'3d');
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
  useEffect(()=>{setPath(null);setPathAttempted(false);setListPage(0);if(selection&&!((selection.kind==='node'?filtered.nodes:filtered.edges).some(x=>x.id===selection.id)))setSelection(null)},[asOf,typeFilter,relationFilter,mode]);
  function focusNode(id) {setSelection({kind:'node',id});setFocusId(id);setSearch('');}
  function tracePath() {setPath(buildPath(filtered.nodes,filtered.edges,pathStart,pathEnd));setPathAttempted(true);}
  return <section className="graph-page">
    <div className="graph-head"><div className="graph-title"><div className="eyebrow">KNOWLEDGE GRAPH / TRACEABLE EVIDENCE</div><h1>图谱探索 <span>Explorer</span></h1>
      <PageQuote/><p>已通过审核的实体关系 {summary?.entity_relations ?? '—'} 条，属性 {summary?.literal_attributes ?? '—'} 条；来源文档 {summary?.relation_source_docs ?? '—'} 份。</p></div>
      <div className="graph-head-actions"><StatusChip tone={mode==='all'?'amber':'mint'}>{mode==='all'?'包含待审候选':'已审核知识'}</StatusChip>
        <button className="button button--quiet" onClick={()=>onResolve()}><GitMerge size={15}/>治理与导出</button></div></div>
    <div className="graph-toolbar">
      <Autocomplete size="small" options={filtered.nodes} getOptionLabel={n=>n.label||n.id} isOptionEqualToValue={(a,b)=>a.id===b.id} getOptionKey={n=>n.id} value={null} inputValue={search} onInputChange={(_,v)=>setSearch(v)} onChange={(_,n)=>n&&focusNode(n.id)} noOptionsText="当前筛选下没有匹配实体" sx={{width:{xs:'100%',sm:300}}} renderInput={params=><TextField {...params} label="搜索图谱实体"/>}/>
      <div className="segment" role="group" aria-label="图谱视图">
        {[['approved','已审核'],['all','包含待审']].map(([id,label])=><button className={mode===id?'active':''} key={id} onClick={()=>setMode(id)}>{label}</button>)}
      </div>
      <div className="tool-divider"/>
      <label className="toolbar-select"><SlidersHorizontal size={15}/><select value={relationFilter} onChange={e=>setRelationFilter(e.target.value)} aria-label="关系类型过滤">
        <option value="">全部关系</option>{relations.map(r=><option value={r} key={r}>{relationLabels[r]||r}</option>)}</select><ChevronDown size={13}/></label>
      <label className="toolbar-select"><select value={typeFilter} onChange={e=>setTypeFilter(e.target.value)} aria-label="实体类型过滤">
        <option value="">全部实体</option>{types.map(t=><option value={t} key={t}>{TYPE_LABEL[t]||t}</option>)}</select><ChevronDown size={13}/></label>
      <ToggleButtonGroup size="small" exclusive value={display} onChange={(_,v)=>v&&setDisplay(v)} aria-label="图谱显示模式"><ToggleButton value="3d">三维图</ToggleButton><ToggleButton value="list">关系列表</ToggleButton></ToggleButtonGroup>
    </div>
    {display==='list'?<div className="ui-graph-list" aria-label="关系列表">{loading?<p role="status">正在读取关系…</p>:error?<p role="alert">{error}</p>:filtered.edges.length?filtered.edges.map(e=><button key={e.id} onClick={()=>ui.openEvidence(EvidenceAdapter(e,{reviewStatus:e.status,reviewUrl:'/?assertion_id='+encodeURIComponent(e.id)+'#review'}))}><strong>{filtered.nodes.find(n=>n.id===e.source)?.label||e.source}</strong><span>{relationLabels[e.predicate]||e.predicate}</span><strong>{filtered.nodes.find(n=>n.id===e.target)?.label||e.target}</strong><small>{sourceLabel(e)} · 核对证据</small></button>):<p>当前筛选下没有实体关系，可调整类型或生效时点。</p>}</div>:<div className="graph-stage">
      <aside className="graph-sidebar">
        <div className="sidebar-section"><div className="sidebar-section-title"><span>ENTITY INDEX</span><strong>{filtered.nodes.length}</strong></div>
          <div className="entity-list">{filtered.nodes.slice(listPage*50,(listPage+1)*50).map(n=><button key={n.id} className={selection?.id===n.id?'is-active':''} onClick={()=>focusNode(n.id)}>
            <span className="node-dot" style={{background:TYPE_COLORS[n.type]||TYPE_COLORS.entity}}/>
            <span><strong>{n.label}</strong><small>{TYPE_LABEL[n.type]||n.type}</small></span><ArrowRight size={13}/></button>)}</div></div>
        <div className="ui-graph-page"><button aria-label="实体上一页" disabled={!listPage} onClick={()=>setListPage(x=>x-1)}>上一页</button><span>{filtered.nodes.length?listPage*50+1:0}–{Math.min((listPage+1)*50,filtered.nodes.length)} / {filtered.nodes.length}</span><button aria-label="实体下一页" disabled={(listPage+1)*50>=filtered.nodes.length} onClick={()=>setListPage(x=>x+1)}>下一页</button></div>
      </aside>
      <div className="graph-viewport">
        <div className="canvas-pattern"/>
        {loading ? <div className="canvas-message"><Activity className="spin" size={24}/><strong>正在加载知识网络</strong></div>
          : error ? <div className="canvas-message"><CircleHelp size={24}/><strong>图谱加载失败</strong><small>{error}</small></div>
          : filtered.nodes.length ? <Suspense fallback={<div className="canvas-message">正在加载图谱画布…</div>}><GraphCanvas ref={canvasRef} nodes={filtered.nodes} edges={filtered.edges}
              selection={selection} focusId={focusId} highlighted={path} onSelect={setSelection} theme={theme}/></Suspense>
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
            <small>{relationLabels[e.predicate]||e.predicate}</small><strong>{filtered.nodes.find(n=>n.id===(e.source===selectedNode.id?e.target:e.source))?.label||'关联实体'}</strong>
            <span>{sourceLabel(e)}</span></button>)}</div>
        </> : selectedEdge ? <>
          <div className="inspector-identity"><span className="inspector-symbol"><GitMerge size={24}/></span><StatusChip tone={selectedEdge.status==='approved'?'mint':'amber'}>{selectedEdge.status}</StatusChip>
            <h3>{relationLabels[selectedEdge.predicate]||selectedEdge.predicate}</h3><code>{selectedEdge.id}</code></div>
          <div className="relation-chain"><strong>{filtered.nodes.find(n=>n.id===selectedEdge.source)?.label}</strong><ArrowRight size={16}/><strong>{filtered.nodes.find(n=>n.id===selectedEdge.target)?.label}</strong></div>
          <div className="inspector-section-title">来源证据</div><div className="inspector-quote">{selectedEdge.source_text_quote||'没有可显示的原文引句。'}</div>
          <div className="inspector-meta"><span>文档</span><strong>{selectedEdge.source_doc_id||'—'}</strong><span>页码</span><strong>{selectedEdge.page_start||'—'}</strong>
            <span>生效</span><strong>{selectedEdge.valid_from||'未标注'}</strong><span>失效</span><strong>{selectedEdge.valid_to||'持续 / 未标注'}</strong></div>
          <Button onClick={()=>ui.openEvidence(EvidenceAdapter(selectedEdge,{reviewStatus:selectedEdge.status,reviewUrl:'/?assertion_id='+encodeURIComponent(selectedEdge.id)+'#review'}))}>核对证据与审核</Button>
          <button className="button button--quiet" onClick={()=>onAsk(`${filtered.nodes.find(n=>n.id===selectedEdge.source)?.label||''} ${selectedEdge.predicate} ${filtered.nodes.find(n=>n.id===selectedEdge.target)?.label||''}`)}><Search size={15}/>用此关系提问</button>
        </> : <div className="inspector-empty"><Network size={27}/><strong>选择一个节点或关系</strong><p>点击画布中的实体，查看相邻关系、原文证据与生效区间。</p></div>}
      </aside>
    </div>}
    <details className="ui-graph-advanced"><summary>高级分析：生效时间轴与关联路径</summary><div className="timeline-panel">
      <div className="timeline-leading"><button className="play-button" disabled={!dateBounds.length} onClick={()=>setPlaying(!playing)} title={playing?'暂停时间轴':'播放时间轴'}>{playing?<Pause size={16}/>:<Play size={16}/>}</button>
        <div><strong>TEMPORAL EVIDENCE</strong><span>{dateBounds.length?asOf:'当前关系尚未标注生效日期'}</span></div></div>
      <div className="timeline-main"><div className="timeline-track"><input type="range" min="0" max={Math.max(0,fullDates.length-1)} value={dateIndex} disabled={!dateBounds.length}
          onChange={e=>setAsOf(fullDates[Number(e.target.value)])} aria-label="生效时点"/>
        <div className="timeline-markers">{fullDates.slice(0,8).map(d=><span key={d}>{d}</span>)}</div></div></div>
      <label className="timeline-date">AS OF <input type="date" value={asOf} onChange={e=>setAsOf(e.target.value)}/></label>
    </div>
    <div className="path-bar"><div className="eyebrow">PATH TRACE</div><select value={pathStart} onChange={e=>setPathStart(e.target.value)} aria-label="路径起点"><option value="">选择起点</option>{filtered.nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select>
      <ArrowRight size={15}/><select value={pathEnd} onChange={e=>setPathEnd(e.target.value)} aria-label="路径终点"><option value="">选择终点</option>{filtered.nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select>
      <button className="button button--quiet" onClick={tracePath} disabled={!pathStart||!pathEnd}>查找关联路径</button>
      {path && <span className="path-result">{pathLabels?.join(' → ')}</span>}
      {!path && pathStart && pathEnd && <span className="path-hint">{pathAttempted?'当前筛选条件下未找到关系路径':'选择起点与终点，查看最短关系链'}</span>}
      {path && <button className="icon-button" onClick={()=>setPath(null)} title="清除路径"><X size={15}/></button>}</div><p className="subtle" style={{padding:'0 24px'}}>关联路径按相邻实体查找，不代表因果关系或有向推理。</p></details>
  </section>;
}
