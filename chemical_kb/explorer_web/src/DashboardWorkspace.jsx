import DatasetCatalog from './DatasetCatalog.jsx';
import {useEffect,useMemo,useRef,useState} from 'react';
import * as echarts from 'echarts/core';
import {BarChart,LineChart,TreemapChart,ScatterChart,HeatmapChart,SankeyChart,GraphChart,BoxplotChart} from 'echarts/charts';
import {GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,VisualMapComponent,AriaComponent} from 'echarts/components';
import {SVGRenderer} from 'echarts/renderers';
import {ArrowDown,ArrowUp,BarChart3,BookOpen,Check,ChevronDown,ChevronLeft,ChevronRight,Database,Download,ExternalLink,FileText,Filter,GripVertical,Info,LayoutGrid,LineChart as LineIcon,Maximize2,MoreHorizontal,Network,Plus,RefreshCw,Save,Search,Settings2,Share2,SlidersHorizontal,Table2,Undo2,X} from 'lucide-react';
import {api} from './api';
import './dashboard.css';

echarts.use([BarChart,LineChart,TreemapChart,ScatterChart,HeatmapChart,SankeyChart,GraphChart,BoxplotChart,GridComponent,TooltipComponent,LegendComponent,DataZoomComponent,VisualMapComponent,AriaComponent,SVGRenderer]);
const LABEL={type:'资料类型',source:'来源标签',collection:'资料范围',chemical:'化学品名称提及',status:'记录状态',country:'来源国家',month:'月份',year:'年份',subject_type:'主体类型',predicate:'关系类型',object_type:'客体类型',page_type:'条目类型'};
const COLORS=['#2f6699','#268e8c','#c19339','#7188a8','#9c7187','#4e876d','#b37247','#859c43'];
const fmt=n=>Number(n??0).toLocaleString('zh-CN',{maximumFractionDigits:1});
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stamp=s=>s?new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未提供';
const DEFAULT={dataset:'documents',dimensions:['type','collection'],metric:'count',filters:[],unknown:'include',time_axis:'published',q:'',from:'',to:''};
const VIEW_TYPES=[
 ['bar','排名比较','一个或两个类别与数值'],['grouped','分组对比','两个类别与数值'],['treemap','层级构成','文种与来源的互斥层级'],
 ['line','时间趋势','已知日期与月份'],['heatmap','关联矩阵','两个离散维度'],['scatter','记录散点','文档片段数与字符数'],
 ['box','数量分布','单记录数值与分组'],['histogram','直方分布','单记录数值'],['sankey','资料路径','范围 / 国家→文种→来源'],
 ['stacked','来源构成','来源内文种构成'],['network','知识网络','当前已接受的实体关系'],['pivot','多维透视','可展开和核对的聚合表'],
];
const INITIAL_ORDER=['timeline','structure','ranking','matrix','network','composition'];
function stored(key,fallback){try{return JSON.parse(localStorage.getItem(key)||'null')??fallback}catch{return fallback}}
function initialQuery(){
 try{
  const encoded=new URLSearchParams(location.search).get('dashboard');
  const candidate=encoded&&encoded.length<12000?JSON.parse(encoded):stored('chemical-dashboard-current',DEFAULT);
  if(candidate&&Array.isArray(candidate.dimensions)&&candidate.dimensions.every(d=>typeof d==="string"&&LABEL[d])&&typeof (candidate.q||"")==="string"&&['documents','news','relations','wiki'].includes(candidate.dataset))return {...DEFAULT,...candidate,filters:Array.isArray(candidate.filters)?candidate.filters:[]};
 }catch{}
 return {...DEFAULT};
}
function persist(key,value){try{localStorage.setItem(key,JSON.stringify(value))}catch{}}
async function postQuery(body,signal){return api('/api/dashboard/query',{method:'POST',body:JSON.stringify(body),signal})}
function csvDownload(body,setError){
 return fetch('/api/dashboard/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
 .then(async r=>{if(!r.ok)throw Error((await r.json()).error||'导出失败');return r.blob()})
 .then(blob=>{const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='危化品分析-'+new Date().toISOString().slice(0,10)+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)})
 .catch(e=>setError(e.message));
}
function Empty({title,children}){return <div className="dash-empty"><Database size={24}/><strong>{title}</strong><p>{children}</p></div>}
function EChart({option,onSelect,theme,height=280}){
 const ref=useRef(),chart=useRef(),handler=useRef(onSelect);handler.current=onSelect;
 useEffect(()=>{
  const instance=echarts.init(ref.current,null,{renderer:'svg'});chart.current=instance;
  instance.on('click',p=>handler.current?.(p));
  const observer=new ResizeObserver(()=>instance.resize());observer.observe(ref.current);
  return()=>{observer.disconnect();instance.dispose();chart.current=null};
 },[]);
 useEffect(()=>{chart.current?.setOption(option,true)},[option,theme]);
 return <div ref={ref} style={{height}} className="dash-echart" role="img" aria-label={option.aria?.description||'数据图表，使用查看数据获取表格视图'}/>;
}
function chartOption(kind,r,theme){
 const dark=theme==='dark',ink=dark?'#dce9f3':'#20344b',muted=dark?'#a6b8c7':'#667b8d',grid=dark?'#33495b':'#e6edf3';
 const common={animation:false,color:COLORS,textStyle:{fontFamily:'system-ui, Microsoft YaHei, sans-serif',fontSize:12,color:ink},
  aria:{enabled:true,description:'来自真实数据的'+(r.passport?.dataset||'')+'分析，可打开数据表核对'},
  tooltip:{confine:true,backgroundColor:dark?'#182a39':'#fff',borderColor:grid,textStyle:{color:ink},formatter:p=>{
   if(Array.isArray(p))return p.map(a=>esc(a.seriesName)+': '+fmt(Array.isArray(a.value)?a.value.at(-1):a.value)).join('<br/>');
   const d=p.data||{};return esc(d.fullName||d.name||p.name||'记录')+'<br/>'+esc(p.seriesName||r.passport?.metric||'数量')+'：'+esc(Array.isArray(p.value)?p.value.join(' / '):fmt(p.value));}},
  grid:{top:35,left:70,right:24,bottom:48,containLabel:true}};
 const axis={axisLine:{lineStyle:{color:grid}},axisTick:{show:false},axisLabel:{color:muted,fontSize:11},splitLine:{lineStyle:{color:grid}}};
 const metric=r.passport?.metric||'数量',unit=r.passport?.unit||'条';
 const groups=r.groups||[];
 if(kind==='bar'){
  const data=groups.slice(0,14).slice().reverse();
  return {...common,xAxis:{...axis,type:'value',name:unit,max:r._compareMax||undefined},yAxis:{...axis,type:'category',data:data.map(g=>g.key.join(' / ')),axisLabel:{...axis.axisLabel,width:130,overflow:'truncate'}},
   series:[{type:'bar',name:metric,barMaxWidth:20,data:data.map(g=>({value:g.value,name:g.key.join(' / '),group:g})),label:{show:true,position:'right',color:muted,formatter:p=>fmt(p.value)}}]};
 }
 if(kind==='grouped'){
  const keys=[...new Set(groups.map(g=>g.key[0]))].slice(0,12),series=[...new Set(groups.map(g=>g.key[1]||'全部'))].slice(0,8);
  return {...common,legend:{top:0,textStyle:{color:muted},type:'scroll'},xAxis:{...axis,type:'category',data:keys,axisLabel:{...axis.axisLabel,rotate:keys.length>5?25:0}},yAxis:{...axis,type:'value',name:unit},
   series:series.map((name,i)=>({name,type:'bar',barMaxWidth:28,data:keys.map(key=>{const g=groups.find(g=>g.key[0]===key&&(g.key[1]||'全部')===name);return {value:g?.value||0,group:g||{key:[key,name],value:0,records:0}}})}))};
 }
 if(kind==='treemap'){
  const parents=new Map();(r.tree||[]).forEach(g=>{if(!parents.has(g.type))parents.set(g.type,[]);parents.get(g.type).push({name:g.source,value:g.value,filter:{field:'source',values:[g.source]}})});
  return {...common,series:[{type:'treemap',roam:false,nodeClick:false,breadcrumb:{show:false},left:6,right:6,top:5,bottom:5,
   label:{show:true,formatter:p=>p.name+'\n'+fmt(p.value),fontSize:12},upperLabel:{show:true,height:26,color:'#fff'},itemStyle:{borderColor:dark?'#192c3e':'#fff',borderWidth:2,gapWidth:2},
   data:[...parents].map(([name,children])=>({name,children,filter:{field:'type',values:[name]}}))}]};
 }
 if(kind==='line'){
  const known=r.timeline||[],dates=[...new Set(known.map(g=>g.key[0]))].sort(),series=[...new Set(known.map(g=>g.key[1]))].slice(0,8);
  return {...common,legend:{top:0,type:'scroll',textStyle:{color:muted}},grid:{...common.grid,bottom:65},xAxis:{...axis,type:'category',data:dates,boundaryGap:false},yAxis:{...axis,type:'value',name:r.dataset==='wiki'?'项':r.dataset==='relations'?'条':'篇'},
   dataZoom:[{type:'inside'},{type:'slider',height:14,bottom:8,borderColor:grid,showDetail:false}],
   series:series.map(name=>({name,type:'line',showSymbol:dates.length<30,symbolSize:5,data:dates.map(date=>{const g=known.find(g=>g.key[0]===date&&g.key[1]===name);return {value:g?.value||0,filter:{field:'month',values:[date]}}})}))};
 }
 if(kind==='heatmap'){
  const ys=[...new Set(groups.map(g=>g.key[0]))].slice(0,16),xs=[...new Set(groups.map(g=>g.key[1]||'全部'))].slice(0,14);
  const data=groups.filter(g=>ys.includes(g.key[0])&&xs.includes(g.key[1]||'全部')).map(g=>({value:[xs.indexOf(g.key[1]||'全部'),ys.indexOf(g.key[0]),g.value],name:g.key.join(' / '),group:g}));
  return {...common,grid:{...common.grid,top:15,right:60,bottom:35},xAxis:{...axis,type:'category',data:xs,splitArea:{show:true}},yAxis:{...axis,type:'category',data:ys,axisLabel:{...axis.axisLabel,width:100,overflow:'truncate'}},
   visualMap:{min:0,max:Math.max(1,...data.map(d=>d.value[2])),calculable:false,orient:'vertical',right:0,top:'middle',itemWidth:10,itemHeight:110,textStyle:{color:muted},inRange:{color:dark?['#20384b','#477aa9','#83b8e4']:['#ecf3fa','#a0c5e5','#2f6699']}},
   series:[{type:'heatmap',data,label:{show:data.length<120,color:ink,fontSize:11,formatter:p=>fmt(p.value[2])},itemStyle:{borderColor:dark?'#1b3042':'#fff',borderWidth:2}}]};
 }
 if(kind==='scatter'){
  return {...common,xAxis:{...axis,type:'value',name:r.dataset==='documents'?'片段数':'名称提及数'},yAxis:{...axis,type:'value',name:'字符'},series:[{type:'scatter',name:'单记录',symbolSize:8,data:(r.scatter||[]).map(d=>({value:[d.x,d.y],name:d.name,id:d.id,itemStyle:{color:COLORS[Math.abs([...d.type].reduce((a,c)=>a+c.charCodeAt(0),0))%COLORS.length],opacity:.75}}))}]};
 }
 if(kind==='box'){
  return {...common,xAxis:{...axis,type:'category',data:(r.distribution||[]).map(d=>d.name),axisLabel:{...axis.axisLabel,width:90,overflow:'truncate'}},yAxis:{...axis,type:'value',name:r.dataset==='documents'?'片段 / 文档':'字符 / 文章'},
   series:[{name:'五数概括',type:'boxplot',data:(r.distribution||[]).map(d=>({value:d.box,name:d.name+'（n='+d.n+'）',filter:{field:r.dimensions[0],values:[d.name]}})),itemStyle:{color:dark?'#274968':'#d3e6f5',borderColor:COLORS[0]}},
    {name:'IQR异常点',type:'scatter',symbolSize:5,data:(r.distribution||[]).flatMap((d,i)=>d.outliers.map(v=>[i,v]))}]};
 }
 if(kind==='histogram'){
  const data=(r.histogram||[]).map(d=>({name:fmt(d.from)+'–'+fmt(d.to),value:d.value}));
  return {...common,xAxis:{...axis,type:'category',data:data.map(d=>d.name),axisLabel:{...axis.axisLabel,rotate:25}},yAxis:{...axis,type:'value',name:'展示记录数'},series:[{name:'字符分箱',type:'bar',barCategoryGap:0,data,label:{show:true,position:'top',color:muted}}]};
 }
 if(kind==='sankey'){
  const links=(r.sankey||[]).slice(0,150),names=[...new Set(links.flatMap(l=>[l.source,l.target]))];
  return {...common,tooltip:{...common.tooltip,formatter:p=>p.dataType==='edge'?esc(p.data.source.split('|').at(-1))+' → '+esc(p.data.target.split('|').at(-1))+'<br/>'+fmt(p.data.value)+esc(r.passport.unit):esc(p.name.split('|').at(-1))},
   series:[{type:'sankey',left:12,right:90,top:16,bottom:18,nodeWidth:14,nodeGap:15,draggable:false,
    data:names.map(name=>({name,filter:{field:name.split('|')[0],values:[name.split('|').slice(1).join('|')]}})),links,
    label:{color:ink,fontSize:11,formatter:p=>p.name.split('|').at(-1)},lineStyle:{color:'source',opacity:.28,curveness:.45},emphasis:{focus:'adjacency'}}]};
 }
 if(kind==='stacked'){
  const tree=r.tree||[],sources=[...new Set(tree.map(g=>g.source))].slice(0,8),types=[...new Set(tree.map(g=>g.type))];
  return {...common,legend:{top:0,type:'scroll',textStyle:{color:muted}},xAxis:{...axis,type:'value',max:100,name:'%'},yAxis:{...axis,type:'category',data:sources,axisLabel:{...axis.axisLabel,width:115,overflow:'truncate'}},
   series:types.map(name=>({name,type:'bar',stack:'share',barMaxWidth:20,data:sources.map(source=>{
    const raw=tree.find(g=>g.source===source&&g.type===name)?.value||0,total=tree.filter(g=>g.source===source).reduce((a,g)=>a+g.value,0);
    return {value:total?Number((raw/total*100).toFixed(2)):0,name:source,filter:{field:'source',values:[source]},raw,total};
   })}))};
 }
 if(kind==='network'){
  const nodes=r.network?.nodes||[],links=r.network?.links||[];
  return {...common,tooltip:{...common.tooltip,formatter:p=>esc(p.dataType==='edge'?p.data.name:p.data.name)},
   series:[{type:'graph',layout:'force',roam:true,force:{repulsion:200,edgeLength:85},draggable:true,
    data:nodes.map((n,i)=>({...n,name:n.id,fullName:n.name,symbolSize:24,itemStyle:{color:COLORS[i%COLORS.length]}})),
    links:links.map(l=>({...l,label:{show:false},lineStyle:{color:COLORS[0],opacity:.5}})),
    label:{show:true,color:ink,fontSize:11,formatter:p=>(p.data.fullName||p.name).slice(0,10)},emphasis:{focus:'adjacency'},edgeSymbol:['none','arrow']}]};
 }
 return common;
}

