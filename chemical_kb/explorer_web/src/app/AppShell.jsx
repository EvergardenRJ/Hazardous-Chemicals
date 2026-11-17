import {lazy,Suspense,useCallback,useEffect,useRef,useState} from 'react';
import {Alert,BottomNavigation,BottomNavigationAction,Box,Button,Chip,Dialog,DialogContent,DialogTitle,Drawer,IconButton,Menu,MenuItem,Stack,TextField,Tooltip,Typography} from '@mui/material';
import {Activity,BookOpen,FileText,FlaskConical,LayoutDashboard,Menu as MenuIcon,Monitor,Moon,MoreHorizontal,Network,Newspaper,PanelLeftClose,Search,ShieldCheck,SlidersHorizontal,Sun,X} from 'lucide-react';
import {api,today} from '../api';
import {useUI} from '../components/WorkspaceUI';
import {PageQuote,PageQuoteProvider} from '../components/PageQuote';
import {commitRoute,readRoute,routeUrl,savePosition,restorePosition} from './routeState';
import WorkspaceNavigation from './WorkspaceNavigation';
import useScrollBrandbar from './useScrollBrandbar';
const QuizWorkspace=lazy(()=>import('../QuizWorkspace'));
const AskWorkspace=lazy(()=>import('../Panels').then(m=>({default:m.AskWorkspace})));
const GovernanceWorkspace=lazy(()=>import('../Panels').then(m=>({default:m.GovernanceWorkspace})));
const KnowledgeSearch=lazy(()=>import('./KnowledgeSearch'));
const TaskDrawer=lazy(()=>import('./TaskDrawer'));
const DashboardWorkspace=lazy(()=>import('../DashboardWorkspace'));
const GraphDesk=lazy(()=>import('../GraphWorkspace'));
const WikiWorkspace=lazy(()=>import('../WikiWorkspace'));
const ChemicalWorkspace=lazy(()=>import('../ChemicalWorkspace'));
const NewsWorkspace=lazy(()=>import('../NewsWorkspace'));
const PortalHome=lazy(()=>import('./PortalHome'));
const SHORTCUT=/Mac|iPhone|iPad/.test(navigator.platform)?'⌘ K':'Ctrl K';
const NAV=[
 {id:'overview',label:'工作总览',icon:LayoutDashboard,group:'开始工作'},
 {id:'quiz',label:'兴趣测试',icon:ShieldCheck,group:'开始工作'},
 {id:'ask',label:'智能检索',icon:Search,group:'开始工作'},
 {id:'wiki',label:'知识 Wiki',icon:BookOpen,group:'阅读与探索'},
 {id:'chemical',label:'化学品专题',icon:FlaskConical,group:'阅读与探索'},
 {id:'graph',label:'图谱探索',icon:Network,group:'阅读与探索'},
 {id:'insights',label:'数据洞察',icon:LayoutDashboard,group:'数据与分析'},
 {id:'analysis',label:'多维分析',icon:SlidersHorizontal,group:'阅读与探索'},
 {id:'news',label:'危化品新闻',icon:Newspaper,group:'阅读与探索'},
 {id:'review',label:'知识治理',icon:ShieldCheck,group:'维护'},
 {id:'data',label:'文档与数据',icon:FileText,group:'维护'},
];

