import {useEffect,useRef,useState} from 'react';
import {ArrowDown,ArrowUp,CalendarDays,Check,ChevronDown,ChevronLeft,ChevronRight,Columns3,Copy,Database,Download,FileText,KeyRound,Maximize2,Minimize2,RefreshCw,Search,X} from 'lucide-react';
import {api} from './api';
import './dataset-catalog.css';

const n=v=>Number(v??0).toLocaleString('zh-CN',{maximumFractionDigits:2});
const pct=(v,total)=>!total?'—':v>0&&100*v/total<.01?'<0.01%':n(100*v/total)+'%';
const bytes=v=>v===null||v===undefined?'索引说明视图':v<1024?n(v)+' B':v<1048576?n(v/1024)+' KB':n(v/1048576)+' MB';
const cell=v=>v===null||v===undefined?'':typeof v==='object'?JSON.stringify(v,null,2):String(v);
const symbol=p=>p.type==='identifier'?<KeyRound size={13}/>:p.type==='date'?<CalendarDays size={13}/>:p.type==='number'?<span>#</span>:<span>Aa</span>;

function Distribution({p,small=false}){
 if(p.type==='identifier')return <div className="file-unique"><strong>{n(p.unique)}</strong><span>个不同标识</span></div>;
 if(p.histogram?.length){
  const max=Math.max(1,...p.histogram.map(b=>b.count)),bars=p.histogram,w=300,h=small?62:128;
  return <div className="file-histogram"><svg viewBox={'0 0 '+w+' '+h} role="img" aria-label={p.label+'：'+p.distribution_label}>
   {bars.map((b,i)=><rect key={i} x={i*w/bars.length+1} y={h-2-(h-4)*b.count/max} width={Math.max(1,w/bars.length-2)} height={(h-4)*b.count/max}><title>{n(b.start)}–{n(b.end)}：{n(b.count)} 条</title></rect>)}
   <line x1="0" y1={h-1} x2={w} y2={h-1}/></svg><div><span>{n(bars[0].start)}</span><span>{n(bars.at(-1).end)}{p.type==='number'?'':' 字符'}</span></div>
  {!small&&<small>{p.distribution_label}</small>}</div>;
 }
 if(p.type==='date'&&p.most_common?.length){
  const bars=p.most_common,max=Math.max(1,...bars.map(b=>b.count)),h=small?62:128;
  return <div className="file-histogram"><svg viewBox={'0 0 300 '+h} role="img" aria-label={p.label+'按月份分布'}>{bars.map((b,i)=><rect key={b.value} x={i*300/bars.length+1} y={h-(h-3)*b.count/max} width={Math.max(.5,300/bars.length-2)} height={(h-3)*b.count/max}><title>{b.value}：{n(b.count)} 条</title></rect>)}</svg><div><span>{bars[0].value}</span><span>{bars.at(-1).value}</span></div></div>;
 }
 if(p.most_common?.length)return <div className="file-categories">{p.most_common.slice(0,small?3:5).map((v,i)=><div key={i}><span title={cell(v.value)}>{cell(v.value)}</span><strong>{pct(v.count,p.total)}</strong><i style={{width:(p.total?100*v.count/p.total:0)+'%'}}/></div>)}</div>;
 return <div className="file-unique"><strong>{n(p.unique)}</strong><span>{p.valid?'个不同值':'暂无有效值'}</span></div>;
}

function Quality({p}){
 return <div className="file-quality">
  <div className="file-quality-bar" aria-label={'有效 '+n(p.valid)+'，类型不符 '+n(p.mismatched)+'，缺失 '+n(p.missing)}>
   <i className="valid" style={{width:(p.total?100*p.valid/p.total:0)+'%'}}/><i className="mismatch" style={{width:(p.total?100*p.mismatched/p.total:0)+'%'}}/><i className="missing" style={{width:(p.total?100*p.missing/p.total:0)+'%'}}/>
  </div><dl>{[['有效','valid',p.valid],['类型不符','mismatch',p.mismatched],['缺失','missing',p.missing]].map(([label,cls,count])=><div key={cls}><dt>{label}<i className={cls}/></dt><dd>{n(count)}</dd><dd>{pct(count,p.total)}</dd></div>)}</dl>
  {p.statistics&&<dl className="file-numeric"><div><dt>均值</dt><dd>{n(p.statistics.mean)}</dd></div><div><dt>标准差（总体）</dt><dd>{n(p.statistics.std)}</dd></div>{p.statistics.quantiles.map((v,i)=><div key={i}><dt>{['最小值','25% 分位数','中位数','75% 分位数','最大值'][i]}</dt><dd>{n(v)}</dd></div>)}</dl>}
  {!p.statistics&&<dl className="file-numeric"><div><dt>不同值数量</dt><dd>{n(p.unique)}</dd></div>{p.most_common_value!==undefined&&<div><dt>最高频值</dt><dd title={p.most_common_value}>{p.most_common_value}<small>{pct(p.most_common_count,p.total)}</small></dd></div>}</dl>}
 </div>;
}