function Passport({r}){
 const p=r?.passport;if(!p)return null;
 return <div className="dash-passport">
  <div className="dash-description"><Info size={17}/><p>{p.note}</p></div>
  <dl>{[
   ['数据对象',p.dataset],['统计粒度 / 去重',p.grain],['指标与单位',p.metric+'（'+p.unit+'）'],
   ['内容关键词',p.keyword||'不限'],['日期范围',(p.date_from||'不限')+' 至 '+(p.date_to||'不限')],['当前范围 / 全集',fmt(p.denominator)+' / '+fmt(p.before_filter)],['时间口径',p.time],['未知日期',fmt(p.unknown_dates)+' 条；'+p.unknown_policy],
   ['多标签总计',p.multi_label?'重新去重，分组不可直接相加':'总计按原集合计算'],['快照',p.snapshot_id],
   ['规则版本',p.version],['来源更新时间',stamp(p.source_updated_at)],
  ].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
  <h3>字段覆盖与未知值</h3><div className="dash-missing">{Object.entries(p.missing||{}).map(([key,value])=><span key={key}>{LABEL[key]||key}<strong>{fmt(value)}</strong>未标注</span>)}</div>
  <h3>当前已应用条件</h3><pre>{JSON.stringify(p.filters,null,2)}</pre>
  <p className="dash-footnote">{p.display_limit}</p>
 </div>;
}
function Pivot({r,onSelect}){
 const groups=r.groups||[],rows=[...new Set(groups.map(g=>g.key[0]))].slice(0,40),cols=[...new Set(groups.map(g=>g.key[1]||'全部'))].slice(0,10);
 return <div className="dash-pivot-wrap"><table className="dash-table dash-pivot"><thead><tr><th>{LABEL[r.dimensions[0]]}</th>{cols.map(c=><th key={c}>{c}</th>)}<th>去重总计</th></tr></thead>
 <tbody>{rows.map(key=><tr key={key}><th>{key}</th>{cols.map(c=>{const g=groups.find(g=>g.key[0]===key&&(g.key[1]||'全部')===c);return <td key={c}><button disabled={!g} onClick={()=>g&&onSelect?.(g)}>{g?fmt(g.value):'—'}</button></td>})}<td>{fmt(r.marginals?.[0]?.find(g=>g.key[0]===key)?.value??groups.find(g=>g.key[0]===key)?.value)}</td></tr>)}</tbody>
 <tfoot><tr><th>完整筛选总计</th><td colSpan={cols.length+1}>{fmt(r.value)} {r.passport?.unit}（重新计算，非各行之和）</td></tr></tfoot></table>
 <small>当前显示 {rows.length} 行 × {cols.length} 列；聚合共有 {r.group_count} 组。空格“—”表示无此组合，不代表字段未知。</small></div>;
}
function chartResult(kind,r){
 if(!r)return r;
 if(kind==='line'){
  const dimensions=['month',r.dataset==='wiki'?'page_type':'type'],groups=r.timeline||[],total=groups.reduce((n,g)=>n+g.value,0);
  const margins=dimensions.map((d,index)=>{const m=new Map();groups.forEach(g=>m.set(g.key[index],(m.get(g.key[index])||0)+g.value));return [...m].map(([key,value])=>({key:[key],value,records:value}))});
  return {...r,groups,group_count:groups.length,dimensions,metric:'count',total,value:total,marginals:margins,
   passport:{...r.passport,metric:'已知日期记录数',unit:r.dataset==='wiki'?'项':r.dataset==='relations'?'条':'篇',denominator:total,
    dimensions:['月份',r.dataset==='wiki'?'条目类型':'资料类型'],unknown_policy:'曲线排除未知日期；其他图可单列保留',
    note:r.passport.note+' 本曲线仅显示已知日期记录，未知日期数量单独说明。'},
   _query:{...r._query,dimensions,metric:'count',unknown:'exclude'}};
 }
 if(['treemap','stacked'].includes(kind)){
  const dimensions=kind==='treemap'?['type','source']:['source','type'];
  const groups=(r.tree||[]).map(g=>({key:kind==='treemap'?[g.type,g.source]:[g.source,g.type],value:g.value,records:g.records}));
  return {...r,groups,group_count:groups.length,dimensions,marginals:dimensions.map(d=>r.marginals_by_field?.[d]||[]),
   passport:{...r.passport,dimensions:dimensions.map(d=>LABEL[d])},_query:{...r._query,dimensions}};
 }
 return r;
}
function ChartPanel({id,title,subtitle,kind,r,theme,onPoint,onAction,wide=false,editing,move,draggable,onDragStart,onDrop}){
 r=chartResult(kind,r);
 const [menu,setMenu]=useState(false),[table,setTable]=useState(false);
 const empty=['treemap','stacked'].includes(kind)?!r?.tree?.length:kind==='line'?!r?.timeline?.length:kind==='network'?!r?.network?.nodes?.length:kind==='scatter'?!r?.scatter?.length:['box','histogram'].includes(kind)?!r?.distribution?.length:kind==='sankey'?!r?.sankey?.length:!r?.groups?.length;
 const option=useMemo(()=>r?chartOption(kind,r,theme):null,[kind,r,theme]);
 let footer=r?r.passport.dataset+' · '+(kind==='line'?'月份 / '+r?.passport?.time:r?.passport?.metric+'（'+r?.passport?.unit+'）'):'来源数据读取中';
 if(kind==='scatter'&&r)footer=r.passport.dataset+' · 单记录：'+(r.dataset==='documents'?'片段数 × 字符数':'名称提及数 × 摘要字符')+' · 字符数最高前300条';
 if(kind==='histogram')footer+=' · 对展示的全部筛选记录按字符数分箱';
 if(kind==='bar')footer+=' · 展示前14组';
 if(kind==='sankey')footer+=' · 记录归属，非因果关系';
 return <section className={'dash-panel '+(wide?'dash-panel-wide':'')} data-chart-id={id} draggable={draggable} onDragStart={onDragStart} onDragOver={editing?e=>e.preventDefault():undefined} onDrop={onDrop}>
  <header><div>{editing&&<GripVertical size={16}/>}<h2>{title}</h2><span>{subtitle}</span></div>
   <div className="dash-panel-actions">{editing&&<><button onClick={()=>move(-1)} title="前移"><ArrowUp size={14}/></button><button onClick={()=>move(1)} title="后移"><ArrowDown size={14}/></button></>}
    <button onClick={()=>onAction('passport',r,title)} aria-label={'统计说明：'+title}><Info size={15}/></button>
    <button onClick={()=>setTable(!table)} aria-label={'查看数据：'+title}>{table?<BarChart3 size={15}/>:<Table2 size={15}/>}</button>
    <button onClick={()=>onAction('expand',r,title,kind)} aria-label={'放大：'+title}><Maximize2 size={15}/></button>
    <button onClick={()=>setMenu(!menu)} aria-label={'操作：'+title}><MoreHorizontal size={17}/></button>
    {menu&&<><button className="dash-menu-close" onClick={()=>setMenu(false)} aria-label="关闭图表操作"/><div className="dash-chart-menu">
     {[['analyse','按维度继续分析'],['details','查看明细'],['passport','查看统计说明'],['compare','加入比较'],['export','导出当前范围']].map(([action,text])=><button key={action} onClick={()=>{setMenu(false);onAction(action,r,title,kind)}}>{text}</button>)}
    </div></>}
   </div>
  </header>
  {!r?<Empty title="正在读取数据">首次加载需要建立只读分析快照。</Empty>:empty?<Empty title={kind==='line'?'该时间口径没有已知日期':kind==='network'?'当前范围无实体关系':'当前范围没有适用数据'}>{kind==='line'?'未知日期仍保留在其他统计中；可选择新闻文章的发布日期分析。':kind==='network'?'字面量属性在已接受知识明细中查看。':'更换范围、维度或指标；不会填入演示值。'}</Empty>
   :table||kind==='pivot'?<Pivot r={r} onSelect={g=>onPoint?.({data:{group:g}},r)}/>:<EChart option={option} onSelect={event=>onPoint?.(event,r)} theme={theme}/>}
  <footer><span>{footer}</span><span>{r?fmt(r.total)+' 条范围内记录':'读取中'}</span></footer>
 </section>;
}

function Modal({title,onClose,children,large=false}){
 const ref=useRef();
 useEffect(()=>{const prev=document.activeElement;(ref.current?.querySelector('button,input,select,a[href]')||ref.current)?.focus();const listener=e=>{
  if(e.key==='Escape'){e.preventDefault();onClose()}
  if(e.key==='Tab'){const items=[...ref.current.querySelectorAll('button:not(:disabled),input,select,textarea,a[href]')];const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}
 };document.addEventListener('keydown',listener);return()=>{document.removeEventListener('keydown',listener);prev?.focus()}},[]);
 return <div className="dash-modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><div className={'dash-modal '+(large?'dash-modal-large':'')} ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title}>
 <header><h2>{title}</h2><button className="dash-icon" aria-label="关闭窗口" onClick={onClose}><X size={19}/></button></header><div className="dash-modal-body">{children}</div></div></div>;
}

function Evidence({record,dataset,snapshot,onOpenWiki}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[offset,setOffset]=useState(0);
 useEffect(()=>{let alive=true;setData(null);setError('');
  api('/api/dashboard/detail/'+dataset+'/'+encodeURIComponent(record.id)+'?snapshot_id='+encodeURIComponent(snapshot)+'&offset='+offset)
  .then(d=>alive&&setData(d)).catch(e=>alive&&setError(e.message));return()=>{alive=false};
 },[record.id,dataset,snapshot,offset]);
 if(error)return <div className="dash-error">{error}</div>;
 if(!data)return <Empty title="正在定位原文">读取记录及其来源片段。</Empty>;
 return <div className="dash-evidence"><h3>{data.title}</h3><div className="dash-record-id">{data.id}</div>
 <dl className="dash-inline-meta"><div><dt>来源</dt><dd>{data.source||'未标注'}</dd></div><div><dt>类型</dt><dd>{data.type}</dd></div><div><dt>日期</dt><dd>{data.date||'未标注'}</dd></div><div><dt>状态</dt><dd>{data.status||'见原始资料'}</dd></div></dl>
 {dataset==='documents'&&<><p className="dash-footnote">全文由原始片段组成，当前显示 {offset+1}–{Math.min(offset+20,data.fragment_total)} / {data.fragment_total}。页码缺失时不推测位置。</p>
  <div className="dash-fragments">{data.fragments.map(f=><article key={f.id}><header><code>{f.id}</code><span>页码 {f.page_start||'未标注'}{f.page_end&&f.page_end!==f.page_start?'–'+f.page_end:''}</span></header>{f.section&&<h4>{f.section}</h4>}<p>{f.text}</p></article>)}</div>
  <div className="dash-pagination"><button disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-20))}>上一组片段</button><button disabled={offset+20>=data.fragment_total} onClick={()=>setOffset(offset+20)}>下一组片段</button></div>
  {data.accepted_assertions?.length>0&&<><h3>当前已接受知识</h3>{data.accepted_assertions.map(a=><article className="dash-quote" key={a.id}><strong>{a.title}</strong><p>{a.quote}</p><small>{a.status} · 页码 {a.page_start||'未标注'}</small></article>)}</>}
 </>}
 {dataset==='relations'&&<><div className="dash-quote"><strong>原文引句</strong><p>{data.quote||'该记录未提供引句'}</p></div><p>文档 {data.doc_id||'未标注'} · 页码 {data.page_start||'未标注'} · 当前状态 {data.status}</p><p className="dash-footnote">这是当前审核记录中的引用；适用条件须结合原文核对。</p></>}
 {dataset==='news'&&<><p>{data.summary||'来源没有提供摘要，请打开原站阅读。'}</p>{data.url&&<a className="dash-button dash-primary" href={data.url} target="_blank" rel="noopener noreferrer"><ExternalLink size={15}/>打开原始文章</a>}<p className="dash-footnote">文章发布日期不是事件日期。来源国家为机构 / 站点信息。</p></>}
 {dataset==='wiki'&&<><p>修订：{data.revision||'未提供'}</p><button className="dash-button dash-primary" onClick={()=>onOpenWiki(data.title)}><BookOpen size={16}/>打开 Wiki 原文</button></>}
 </div>;
}