export default function AppShell(){
 const ui=useUI(),[route,setRoute]=useState(readRoute),[summary,setSummary]=useState(null),[connection,setConnection]=useState('connecting'),[updated,setUpdated]=useState(null),[refresh,setRefresh]=useState(0),[searchOpen,setSearchOpen]=useState(false),[topicOpen,setTopicOpen]=useState(false),[tasksOpen,setTasksOpen]=useState(false),[collapsed,setCollapsed]=useState(()=>{try{return localStorage.getItem('ui-rail-collapsed')==='true'}catch{return false}}),[mobileMenu,setMobileMenu]=useState(false),[appearance,setAppearance]=useState(null);
 const [graph,setGraph]=useState(null),[graphError,setGraphError]=useState(''),[graphLoading,setGraphLoading]=useState(false),[seedQuestion,setSeedQuestion]=useState(''),[searchSeed,setSearchSeed]=useState('');
 const previousHref=useRef(location.href),handling=useRef(false),mainRef=useRef(null);
 const page=(route.page==='chemical'||NAV.some(n=>n.id===route.page))?route.page:'overview',chemical=route.params.chemical||'',asOf=route.params.as_of||today(),mode=route.params.mode||'approved';
 const brandHidden=useScrollBrandbar(page,mainRef);
 const navigateRaw=useCallback((id,changes={},replace=false)=>{savePosition();commitRoute(routeUrl(id,changes),replace)},[]);
 const navigate=useCallback((id,section)=>{setMobileMenu(false);return ui.guardNavigation(()=>{const target=id==='resolve'?'review':id==='library'?'data':id;const hash=target==='review'&&(section==='entities'||id==='resolve')?'review-entities':target;navigateRaw(hash,target==='news'?{article:section?.article||null,...(section?.article?{chemical:null}:{})}:target==='insights'&&section?.dashboard?{dashboard:JSON.stringify(section.dashboard)}:{});setMobileMenu(false);setSearchOpen(false)})},[ui.guardNavigation,navigateRaw]);
 const openWiki=useCallback((name,section)=>ui.guardNavigation(()=>{navigateRaw('wiki',{wiki:name,section:section||null,view:null,revision:null});setSearchOpen(false)}),[ui.guardNavigation,navigateRaw]);
 const chooseChemical=useCallback(name=>ui.guardNavigation(()=>{savePosition();commitRoute(routeUrl('chemical',{chemical:name,chemicalView:'overview'},{clean:true}));setTopicOpen(false);setSeedQuestion('')}),[ui.guardNavigation]);
 const focusGraph=useCallback(id=>ui.guardNavigation(()=>navigateRaw('graph',{focus_id:id})),[ui.guardNavigation,navigateRaw]);
 useEffect(()=>{const change=async()=>{const next=location.href;if(next===previousHref.current){setRoute(readRoute());return}if(handling.current)return;handling.current=true;history.replaceState({},'',previousHref.current);await ui.guardNavigation(()=>{history.replaceState({},'',next);previousHref.current=next;setRoute(readRoute());window.dispatchEvent(new Event('wiki:navigate'))});handling.current=false;};const remember=()=>{previousHref.current=location.href;setRoute(readRoute())};const internal=()=>{previousHref.current=location.href;setRoute(readRoute());window.dispatchEvent(new Event('wiki:navigate'))};window.addEventListener('popstate',change);window.addEventListener('hashchange',change);window.addEventListener('workspace:navigate',internal);window.addEventListener('workspace:location',remember);return()=>{window.removeEventListener('popstate',change);window.removeEventListener('hashchange',change);window.removeEventListener('workspace:navigate',internal);window.removeEventListener('workspace:location',remember)}},[ui.guardNavigation]);
 useEffect(()=>{const key=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setSearchOpen(v=>!v)}};const links=e=>{if(e.defaultPrevented||e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;const a=e.target.closest('a[href]');if(!a||a.target==='_blank'||a.hasAttribute('download'))return;const u=new URL(a.href,location.href);if(u.origin===location.origin&&!u.pathname.startsWith('/api/')&&['/','/index.html',location.pathname].includes(u.pathname)){e.preventDefault();ui.guardNavigation(()=>{history.pushState({},'',u);window.dispatchEvent(new Event('workspace:navigate'))})}};document.addEventListener('keydown',key);document.addEventListener('click',links);return()=>{document.removeEventListener('keydown',key);document.removeEventListener('click',links)}},[ui.guardNavigation]);
 useEffect(()=>{let active=true;const load=()=>{if(document.visibilityState!=='visible')return;api('/api/summary').then(d=>{if(active){setSummary(d);setConnection('ready');setUpdated(new Date())}}).catch(()=>active&&setConnection('offline'))};load();const id=setInterval(load,30000);return()=>{active=false;clearInterval(id)}},[refresh]);
 useEffect(()=>{if(page!=='graph')return;const c=new AbortController();setGraphLoading(true);setGraphError('');api('/api/graph?mode='+mode,{signal:c.signal}).then(setGraph).catch(e=>{if(e.name!=='AbortError')setGraphError(e.message)}).finally(()=>{if(!c.signal.aborted)setGraphLoading(false)});return()=>c.abort()},[page,mode,refresh]);
 const menu=<><button className="ui-brand" onClick={()=>navigate('overview')} aria-label="危化品知识平台首页"><span><FlaskConical size={23}/></span>{!collapsed&&<strong>危化品<span>知识与证据</span></strong>}</button><nav aria-label="主导航">{NAV.map((n,i)=>{const Icon=n.icon;return <div key={n.id}>{(i===0||NAV[i-1].group!==n.group)&&!collapsed&&<div className="ui-nav-group">{n.group}</div>}<Tooltip title={collapsed?n.label:''} placement="right"><button className={'ui-nav-link '+(page===n.id?'active':'')} aria-current={page===n.id?'page':undefined} onClick={()=>navigate(n.id)}><Icon size={19}/>{!collapsed&&<span>{n.label}</span>}</button></Tooltip></div>})}</nav><div className="ui-sidebar-bottom"><button onClick={()=>{const v=!collapsed;setCollapsed(v);try{localStorage.setItem('ui-rail-collapsed',String(v))}catch{}}} className="ui-nav-link" aria-label={collapsed?'展开导航':'收起导航'}><PanelLeftClose size={18}/>{!collapsed&&'收起导航'}</button><a href="/legacy-ui/index.html" className="ui-legacy-link">回到旧版</a>{!collapsed&&<small className="ui-service-state"><i data-status={connection}/>{connection==='ready'?'服务可达':connection==='offline'?'服务暂不可达':'正在连接'}</small>}</div></>;
 useEffect(()=>restorePosition(),[route.page,route.params.wiki,route.params.section,route.params.chemical]);
 const setAsOf=value=>navigateRaw(location.hash.slice(1)||page,{as_of:value},true);
 return <div className={'app-shell ui-shell ui-portal-shell '+(page==='overview'?'ui-home-active':'')}>
  <Drawer open={mobileMenu} onClose={()=>setMobileMenu(false)} slotProps={{paper:{sx:{width:260,p:2}}}}><div className="ui-mobile-menu">{menu}</div></Drawer>
  <div ref={mainRef} className="app-main ui-main"><header className={'ui-topbar '+(brandHidden?'is-scroll-hidden':'')} aria-hidden={brandHidden||undefined} inert={brandHidden||undefined}><IconButton className="ui-menu-trigger" onClick={()=>setMobileMenu(true)} aria-label="打开导航"><MenuIcon size={21}/></IconButton><button className="ui-header-brand" onClick={()=>navigate('overview')} aria-label="危化品知识平台首页"><span><FlaskConical size={28} strokeWidth={1.5}/></span><strong>危化品知识平台<small>CHEMICAL KNOWLEDGE & EVIDENCE</small></strong></button><div className="ui-breadcrumb"><strong>{page==='chemical'?'化学品专题':NAV.find(n=>n.id===page)?.label}</strong></div><button className="ui-command-trigger" onClick={()=>{setSearchSeed('');setSearchOpen(true)}} aria-label="搜索知识与工作区"><Search size={18}/><span>搜索知识与原文</span><kbd>{SHORTCUT}</kbd></button><div className="ui-topbar-actions"><Tooltip title="任务与进度"><IconButton onClick={()=>setTasksOpen(true)} aria-label="任务与进度"><Activity size={20}/></IconButton></Tooltip><Tooltip title="页面外观"><IconButton onClick={e=>setAppearance(e.currentTarget)} aria-label="页面外观">{ui.preference==='system'?<Monitor size={19}/>:ui.themeMode==='dark'?<Moon size={19}/>:<Sun size={19}/>}</IconButton></Tooltip><Menu anchorEl={appearance} open={!!appearance} onClose={()=>setAppearance(null)}>{[['system','跟随系统'],['light','浅色'],['dark','深色']].map(([v,l])=><MenuItem key={v} selected={ui.preference===v} onClick={()=>{ui.setPreference(v);setAppearance(null)}}>{l}</MenuItem>)}</Menu></div><a href="/legacy-ui/index.html" onClick={e=>{e.preventDefault();ui.guardNavigation(()=>location.assign('/legacy-ui/index.html'))}} className="ui-header-legacy">回到旧版</a></header>
  <WorkspaceNavigation page={page} navigate={navigate} connection={connection}/>

  {connection==='offline'&&<Alert severity="warning" action={<Button onClick={()=>setRefresh(x=>x+1)}>重试连接</Button>}>服务暂时不可达，保留上次读取的数据。请稍后重试。</Alert>}
  <PageQuoteProvider page={page}>
  <Suspense fallback={<div className="ui-page-loading" role="status"><Activity size={22}/>正在打开工作区…</div>}>
   {page==='overview'&&<PortalHome summary={summary} chemical={chemical} theme={ui.themeMode} onNavigate={navigate} onOpenWiki={openWiki} onChooseChemical={name=>name?chooseChemical(name):setTopicOpen(true)} onSearch={query=>{setSearchSeed(query);setSearchOpen(true)}}/>}
   {['insights','analysis','data'].includes(page)&&<DashboardWorkspace view={page==='insights'?'overview':page} theme={ui.themeMode} onNavigate={navigate} onOpenWiki={openWiki} chemical={chemical} onChooseChemical={()=>setTopicOpen(true)}/>}
   {page==='chemical'&&(chemical?<ChemicalWorkspace key={chemical} onNavigate={navigate} onOpenWiki={openWiki} onFocusGraph={focusGraph}/>:<div className="ui-topic-start"><FlaskConical size={46}/><h1>从一种化学品开始</h1><PageQuote/><Button variant="contained" onClick={()=>setTopicOpen(true)}>选择化学品专题</Button><Stack direction="row" gap={1} sx={{mt:3}}>{['液氯','甲醇','氢氟酸'].map(n=><Button key={n} variant="outlined" onClick={()=>chooseChemical(n)}>{n}</Button>)}</Stack></div>)}
   {page==='wiki'&&<WikiWorkspace key={chemical}/>}
   {page==='quiz'&&<QuizWorkspace onAsk={q=>{setSeedQuestion(q);navigate('ask')}}/>}
   {page==='ask'&&<AskWorkspace key={chemical} asOf={asOf} setAsOf={setAsOf} seedQuestion={seedQuestion||(chemical?chemical+'储存和装卸有哪些原文依据？':'')}/>}
   {page==='review'&&<GovernanceWorkspace key={chemical} tab={route.governanceTab} setTab={tab=>navigate('review',tab)} summary={summary} asOf={asOf} onGraphRefresh={()=>setRefresh(x=>x+1)}/>}
   {page==='news'&&<NewsWorkspace key={chemical+':'+(route.params.article||'')}/>}
   {page==='graph'&&<GraphDesk raw={graph} loading={graphLoading} error={graphError} mode={mode} setMode={v=>navigateRaw('graph',{mode:v},true)} asOf={asOf} setAsOf={setAsOf} onAsk={q=>{setSeedQuestion(q);navigate('ask')}} onResolve={id=>{if(id)navigateRaw('review',{assertion_id:id});else navigate('review','entities')}} externalFocusId={route.params.focus_id||(chemical?'chemical::'+chemical:'')} theme={ui.themeMode} summary={summary}/>}
  </Suspense>
  </PageQuoteProvider></div>
  <BottomNavigation className="ui-bottom-nav" showLabels value={['overview','ask','chemical','wiki'].includes(page)?page:'more'} onChange={(_,id)=>id==='more'?setMobileMenu(true):navigate(id)}>{[['overview','总览',LayoutDashboard],['ask','检索',Search],['wiki','Wiki',BookOpen],['chemical','专题',FlaskConical],['more','更多',MoreHorizontal]].map(([id,label,Icon])=><BottomNavigationAction key={id} value={id} label={label} icon={<Icon size={21}/>}/>)}</BottomNavigation>
  <Suspense fallback={null}>{searchOpen&&<KnowledgeSearch nav={NAV} initialQuery={searchSeed} open onClose={()=>setSearchOpen(false)} navigate={navigate} openWiki={openWiki} focusGraph={focusGraph} chooseChemical={chooseChemical}/>}{topicOpen&&<KnowledgeSearch nav={NAV} chemicalOnly open onClose={()=>setTopicOpen(false)} navigate={navigate} openWiki={openWiki} focusGraph={focusGraph} chooseChemical={chooseChemical}/>}{tasksOpen&&<TaskDrawer open onClose={()=>setTasksOpen(false)} openWiki={openWiki}/>}</Suspense>
 </div>;
}