function CellDialog({value,name,onClose}){
 const ref=useRef(),[copied,setCopied]=useState(false);
 useEffect(()=>{const previous=document.activeElement;ref.current?.querySelector('button')?.focus();function key(e){if(e.key==='Escape')onClose();if(e.key==='Tab'){const els=ref.current.querySelectorAll('button');const a=els[0],b=els[els.length-1];if(e.shiftKey&&document.activeElement===a){e.preventDefault();b.focus()}else if(!e.shiftKey&&document.activeElement===b){e.preventDefault();a.focus()}}}document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);previous?.focus()}},[]);
 return <div className="file-cell-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className="file-cell-dialog" role="dialog" aria-modal="true" aria-label="完整样例值" ref={ref}><header><div><strong>{name}</strong><small>当前样例中的完整字段值</small></div><button className="dash-icon" onClick={onClose} aria-label="关闭样例"><X size={18}/></button></header><pre>{cell(value)||'此字段未提供值'}</pre><footer><button className="dash-button" onClick={async()=>{try{await navigator.clipboard.writeText(cell(value));setCopied(true)}catch{setCopied(false)}}}>{copied?<Check size={14}/>:<Copy size={14}/>}复制字段值</button><span>{copied?'已复制':'可选择文本复制'}</span></footer></div></div>;
}