export default function DashboardWorkspace({view='overview',theme='light',onNavigate,onOpenWiki}){
 const [dataTab,setDataTab]=useState('files');
 const [boot,setBoot]=useState(null),[bootError,setBootError]=useState(''),[refresh,setRefresh]=useState(0);
 const [query,setQuery]=useState(initialQuery),[draft,setDraft]=useState(initialQuery),[result,setResult]=useState(null);
 const [independent,setIndependent]=useState({news:null,relations:null}),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [search,setSearch]=useState(''),[controlTab,setControlTab]=useState('data'),[kind,setKind]=useState('grouped');
 const [mode,setMode]=useState('board'),[modal,setModal]=useState(null),[point,setPoint]=useState(null),[notice,setNotice]=useState('');
 const [saved,setSaved]=useState(()=>stored('chemical-dashboard-views',[])),[history,setHistory]=useState([]);
 const [compare,setCompare]=useState(null),[compareResult,setCompareResult]=useState(null),[compareA,setCompareA]=useState(null),[compareRun,setCompareRun]=useState(null),[compareText,setCompareText]=useState('');
 const [editing,setEditing]=useState(false),[order,setOrder]=useState(()=>stored('chemical-dashboard-order',INITIAL_ORDER)),[orderBefore,setOrderBefore]=useState(INITIAL_ORDER);
 const [draftSize,setDraftSize]=useState('comfortable');
 const spec=boot?.datasets?.[draft.dataset],activeSpec=boot?.datasets?.[query.dataset];
 const queryKey=JSON.stringify(query);
 useEffect(()=>{let alive=true;setBootError('');api('/api/dashboard/bootstrap').then(d=>{if(alive)setBoot(d)}).catch(e=>alive&&setBootError(e.message));return()=>{alive=false}},[refresh]);
 useEffect(()=>{
  if(!boot)return;let alive=true;const controller=new AbortController();setBusy(true);setError('');
  const payload={...query,snapshot_id:boot.snapshot_id};
  postQuery(payload,controller.signal).then(r=>{if(alive){setResult({...r,_query:payload});persist('chemical-dashboard-current',query)}})
  .catch(e=>{if(alive&&e.name!=='AbortError')setError(e.message)}).finally(()=>alive&&setBusy(false));
  return()=>{alive=false;controller.abort()};
 },[queryKey,boot?.snapshot_id]);
 useEffect(()=>{
  if(!boot)return;let alive=true;const controller=new AbortController();
  Promise.all(['news','relations'].map(dataset=>postQuery({dataset,dimensions:['type','source'],metric:'count',filters:dataset==='relations'?[{field:'type',values:['实体关系']}]:[],unknown:'include',snapshot_id:boot.snapshot_id},controller.signal).then(r=>[dataset,{...r,_query:{dataset,dimensions:['type','source'],metric:'count',filters:dataset==='relations'?[{field:'type',values:['实体关系']}]:[],unknown:'include',snapshot_id:boot.snapshot_id}}]).catch(e=>{if(alive&&e.name!=='AbortError')setError('独立图表读取失败：'+e.message);return [dataset,null]})))
   .then(entries=>alive&&setIndependent(Object.fromEntries(entries)));return()=>{alive=false;controller.abort()};
 },[boot?.snapshot_id]);
 useEffect(()=>{
  if(!compare||!boot){setCompareResult(null);setCompareA(null);return}
  let alive=true;const controller=new AbortController();
  Promise.all([compare,{...compare,q:compareRun??compare.q}].map(q=>postQuery({...q,snapshot_id:boot.snapshot_id},controller.signal).then(r=>({...r,_query:{...q,snapshot_id:boot.snapshot_id}}))))
   .then(([a,b])=>{if(!alive)return;const max=Math.max(1,...a.groups.map(g=>g.value),...b.groups.map(g=>g.value));setCompareA({...a,_compareMax:max});setCompareResult({...b,_compareMax:max})})
   .catch(e=>alive&&setError(e.message));
  return()=>{alive=false;controller.abort()};
 },[JSON.stringify(compare),compareRun,boot?.snapshot_id]);
 const chemicalResult=useRef(null);
 const [chemicalData,setChemicalData]=useState(null);
 useEffect(()=>{
  if(!boot||!activeSpec?.dimensions.chemical){setChemicalData(null);return}
  let alive=true;const controller=new AbortController();
  postQuery({...query,dimensions:['chemical','type'],metric:'count',snapshot_id:boot.snapshot_id},controller.signal).then(r=>alive&&setChemicalData({...r,_query:{...query,dimensions:['chemical','type'],metric:'count',snapshot_id:boot.snapshot_id}})).catch(()=>alive&&setChemicalData(null));
  return()=>{alive=false;controller.abort()};
 },[queryKey,boot?.snapshot_id]);
 function run(next=draft){setHistory(h=>[...h.slice(-19),query]);setQuery(next);setDraft(next);setPoint(null)}
 function datasetChange(dataset){
  const ds=boot?.datasets[dataset],dims=Object.keys(ds?.dimensions||{}).filter(d=>!['month','year'].includes(d)).slice(0,2);
  const next={...DEFAULT,dataset,dimensions:dims.length?dims:['type']};
  setDraft(next);run(next);
 }
 function addFilter(field,values,source='图表选择'){
  if(!activeSpec?.dimensions[field]&&field!=='id'){setNotice('该条件不适用于当前数据集。');return}
  const fs=[...query.filters.filter(f=>f.field!==field),{field,values,source}];run({...query,filters:fs});
 }
 function undo(){if(!history.length)return;const previous=history.at(-1);setHistory(history.slice(0,-1));setQuery(previous);setDraft(previous)}
 function changeDimension(index,value){const dims=[...draft.dimensions];if(value)dims[index]=value;else dims.splice(index,1);if(new Set(dims).size!==dims.length){setNotice('行列维度不能相同');return}setDraft({...draft,dimensions:dims})}
 function selectPoint(p,r=result,title='图表'){
  if(!r)return;
  const d=p.data||{},group=d.group;
  let conditions=group?r.dimensions.map((field,i)=>({field,values:[group.key[i]]})):d.filter?[d.filter]:[];
  if(d.id&&p.dataType!=='edge'&&r.dataset!=='relations')conditions=[{field:'id',values:[String(d.id)]}];
  if(p.dataType==='edge'&&d.id)conditions=[{field:'id',values:[d.id]}];
  if(p.dataType==='node'&&r.dataset==='relations')return setNotice('节点表示实体，点击关系边核对知识；实体筛选在图谱探索中完成。');
  if(!conditions.length)return;
  setPoint({r,title,conditions,label:group?group.key.join(' / '):d.fullName||d.name||p.name||'选中记录'});
 }
 function applyPoint(){
  if(point.r.dataset!==query.dataset){datasetChange(point.r.dataset);setNotice('已切换到该图的数据对象；请重新选择数据点。');setPoint(null);return}
  const fields=point.conditions.map(c=>c.field),filters=[...query.filters.filter(f=>!fields.includes(f.field)),...point.conditions.map(c=>({...c,source:point.title}))];
  run({...query,filters});
 }
 function detailsFor(r,extra=[]){setModal({type:'details',title:'当前范围明细',r,query:{...r._query,filters:[...(r._query.filters||[]),...extra],offset:0}})}
 function action(name,r,title,chartKind){
  if(!r)return;
  if(name==='passport')return setModal({type:'passport',title:'统计说明 · '+title,r});
  if(name==='expand')return setModal({type:'expand',title,r,kind:chartKind});
  if(name==='details')return detailsFor(r);
  if(name==='analyse'){
   const next={...DEFAULT,...r._query};delete next.snapshot_id;delete next.offset;delete next.size;run(next);onNavigate('analysis');return;
  }
  if(name==='export')return csvDownload(r._query,setError);
  if(name==='compare'){setCompare({...query});setMode('compare');setNotice('已固定 A 组。修改下方 B 组关键词并运行比较。')}
 }
 function saveView(){
  const name=prompt('为这个动态分析视图命名：','我的危化品分析');
  if(!name?.trim())return;
  const entry={id:Date.now(),name:name.trim().slice(0,60),query,kind,mode,order,created_at:new Date().toISOString()};
  const next=[entry,...saved].slice(0,20);persist('chemical-dashboard-views',next);setSaved(next);setNotice('视图已保存在本机，重新打开时使用最新数据；导出附带固定快照。');
 }
 async function share(){
  const u=new URL(location.href);u.searchParams.set('dashboard',JSON.stringify(query));u.hash='analysis';
  try{await navigator.clipboard.writeText(u.toString());setNotice('分析链接已复制，链接包含筛选定义；访问者仍需连接当前服务器。')}catch{setModal({type:'share',title:'分析链接',url:u.toString()})}
 }
 function moveItem(id,delta){const at=order.indexOf(id),next=[...order],to=Math.max(0,Math.min(next.length-1,at+delta));next.splice(at,1);next.splice(to,0,id);setOrder(next)}
 function reorderDrop(target,e){e.preventDefault();const id=e.dataTransfer.getData('dash-panel');if(!id||!order.includes(id))return;const next=order.filter(v=>v!==id);next.splice(next.indexOf(target),0,id);setOrder(next)}
 const overviewPanels={
  timeline:{title:'文章发布节奏',subtitle:'独立新闻范围 · 发布日期，不代表事件发生日',kind:'line',r:independent.news,wide:true},
  structure:{title:'文种与来源结构',subtitle:'面积表示当前指标 · 来源是已有标签',kind:'treemap',r:result},
  ranking:{title:activeSpec?.dimensions.chemical?'化学品名称提及排行':'类别与数量比较',subtitle:activeSpec?.dimensions.chemical?'字面提及 · 多标签，不代表已核实实体':'当前维度与指标',kind:'bar',r:activeSpec?.dimensions.chemical?chemicalData:result},
  matrix:{title:activeSpec?.dimensions.chemical?'名称提及 × 资料类型':'双维度覆盖矩阵',subtitle:'未标注单列 · 组合数据可下钻',kind:'heatmap',r:activeSpec?.dimensions.chemical?chemicalData:result},
  network:{title:'当前已接受实体关系',subtitle:'独立知识范围 · 属性在明细中查看',kind:'network',r:independent.relations},
  composition:{title:'各来源的资料构成',subtitle:'分母是各来源内记录量 · 互斥文种',kind:'stacked',r:result,wide:true},
 };
 const explorePanels=[
  {id:'trend',title:'当前对象的时间分布',subtitle:activeSpec?.time_label,kind:'line',r:result},
  {id:'compare',title:'分组与数量比较',subtitle:result?.passport?.dimensions.join(' × '),kind:'grouped',r:result},
  {id:'scatter',title:'原始记录的数量关系',subtitle:query.dataset==='documents'?'每点为一份文档 · 片段数 × 字符数':'每点为一篇文章 · 名称提及数 × 摘要字符',kind:'scatter',r:result},
  {id:'flow',title:'资料范围—文种—来源路径',subtitle:'完整资料归属 · 不代表因果',kind:'sankey',r:result},
  {id:'distribution',title:'单记录的数量分布',subtitle:query.dataset==='documents'?'每篇文档的片段数 · 五数概括 + IQR':'每篇文章的标题摘要字符数',kind:'box',r:result},
  {id:'pivot',title:'多维透视与去重总计',subtitle:'总计重新计算 · 不直接相加分组',kind:'pivot',r:result},
 ];
 const fieldEntries=Object.entries(spec?.dimensions||{}).filter(([key,d])=>(d.label+' '+key).includes(search));
 function panelProps(id,p){return {id,...p,theme,editing,draggable:editing,move:delta=>moveItem(id,delta),onDragStart:e=>editing&&e.dataTransfer.setData('dash-panel',id),onDrop:e=>reorderDrop(id,e),onPoint:(point,shown)=>selectPoint(point,shown||p.r,p.title),onAction:action}}
 if(bootError)return <main className="dashboard-workspace"><Empty title="分析数据暂时不可读取">{bootError}</Empty><button className="dash-button" onClick={()=>setRefresh(n=>n+1)}>重新读取</button></main>;
 if(!boot)return <main className="dashboard-workspace"><Empty title="正在建立数据分析快照">只读加载资料、新闻、Wiki 与当前知识目录。</Empty></main>;
 if(view==='data')return <main className="dashboard-workspace"><header className="dash-page-head"><div><span className="dash-kicker">数据依据</span><h1>数据说明与指标词典</h1><p>来源、粒度、字段覆盖和统计定义共同决定分析能回答什么。</p></div><button className="dash-button" onClick={()=>setRefresh(n=>n+1)}><RefreshCw size={16}/>更新快照</button></header>
  <div className="dash-view-tabs" role="tablist" aria-label="数据说明内容"><button role="tab" aria-selected={dataTab==='files'} className={dataTab==='files'?'active':''} onClick={()=>setDataTab('files')}>文件与样例</button><button role="tab" aria-selected={dataTab==='dictionary'} className={dataTab==='dictionary'?'active':''} onClick={()=>setDataTab('dictionary')}>指标与分析边界</button></div>
  {dataTab==='files'?<DatasetCatalog snapshot={boot.snapshot_id} refresh={refresh}/>:<>
  <section className="dash-panel"><header><h2>当前数据对象</h2></header><div className="dash-dataset-cards">{Object.entries(boot.datasets).map(([key,ds])=><article key={key}><Database size={21}/><h3>{ds.label}</h3><strong>{ds.available?fmt(ds.total):'未接入'} <small>{ds.unit}</small></strong><p>{ds.note}</p><dl><dt>去重键</dt><dd>{ds.key}</dd><dt>时间口径</dt><dd>{ds.time_label}</dd><dt>日期未知</dt><dd>{fmt(ds.unknown_date)}</dd></dl><button className="dash-button" onClick={()=>{datasetChange(key);onNavigate('analysis')}}>分析这个对象</button></article>)}</div></section>
  <section className="dash-panel"><header><h2>字段覆盖与可用维度</h2></header><div className="dash-field-coverage">{Object.entries(boot.datasets).map(([key,ds])=><details key={key} open={key==='documents'}><summary>{ds.label}</summary><table className="dash-table"><thead><tr><th>维度</th><th>有效覆盖</th><th>未标注</th><th>统计特征</th></tr></thead><tbody>{Object.entries(ds.dimensions).map(([f,d])=><tr key={f}><td>{d.label}</td><td>{d.coverage===null?'暂无分母':d.coverage+'%'}</td><td>{fmt(d.missing)}</td><td>{d.multi?'多标签，重新去重':d.type==='time'?'未知时间单列':'单值类别'}</td></tr>)}</tbody></table></details>)}</div></section>
  <section className="dash-panel"><header><h2>分析边界与快照</h2></header><div className="dash-passport"><ul>{boot.limitations.map(v=><li key={v}>{v}</li>)}</ul><p>快照 {boot.snapshot_id} · 来源更新 {stamp(boot.source_updated_at)} · 规则 {boot.version}</p><p>重复片段 ID：{boot.quality.duplicate_chunk_ids}；无文档 ID 记录：{boot.quality.rows_without_document_id}。同 ID 片段保留首次记录，重复项不重复聚合。</p></div></section>
  </>}
 </main>;

 return <main className={'dashboard-workspace '+(draftSize==='compact'?'dash-compact':'')}>
  <header className="dash-page-head"><div><span className="dash-kicker">{view==='overview'?'内容洞察':'探索与比较'}</span><h1>{view==='overview'?'危化品数据洞察':'多维探索工作台'}</h1><p>{view==='overview'?'资料结构、专题覆盖与可核实的知识关联。':'选择事实对象和指标，在同一口径下组合维度、联动与核对原文。'}</p></div>
   <div className="dash-head-actions"><button className="dash-button" onClick={()=>setRefresh(n=>n+1)} title="更新快照"><RefreshCw size={15}/></button>{view==='overview'&&<button className="dash-button" onClick={()=>{setEditing(!editing);setOrderBefore(order)}}><Settings2 size={15}/>{editing?'退出编辑':'编辑看板'}</button>}
    <button className="dash-button" onClick={saveView}><Save size={15}/>保存视图</button><button className="dash-button" onClick={share}><Share2 size={15}/>分享</button><button className="dash-button" disabled={!result} onClick={()=>csvDownload(result._query,setError)}><Download size={15}/>导出</button>
   </div>
  </header>
  {notice&&<div className="dash-notice" role="status">{notice}<button className="dash-icon" aria-label="关闭提示" onClick={()=>setNotice('')}><X size={14}/></button></div>}
  {(error||bootError)&&<div className="dash-error" role="alert">{error||bootError}<button className="dash-button" onClick={()=>setRefresh(n=>n+1)}>更新快照重试</button></div>}
  {view==='overview'&&<div className="dash-view-tabs">{[['documents','资料结构'],['relations','知识关联'],['news','新闻观察'],['wiki','Wiki 内容']].map(([id,title])=><button key={id} className={query.dataset===id?'active':''} onClick={()=>datasetChange(id)}>{title}</button>)}</div>}
  <section className="dash-filters" aria-label="数据筛选"><label>数据对象<select aria-label="分析数据对象" value={query.dataset} onChange={e=>datasetChange(e.target.value)}>{Object.entries(boot.datasets).map(([key,ds])=><option key={key} value={key} disabled={!ds.available}>{ds.label}</option>)}</select></label>
   {(view==='overview'?['type','source']:['type','chemical']).filter(f=>activeSpec?.dimensions[f]).map(f=><label key={f}>{LABEL[f]}<select aria-label={LABEL[f]+'筛选'} value={query.filters.find(v=>v.field===f)?.values[0]||''} onChange={e=>e.target.value?addFilter(f,[e.target.value],'筛选控件'):run({...query,filters:query.filters.filter(v=>v.field!==f)})}><option value="">全部</option>{activeSpec.dimensions[f].values.map(v=><option key={v}>{v}</option>)}</select></label>)}
   <label className="dash-q">内容关键词<div><Search size={14}/><input aria-label="内容关键词" placeholder="检索当前对象的真实文本" value={draft.q} onChange={e=>setDraft({...draft,q:e.target.value})} onKeyDown={e=>e.key==='Enter'&&run(draft)}/></div></label>
   <button className="dash-button dash-primary" onClick={()=>run(draft)} disabled={busy}><Filter size={14}/>应用</button>
  </section>
  <div className="dash-applied"><span>已应用条件</span>{query.q&&<button onClick={()=>run({...query,q:''})}>关键词：{query.q}<X size={12}/></button>}{query.filters.map((f,i)=><button key={f.field+JSON.stringify(f.values)} onClick={()=>run({...query,filters:query.filters.filter((_,j)=>j!==i)})} title={'来自'+(f.source||'条件')}><span>{LABEL[f.field]||'记录'}：{f.values.join('、')}</span><X size={12}/></button>)}
   {!query.q&&!query.filters.length&&<small>当前对象全部记录；图表各自说明范围</small>}<button className="dash-reset" onClick={()=>run({...query,q:'',filters:[],from:'',to:'',unknown:'include'})}>重置筛选</button><button className="dash-reset" disabled={!history.length} onClick={undo}><Undo2 size={13}/>撤销</button><button className="dash-reset" onClick={()=>setModal({type:'scope',title:'筛选作用范围'})}>查看作用域</button>
  </div>
  <div className="dash-saved"><span>已保存视图</span>{saved.slice(0,6).map(v=><button key={v.id} onClick={()=>{run(v.query);setKind(v.kind||'bar');setNotice('已载入动态视图：'+v.name)}}>{v.name}</button>)}{!saved.length&&<small>保存维度、指标与过滤；不保存原文副本</small>}</div>
  {busy&&<div className="dash-loading" role="status">正在更新分析，当前图表保留上一次成功结果…</div>}
  {view==='overview'&&<><div className="dash-snapshot-metrics">{[['documents','资料文档','doc_id 去重'],['chunks','原文片段','chunk_id 去重'],['wiki','Wiki 条目','包含草稿'],['news','新闻文章','排除已移除记录']].map(([key,text,note])=><div key={key}><FileText size={20}/><span>{text}<strong>{fmt(boot.totals[key])}</strong><small>{note}</small></span></div>)}<p>全库快照 · 不作为每张图的分母</p></div>
   <div className="dash-context"><Info size={16}/><span>当前对象 {activeSpec.label}：{fmt(result?.total)} 条范围内记录。每张图可查看数据、口径并下钻；独立新闻 / 知识图不应用当前对象过滤。</span><button onClick={()=>onNavigate('data')}>完整数据说明</button></div>
   {editing&&<div className="dash-edit-bar">拖动图表或使用前移 / 后移调整阅读顺序。<button className="dash-button dash-primary" onClick={()=>{persist('chemical-dashboard-order',order);setEditing(false);setNotice('看板顺序已保存')}}>保存布局</button><button className="dash-button" onClick={()=>{setOrder(orderBefore);setEditing(false)}}>取消</button></div>}
   <div className="dash-overview-grid">{order.filter(id=>overviewPanels[id]).map(id=><ChartPanel key={id} {...panelProps(id,overviewPanels[id])}/>)}</div>
  </>}
  {view==='analysis'&&<><div className="dash-analysis-tabs">{[['board','组合分析',LayoutGrid],['single','单图探索',BarChart3],['compare','A/B 比较',SlidersHorizontal],['details','明细结果',Table2],['explain','分析说明',Info]].map(([id,text,Icon])=><button key={id} className={mode===id?'active':''} onClick={()=>setMode(id)}><Icon size={15}/>{text}</button>)}</div>
  <div className="dash-analysis-layout"><aside className="dash-controls">
   <header><h2>字段与控制</h2><Database size={16}/></header><div className="dash-field-search"><Search size={14}/><input aria-label="搜索分析字段" value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜索字段"/></div>
   <h3>维度 <small>可拖到分组区域</small></h3><div className="dash-field-pool">{fieldEntries.map(([key,f])=><button key={key} draggable onDragStart={e=>e.dataTransfer.setData('dash-field',key)} onClick={()=>changeDimension(0,key)} title={f.label+'；覆盖率 '+f.coverage+'%；未标注 '+f.missing}><span>{f.type==='time'?'◷':'A'}</span><strong>{f.label}</strong><small>{f.coverage===null?'—':f.coverage+'%'}</small></button>)}</div>
   <div className="dash-control-tabs"><button className={controlTab==='data'?'active':''} onClick={()=>setControlTab('data')}>数据</button><button className={controlTab==='style'?'active':''} onClick={()=>setControlTab('style')}>样式</button></div>
   {controlTab==='data'?<div className="dash-config">
    {[0,1].map(i=><label key={i} className="dash-dropzone" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();changeDimension(i,e.dataTransfer.getData('dash-field'))}}>{i?'列维度（可选）':'行维度'}<select aria-label={i?'列维度':'行维度'} value={draft.dimensions[i]||''} onChange={e=>changeDimension(i,e.target.value)}>{i===1&&<option value="">不分列</option>}{Object.entries(spec.dimensions).map(([key,f])=><option key={key} value={key} disabled={draft.dimensions[1-i]===key}>{f.label}</option>)}</select></label>)}
    <label>指标<select aria-label="聚合指标" value={draft.metric} onChange={e=>setDraft({...draft,metric:e.target.value})}>{Object.entries(spec.metrics).map(([key,m])=><option value={key} key={key}>{m[0]}（{m[1]}）</option>)}</select></label>
    {draft.dataset==='news'&&<label>时间口径<select aria-label="时间口径" value={draft.time_axis} onChange={e=>setDraft({...draft,time_axis:e.target.value})}><option value="published">文章发布日期</option><option value="event">事件日期</option></select></label>}
    <label>未知日期<select aria-label="未知日期处理" value={draft.unknown} onChange={e=>setDraft({...draft,unknown:e.target.value})}><option value="include">单列保留</option><option value="exclude">明确排除</option><option value="only">仅未知日期</option></select></label>
    <label>开始日期<input type="date" aria-label="开始日期" value={draft.from} onChange={e=>setDraft({...draft,from:e.target.value})}/></label><label>结束日期<input type="date" aria-label="结束日期" value={draft.to} onChange={e=>setDraft({...draft,to:e.target.value})}/></label>
    <small className="dash-footnote">同一维度内 OR，不同条件间 AND。时间范围内的未知日期按所选策略处理。</small>
    <button className="dash-button dash-primary" onClick={()=>run(draft)} disabled={busy}>运行分析</button>
   </div>:<div className="dash-config"><label>信息密度<select value={draftSize} onChange={e=>setDraftSize(e.target.value)}><option value="comfortable">舒展</option><option value="compact">紧凑</option></select></label><p>样式变更不改变统计口径。分类颜色、单位与缺失状态保持一致。</p></div>}
   <h3>图表类型</h3><div className="dash-gallery">{VIEW_TYPES.map(([id,name,tip])=><button key={id} className={kind===id?'active':''} title={tip} onClick={()=>{setKind(id);setMode('single')}}><span>{id==='line'?<LineIcon size={20}/>:id==='network'?<Network size={20}/>:id==='pivot'?<Table2 size={20}/>:<BarChart3 size={20}/>}</span>{name}</button>)}</div>
  </aside>
  <div className="dash-analysis-canvas">
   {mode==='board'&&<div className="dash-explore-grid">{explorePanels.map(p=><ChartPanel key={p.id} {...panelProps(p.id,p)}/>)}</div>}
   {mode==='single'&&<ChartPanel {...panelProps('single',{title:VIEW_TYPES.find(v=>v[0]===kind)?.[1]||'单图分析',subtitle:result?.passport?.dimensions.join(' × '),kind,r:result})}/>}
   {mode==='details'&&result&&<DetailsTable r={result} query={result._query} onRecord={record=>setModal({type:'evidence',title:'原文与来源',record,dataset:result.dataset,snapshot:result.snapshot_id})}/>}
   {mode==='explain'&&<section className="dash-panel"><header><h2>当前查询的统计说明</h2></header><Passport r={result}/></section>}
   {mode==='compare'&&<><section className="dash-compare-head"><h2>A/B 同口径比较</h2><p>固定 A 后，两组共享对象、指标、维度、过滤与快照，只有关键词不同。比较范围独立于后续浏览筛选。</p><div><button className="dash-button" onClick={()=>{setCompare({...query});setCompareRun(null)}}>固定当前范围为 A</button><input aria-label="B组关键词" value={compareText} onChange={e=>setCompareText(e.target.value)} placeholder="B 组关键词（全文字面检索）"/><button className="dash-button dash-primary" onClick={()=>{if(!compare)setCompare({...query});setCompareRun(compareText);setNotice('两组共享固定条件，B 使用独立关键词；坐标尺度一致')}}>运行 B 组</button></div></section>
    <div className="dash-compare-grid"><ChartPanel {...panelProps('a',{title:'A · 固定范围',subtitle:'固定分析条件',kind:'bar',r:compareA})}/><ChartPanel {...panelProps('b',{title:'B · 关键词范围',subtitle:compareText||'全部',kind:'bar',r:compareResult})}/></div><p className="dash-footnote">A {fmt(compareA?.value)}；B {fmt(compareResult?.value)}。分组为多标签时差异不由分组数量相加。</p>
   </>}
  </div></div></>}
  <div className="dash-bottom-note"><Database size={14}/><span>真实资料 · {result?.snapshot_id||boot.snapshot_id}</span><span>来源更新 {stamp(boot.source_updated_at)}</span><button onClick={()=>result&&setModal({type:'passport',title:'当前统计说明',r:result})}>统计说明与缺失值</button></div>
  {point&&<Modal title={'选择：'+point.label} onClose={()=>setPoint(null)}>
   <p>来自 {point.title} · {point.r.passport.dataset}。选择的维度条件：</p><div className="dash-point-tags">{point.conditions.map(c=><span key={c.field}>{LABEL[c.field]||'记录'}：{c.values.join('、')}</span>)}</div>
   <div className="dash-point-actions"><button className="dash-button dash-primary" onClick={applyPoint}>联动当前数据对象</button><button className="dash-button" onClick={()=>{detailsFor(point.r,point.conditions);setPoint(null)}}>查看明细 / 原文</button><button className="dash-button" onClick={()=>{action('analyse',point.r,point.title);setPoint(null)}}>按维度继续分析</button></div>
   <p className="dash-footnote">联动只作用于同一事实对象的图表。独立新闻与知识视图有明确范围；未建立的跨对象映射不会推造。</p>
  </Modal>}
  {modal&&<Modal title={modal.title} onClose={()=>setModal(null)} large={['expand','details','evidence'].includes(modal.type)}>
   {modal.type==='passport'&&<Passport r={modal.r}/>}
   {modal.type==='expand'&&<><EChart option={chartOption(modal.kind,modal.r,theme)} theme={theme} height={500} onSelect={p=>selectPoint(p,modal.r,modal.title)}/><Passport r={modal.r}/></>}
   {modal.type==='details'&&<DetailsTable r={modal.r} query={modal.query} onRecord={record=>setModal({type:'evidence',title:'原文与来源',record,dataset:modal.r.dataset,snapshot:modal.r.snapshot_id})}/>}
   {modal.type==='evidence'&&<Evidence record={modal.record} dataset={modal.dataset} snapshot={modal.snapshot} onOpenWiki={onOpenWiki}/>}
   {modal.type==='share'&&<><p>链接保存分析定义，访问者需要对应服务器连接。</p><textarea readOnly value={modal.url} rows={6} style={{width:'100%'}}/></>}
   {modal.type==='scope'&&<><p>当前条件作用于 <strong>{activeSpec.label}</strong> 的图形、明细和导出。同一字段内多值为 OR，多个条件为 AND。</p><ul><li>独立“文章发布节奏”始终使用新闻全库。</li><li>独立“当前已接受实体关系”始终使用当前知识目录。</li><li>化学品名称提及只在支持该维度的数据对象生效。</li><li>工艺、地理、事件数量尚未建立可靠映射时不作为可选维度。</li></ul><Passport r={result}/></>}
  </Modal>}
 </main>;
}

