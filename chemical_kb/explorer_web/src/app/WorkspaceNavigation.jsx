import {useEffect,useRef,useState} from 'react';
import {ArrowRight,BookOpen,ChevronDown,Database,Network} from 'lucide-react';

export const NAV_GROUPS=[
 {id:'overview',label:'工作总览'},
 {id:'search-work',label:'智能检索',icon:BookOpen,intro:'在提问和挑战中学习，沿着证据核对。',description:'查找原文、理解答案，再通过题目巩固危化品知识。',children:[{id:'ask',label:'智能问答',description:'提问、查资料、核对引用'},{id:'quiz',label:'兴趣测试',description:'危化品题目、答案解析与错题复习'}]},
 {id:'knowledge',label:'知识 Wiki',icon:BookOpen,intro:'围绕主题阅读，沿着引用核对。',description:'知识条目与化学品专题放在同一处，阅读和查证可以连续进行。',children:[{id:'wiki',label:'条目阅读',description:'章节、引用与版本历史'},{id:'chemical',label:'化学品专题',description:'主题资料、原文与事故线索'}]},
 {id:'knowledge-work',label:'图谱与治理',icon:Network,intro:'看清知识关联，逐条核实证据。',description:'从图谱中的实体关系进入来源核对，再回到审核与知识维护。',children:[{id:'graph',label:'图谱探索',description:'实体、关系与原文来源'},{id:'review',label:'知识治理',description:'断言审核、实体与冲突'}]},
 {id:'data-work',label:'数据与分析',icon:Database,intro:'从全库概览，进入具体分析。',description:'资料结构、文档样例和多维分析共用真实数据与统计口径。',children:[{id:'insights',label:'数据洞察',description:'资料结构与知识分布'},{id:'data',label:'文档与数据',description:'数据样例、口径与文档上传'},{id:'analysis',label:'多维分析',description:'维度组合、比较与明细'}]},
 {id:'news',label:'危化品新闻'},
];

export default function WorkspaceNavigation({page,navigate,connection}){
 const [open,setOpen]=useState(null),timer=useRef(),root=useRef(),triggers=useRef({}),focusNext=useRef(false);
 const group=NAV_GROUPS.find(n=>n.id===open);
 const cancel=()=>clearTimeout(timer.current);
 const close=()=>{cancel();setOpen(null)};
 const schedule=(id,delay=220)=>{cancel();timer.current=setTimeout(()=>setOpen(id),delay)};
 useEffect(()=>()=>clearTimeout(timer.current),[]);
 useEffect(()=>{close()},[page]);
 useEffect(()=>{if(open&&focusNext.current){focusNext.current=false;root.current?.querySelector('.ui-mega-links button')?.focus()}},[open]);
 return <nav ref={root} className="ui-horizontal-nav ui-grouped-nav" aria-label="主导航" onPointerLeave={e=>e.pointerType==='mouse'&&schedule(null,180)} onPointerEnter={cancel} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))close()}} onKeyDown={e=>{if(e.key==='Escape'&&open){e.preventDefault();const id=open;close();triggers.current[id]?.focus()}}}>
  {NAV_GROUPS.map(n=>{const active=n.children?.some(c=>c.id===page)||n.id===page;return <div key={n.id} className="ui-horizontal-item"><button ref={el=>{triggers.current[n.id]=el}} className={active?'active':''} aria-current={active?'page':undefined} aria-expanded={n.children?open===n.id:undefined} aria-haspopup={n.children?'true':undefined} aria-controls={n.children?'workspace-menu-'+n.id:undefined} onPointerEnter={e=>{if(e.pointerType==='mouse')schedule(n.children?n.id:null)}} onClick={()=>n.children?(cancel(),setOpen(open===n.id?null:n.id)):(close(),navigate(n.id))} onKeyDown={e=>{if(n.children&&e.key==='ArrowDown'){e.preventDefault();cancel();focusNext.current=true;if(open===n.id)root.current?.querySelector('.ui-mega-links button')?.focus();else setOpen(n.id)}}}>{n.label}{n.children&&<ChevronDown size={13} className={open===n.id?'is-open':''}/>}</button></div>})}
  <span className="ui-horizontal-status"><i data-status={connection}/>{connection==='ready'?'服务可达':connection==='offline'?'服务暂不可达':'连接中'}</span>
  {group?.children&&<section id={'workspace-menu-'+group.id} className="ui-mega-panel" aria-label={group.label+'子栏目'} onPointerEnter={cancel}><div className="ui-mega-intro"><group.icon size={44} strokeWidth={1.1}/><div><strong>{group.intro}</strong><p>{group.description}</p></div></div><div className="ui-mega-links">{group.children.map(n=><button key={n.id} aria-label={n.label} aria-current={page===n.id?'page':undefined} onClick={()=>{close();navigate(n.id)}}><span>{n.label}<small>{n.description}</small></span><ArrowRight size={18}/></button>)}</div></section>}
 </nav>;
}