export default function DatasetCatalog({snapshot,refresh}){
 const [catalog,setCatalog]=useState(null),[selected,setSelected]=useState('main_chunks'),[data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [view,setView]=useState('detail'),[fields,setFields]=useState([]),[fieldMenu,setFieldMenu]=useState(false),[search,setSearch]=useState(''),[offset,setOffset]=useState(0),[sort,setSort]=useState(null),[direction,setDirection]=useState('asc');
 const [reload,setReload]=useState(0),[valueDialog,setValueDialog]=useState(null),[expanded,setExpanded]=useState(false),[notice,setNotice]=useState('');
 const viewer=useRef(),fieldPopover=useRef();
 useEffect(()=>{const c=new AbortController();setError('');setCatalog(null);api('/api/dashboard/files',{signal:c.signal}).then(setCatalog).catch(e=>e.name!=='AbortError'&&setError(e.message));return()=>c.abort()},[snapshot,refresh,reload]);
 useEffect(()=>{if(!catalog)return;const c=new AbortController();setBusy(true);setError('');
  const q=new URLSearchParams({catalog_revision:catalog.catalog_revision,offset:String(offset),size:'20'});if(sort){q.set('sort',sort);q.set('direction',direction)}
  api('/api/dashboard/files/'+selected+'?'+q,{signal:c.signal}).then(d=>{setData(d);setFields(prev=>prev.length?prev:(()=>{const keys=d.columns.slice(0,8).map(v=>v.name);for(const k of ['text','sample_text'])if(d.columns.some(v=>v.name===k)&&!keys.includes(k))keys.push(k);return keys})())}).catch(e=>e.name!=='AbortError'&&setError(e.message)).finally(()=>!c.signal.aborted&&setBusy(false));return()=>c.abort();
 },[catalog?.catalog_revision,selected,offset,sort,direction,reload]);
 useEffect(()=>{function full(){setExpanded(document.fullscreenElement===viewer.current)}document.addEventListener('fullscreenchange',full);return()=>document.removeEventListener('fullscreenchange',full)},[]);
 useEffect(()=>{if(!fieldMenu)return;function outside(e){if(!fieldPopover.current?.contains(e.target))setFieldMenu(false)}function escape(e){if(e.key==='Escape')setFieldMenu(false)}document.addEventListener('mousedown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('mousedown',outside);document.removeEventListener('keydown',escape)}},[fieldMenu]);
 function choose(key){setSelected(key);setData(null);setOffset(0);setSort(null);setDirection('asc');setFields([]);setFieldMenu(false);setValueDialog(null)}
 function toggleField(key){setFields(prev=>prev.includes(key)?prev.length>1?prev.filter(v=>v!==key):prev:[...prev,key])}
 function sorting(key){setOffset(0);setDirection(sort===key&&direction==='asc'?'desc':'asc');setSort(key)}
 function download(){
  if(!data)return;
  const payload={file:data.file.name,catalog_revision:data.catalog_revision,snapshot_id:data.snapshot_id,total_rows:data.total,offset:data.offset,sample_rows:data.rows,description:'真实记录的当前页样例，保留完整字段值；不是完整数据文件。'};
  const blob=new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=selected+'-sample-'+(offset+1)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
 async function maximize(){try{if(expanded)await document.exitFullscreen();else await viewer.current.requestFullscreen()}catch{setNotice('此窗口无法全屏，请使用图表区域横向滚动查看全部字段。')}}
 const columns=data?.columns.filter(p=>fields.includes(p.name))||[];
 const visible=catalog?.files.filter(d=>(d.name+' '+d.label+' '+d.format).toLowerCase().includes(search.toLowerCase()))||[];
 const file=data?.file||catalog?.files.find(d=>d.id===selected);
 return <div className="file-catalog">
  <aside className="file-catalog-sidebar"><h2><Database size={18}/>文件与资料</h2><label className="file-search"><Search size={15}/><input aria-label="搜索文件类别" placeholder="搜索名称或格式" value={search} onChange={e=>setSearch(e.target.value)}/></label>
   {!catalog&&!error&&<p className="file-empty">正在读取文件目录…</p>}
   {['可分析的数据文件','原始资料类别'].map(group=><div className="file-list-group" key={group}><h3>{group}</h3>{visible.filter(d=>d.group===group).map(d=><button key={d.id} className={selected===d.id?'selected':''} onClick={()=>choose(d.id)} aria-pressed={selected===d.id} data-file-id={d.id}><FileText size={16}/><span><strong>{d.label}</strong><small>{d.format}{d.rows!==null?' · '+n(d.rows)+' 条':''}{!d.available?' · 暂无资料':''}</small></span><ChevronRight size={14}/></button>)}</div>)}
   {catalog&&<p className="file-sidebar-note">{catalog.files.length} 类文件 / 资料<br/>实际字段统计与真实内容样例</p>}
  </aside>
  <section className="file-catalog-viewer" ref={viewer} aria-busy={busy}>
   <header className="file-viewer-head"><div><h2>{file?.name||'文件预览'} <span>({bytes(file?.bytes)})</span></h2><p>{file?.label} · {file?.grain}</p></div><div><button className="dash-icon" aria-label="下载当前页样例" title="下载当前页真实样例 JSON，保留完整字段；不是全文件" disabled={!data||busy} onClick={download}><Download size={17}/></button><button className="dash-icon" aria-label={expanded?'退出预览全屏':'全屏查看文件预览'} title="全屏查看" onClick={maximize}><Maximize2 size={17}/></button></div></header>
   <div className="file-viewer-tabs"><div role="tablist" aria-label="文件预览方式" onKeyDown={e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const keys=['detail','compact','column'],i=keys.indexOf(view),j=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;setView(keys[j]);e.currentTarget.querySelectorAll('[role=tab]')[j].focus()}}>
    {[['detail','详细'],['compact','紧凑'],['column','按列']].map(([k,label])=><button key={k} role="tab" aria-selected={view===k} className={view===k?'active':''} onClick={()=>setView(k)}>{label}</button>)}</div>
    <div className="file-field-chooser" ref={fieldPopover}><button className="file-choose-button" disabled={!data} aria-expanded={fieldMenu} onClick={()=>setFieldMenu(!fieldMenu)}><Columns3 size={14}/>展示 {columns.length} / {data?.columns.length||0} 列<ChevronDown size={14}/></button>
     {fieldMenu&&<div className="file-field-popover"><header><strong>选择展示字段</strong><button onClick={()=>setFields(data.columns.map(v=>v.name))}>全部展示</button></header>{data.columns.map(p=><label key={p.name}><input type="checkbox" checked={fields.includes(p.name)} disabled={fields.length===1&&fields.includes(p.name)} onChange={()=>toggleField(p.name)}/><span>{p.label}<code>{p.name}</code></span></label>)}</div>}
    </div>
   </div>
   {error&&<div className="file-error" role="alert"><p>{error}</p><button className="dash-button" onClick={()=>{setData(null);setOffset(0);setReload(v=>v+1)}}><RefreshCw size={14}/>重新读取文件快照</button></div>}
   {notice&&<p className="file-notice" role="status">{notice}</p>}
   {busy&&<div className="file-loading" role="status">正在读取真实记录与完整字段统计…</div>}
   {!busy&&!data&&!error&&<div className="file-empty">选择一类文件，查看其用途、字段和内容样例。</div>}
   {data&&!error&&<div className={busy?'file-result is-updating':'file-result'}>
    {view==='detail'&&<div className="file-about"><h3>关于这类文件</h3><p>{data.file.about}</p><dl><div><dt>实际结构</dt><dd>{data.file.format} · {data.file.grain}</dd></div><div><dt>当前记录</dt><dd>{n(data.total)} 条 / {data.columns.length} 个字段</dd></div>{data.file.path&&<div><dt>来源文件</dt><dd><code>{data.file.path}</code></dd></div>}</dl><p className="file-about-note">{data.file.note}</p>
     {data.file.doc_type&&data.rows[0]&&<div className="file-document-preview"><header><FileText size={18}/><strong>{data.rows[0].title}</strong><span>原文片段样例 · {data.rows[0].sample_page?'已有页码 '+data.rows[0].sample_page:'未标注页码'}</span></header><pre>{cell(data.rows[0].sample_text).slice(0,1800)||'此记录未提供原文片段'}</pre><small>展示索引中保留的文本，原文件的版式、图片与表格未在此重排。</small></div>}
     {data.preview_json&&<details className="file-structure"><summary>查看{data.file.doc_type?'索引记录':data.file.format==='JSONL'?'一行 JSON 对象':'原始字段'}结构样例</summary><pre>{data.preview_json}</pre><small>结构展示最多 4,500 字符；下方点击单元格可查看完整字段值。</small></details>}
    </div>}
    {view==='column'?<div className="file-column-view">{columns.map(p=><article className="file-column-profile" key={p.name}><header><div>{symbol(p)}<h3>{p.label} <code>{p.name}</code></h3><span>{p.type_label}</span></div><p>{p.description}</p></header><div className="file-column-grid"><div><Distribution p={p}/><small>{p.profile_basis} · {n(p.total)} 条</small></div><Quality p={p}/></div></article>)}</div>:<div className={'file-table-scroll '+(view==='compact'?'is-compact':'')} tabIndex={0} aria-label="真实样例表格，可横向滚动"><table className="file-preview-table"><thead><tr>{columns.map(p=><th key={p.name} aria-sort={sort===p.name?direction==='asc'?'ascending':'descending':'none'}><button onClick={()=>sorting(p.name)} aria-label={'按 '+p.name+' 排序'}>{symbol(p)}<span>{p.label}<code>{p.name}</code></span>{sort===p.name?direction==='asc'?<ArrowUp size={13}/>:<ArrowDown size={13}/>:<ArrowDown size={12}/>}</button>{view==='detail'&&<p>{p.description}</p>}</th>)}</tr>
     {view==='detail'&&<tr className="file-distribution-row">{columns.map(p=><td key={p.name}><Distribution p={p} small/><small>{p.type_label} · 缺失 {pct(p.missing,p.total)}</small></td>)}</tr>}
     </thead><tbody>{data.rows.map((row,i)=><tr key={offset+i}>{columns.map(p=><td key={p.name}>{cell(row[p.name])?<button className="file-cell" onClick={()=>setValueDialog({name:p.label+' / '+p.name,value:row[p.name]})} title="点击查看完整字段值"><span>{cell(row[p.name])}</span></button>:<span className="file-null">未提供</span>}</td>)}</tr>)}</tbody></table>{!data.rows.length&&<div className="file-empty">这类文件暂时没有可预览记录。</div>}</div>}
    <footer className="file-preview-footer"><div><strong>{view==='column'?'字段统计：全部 '+n(data.total)+' 条记录':'真实样例 '+n(data.rows.length?offset+1:0)+'–'+n(Math.min(offset+data.rows.length,data.total))+' / '+n(data.total)+' 条'}</strong><small>{view==='column'?data.invalid_type_rule:'分布统计覆盖全部记录，表格是当前页样例；点击单元格查看完整值。'}</small></div>{view!=='column'&&<div><button className="dash-icon" aria-label="上一页样例" disabled={!offset||busy} onClick={()=>setOffset(Math.max(0,offset-20))}><ChevronLeft size={17}/></button><span>第 {Math.floor(offset/20)+1} / {Math.max(1,Math.ceil(data.total/20))} 页</span><button className="dash-icon" aria-label="下一页样例" disabled={offset+20>=data.total||busy} onClick={()=>setOffset(offset+20)}><ChevronRight size={17}/></button></div>}</footer>
    <div className="file-profile-footnote">有效表示满足字段结构与类型规则，不代表业务事实已核实。不同值数量按完整值统计；空字符串、空对象 / 数组及未提供值计为缺失。<span>文件快照 {data.catalog_revision}</span></div>
   </div>}
   {valueDialog&&<CellDialog {...valueDialog} onClose={()=>setValueDialog(null)}/>}
  </section>
 </div>;
}