function DetailsTable({r,query,onRecord}){
 const [result,setResult]=useState(r),[offset,setOffset]=useState(query.offset||0),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let alive=true;setBusy(true);setError('');postQuery({...query,offset,size:25}).then(d=>alive&&setResult(d)).catch(e=>alive&&setError(e.message)).finally(()=>alive&&setBusy(false));return()=>{alive=false}},[JSON.stringify(query),offset]);
 if(error)return <div className="dash-error">{error}</div>;
 return <section className="dash-panel dash-detail-panel"><header><h2>真实记录明细</h2><span>共 {fmt(result.total)} 条 · 当前页 {result.details?.length||0} 条 {busy?'· 更新中':''}</span></header><div className="dash-table-scroll"><table className="dash-table"><thead><tr><th>标题与 ID</th><th>类型</th><th>来源</th><th>日期</th><th>数量</th><th>原文</th></tr></thead><tbody>{result.details?.map(row=><tr key={row.id}><td><strong>{row.title}</strong><code>{row.id}</code></td><td>{row.type||row.page_type||'未标注'}</td><td>{row.source||'未标注'}</td><td>{row.date||'未标注'}</td><td>{row.chunks!==undefined?fmt(row.chunks)+' 片段':row.characters!==undefined?fmt(row.characters)+' 字符':row.status||'—'}</td><td><button className="dash-table-link" onClick={()=>onRecord(row)}>查看来源</button></td></tr>)}</tbody></table>{!result.details?.length&&<Empty title="当前条件没有记录">请检查筛选范围和未知值设置。</Empty>}</div>
 <div className="dash-pagination"><span>{offset+1}–{Math.min(offset+25,result.total)} / {fmt(result.total)}</span><button disabled={!offset||busy} onClick={()=>setOffset(Math.max(0,offset-25))}><ChevronLeft size={14}/>上一页</button><button disabled={offset+25>=result.total||busy} onClick={()=>setOffset(offset+25)}>下一页<ChevronRight size={14}/></button></div>
 </section>;
}
