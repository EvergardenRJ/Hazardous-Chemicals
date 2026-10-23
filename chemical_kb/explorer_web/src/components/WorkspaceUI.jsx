import {cloneElement,createContext,lazy,Suspense,useCallback,useContext,useEffect,useId,useMemo,useRef,useState} from 'react';
import {createTheme,ThemeProvider} from '@mui/material/styles';
import {Alert,Box,Button,Chip,CircularProgress,Dialog,DialogActions,DialogContent,DialogContentText,DialogTitle,Drawer,IconButton,Snackbar,Stack,Typography,useMediaQuery} from '@mui/material';
import {X,ExternalLink,Copy,FileText} from 'lucide-react';
import {schemes,fontFamily} from '../theme/tokens';

const UIContext=createContext(null);
const TextField=lazy(()=>import('@mui/material/TextField'));
export const useUI=()=>useContext(UIContext);
export function readStored(key,fallback=null,storage=localStorage){try{return JSON.parse(storage.getItem(key)||'null')??fallback}catch{return fallback}}
export function storeValue(key,value,storage=localStorage){try{storage.setItem(key,JSON.stringify(value))}catch{}}
export function EvidenceAdapter(item,extra={}) {
  const m=item?.metadata||item?.assertion||item||{};
  return {kind:'document',id:item?.evidence_id||m.chunk_id||m.source_chunk_id||m.assertion_id,title:m.title||m.code||m.source_doc_id||m.doc_id||'来源标题未记录',docId:m.doc_id||m.source_doc_id,pageStart:m.page_start||null,pageEnd:m.page_end||null,quote:m.text||m.source_text_quote||'',sourceRevision:m.source_revision||m.version||null,knowledgeRevision:null,reviewStatus:m.review_status||m.status||'unknown',fileUrl:m.source_url||null,sourceUrl:m.source_url||null,...extra};
}
export function StatusBadge({status,dimension='review',label}) {
 const labels={review:{pending:'待审核',approved:'已通过',modified:'修订后通过',rejected:'已撤销',unknown:'待确认'},publish:{draft:'未发布草稿',published:'已发布版本',history:'历史版本'},freshness:{fresh:'未检测到变化',stale:'来源已变化',needs_check:'来源待核对'}};
 const color=['approved','modified','published','fresh'].includes(status)?'success':['rejected','failed'].includes(status)?'error':['pending','draft','stale','needs_check'].includes(status)?'warning':'default';
 return <Chip size="small" variant="outlined" color={color} label={label||labels[dimension]?.[status]||status||'待确认'}/>;
}
export function SettingRow({title,summary,children}){
 const id=useId();return <Box component="label" htmlFor={id} className="ui-setting-row"><Box><Typography component="span" fontSize={14} fontWeight={600}>{title}</Typography>{summary&&<Typography component="span" display="block" fontSize={12} color="text.secondary" sx={{mt:.5,lineHeight:1.6}}>{summary}</Typography>}</Box><Box className="ui-setting-control">{cloneElement(children,{id})}</Box></Box>;
}
export function AsyncState({loading,error,empty,children,onRetry,lastSuccessAt}) {
 if(error)return <Alert severity="error" action={onRetry&&<Button color="inherit" onClick={onRetry}>重试</Button>}>{error}{lastSuccessAt&&'；保留上次读取的数据'}</Alert>;
 if(loading)return <Stack direction="row" alignItems="center" gap={1.5} role="status" sx={{p:3}}><CircularProgress size={20}/>正在读取资料…</Stack>;
 if(empty)return <Box className="ui-empty"><FileText size={28}/><Typography>暂无匹配资料</Typography>{onRetry&&<Button onClick={onRetry}>重新读取</Button>}</Box>;
 return children;
}

export function UIProvider({children}) {
 const [preference,setPreference]=useState(()=>{try{return localStorage.getItem('alpha-theme')||'system'}catch{return 'system'}});
 const systemDark=useMediaQuery('(prefers-color-scheme: dark)');
 const themeMode=preference==='system'?(systemDark?'dark':'light'):preference;
 const [dialog,setDialog]=useState(null),[field,setField]=useState(''),[notice,setNotice]=useState(null),[evidence,setEvidence]=useState(null);
 const guardRef=useRef(new Map()),resolver=useRef(null),dialogQueue=useRef(Promise.resolve()),evidenceTrigger=useRef(null),evidenceReturn=useRef(null);
 useEffect(()=>{document.documentElement.dataset.theme=themeMode;document.documentElement.dataset.ui='v2';try{localStorage.setItem('alpha-theme',preference)}catch{}},[themeMode,preference]);
 const theme=useMemo(()=>{const c=schemes[themeMode];return createTheme({palette:{mode:themeMode,primary:{main:c.primary,contrastText:themeMode==='dark'?'#102832':'#FFFFFF'},background:{default:c.bg,paper:c.paper},text:{primary:c.ink,secondary:c.muted},divider:c.line,success:{main:c.success},warning:{main:c.warning},error:{main:c.error}},typography:{fontFamily,fontSize:14,h1:{fontSize:28,fontWeight:650},h2:{fontSize:20,fontWeight:600}},shape:{borderRadius:8},components:{MuiButton:{defaultProps:{disableElevation:true},styleOverrides:{root:{textTransform:'none',minHeight:40,fontWeight:600}}},MuiIconButton:{styleOverrides:{root:{minWidth:40,minHeight:40}}},MuiDialog:{styleOverrides:{paper:{borderRadius:16}}},MuiDrawer:{styleOverrides:{paper:{backgroundImage:'none'}}},MuiChip:{styleOverrides:{root:{fontSize:12}}},MuiTextField:{defaultProps:{size:'small'}},MuiPaper:{styleOverrides:{root:{backgroundImage:'none'}}}}});},[themeMode]);
 const settle=useCallback(value=>{resolver.current?.(value);resolver.current=null;setDialog(null)},[]);
 const request=useCallback(config=>{
  const promise=dialogQueue.current.then(()=>new Promise(resolve=>{resolver.current=resolve;setField(config.value||'');setDialog(config)}));
  dialogQueue.current=promise.catch(()=>{});return promise;
 },[]);
 const notify=useCallback((message,severity='success')=>setNotice({message,severity}),[]);
 const guardNavigation=useCallback(async action=>{
  for(const get of guardRef.current.values()){
   const g=get();if(!g?.dirty)continue;
   const choice=await request({kind:'dirty',title:g.title||'有尚未保存的修改',description:'继续编辑，或将修改暂存在当前浏览器后离开。暂存不会提交审核。'});
   if(choice==='stay'||choice==null)return false;
   if(choice==='stash')g.stash?.();
   g.discard?.();
  }
  action?.();return true;
 },[request]);
 useEffect(()=>{const unload=e=>{if([...guardRef.current.values()].some(get=>get()?.dirty)){e.preventDefault();e.returnValue=''}};window.addEventListener('beforeunload',unload);return()=>window.removeEventListener('beforeunload',unload)},[]);
 const openEvidence=useCallback(data=>{evidenceTrigger.current=document.activeElement;evidenceReturn.current=data.triggerSelector||null;setEvidence(data)},[]);
 const restoreEvidenceFocus=()=>{const previous=evidenceTrigger.current;const target=previous?.isConnected?previous:evidenceReturn.current?document.querySelector(evidenceReturn.current):null;target?.focus?.()};
 const closeEvidence=()=>{setEvidence(null)};
 const value=useMemo(()=>({themeMode,preference,setPreference,notify,openEvidence,request,guardNavigation,registerGuard:(id,get)=>{guardRef.current.set(id,get);return()=>guardRef.current.delete(id)}}),[themeMode,preference,notify,openEvidence,request,guardNavigation]);
 const phone=useMediaQuery('(max-width:767px)');
 return <ThemeProvider theme={theme}><UIContext.Provider value={value}>{children}
  <Dialog open={!!dialog} onClose={()=>settle(dialog?.kind==='dirty'?'stay':null)} fullWidth maxWidth="sm" aria-labelledby="ui-dialog-title">
   <DialogTitle id="ui-dialog-title">{dialog?.title}</DialogTitle><DialogContent><DialogContentText sx={{mb:2}}>{dialog?.description}</DialogContentText>{dialog?.kind==='text'&&<Suspense fallback={<CircularProgress size={20}/>}><TextField autoFocus fullWidth label={dialog.label||'名称'} value={field} onChange={e=>setField(e.target.value)} slotProps={{htmlInput:{maxLength:dialog.maxLength||120}}} onKeyDown={e=>{if(e.key==='Enter'&&!e.nativeEvent.isComposing&&field.trim()){e.preventDefault();settle(field.trim())}}}/></Suspense>}</DialogContent>
   <DialogActions sx={{p:2,flexWrap:'wrap',gap:1}}>{dialog?.kind==='dirty'?<><Button onClick={()=>settle('stay')}>继续编辑</Button><Button color="error" onClick={()=>settle('discard')}>放弃修改</Button><Button variant="contained" onClick={()=>settle('stash')}>暂存本机并离开</Button></>:<><Button onClick={()=>settle(null)}>取消</Button><Button variant="contained" color={dialog?.danger?'error':'primary'} disabled={dialog?.kind==='text'&&!field.trim()} onClick={()=>settle(dialog.kind==='text'?field.trim():true)}>{dialog?.submitLabel||'确认'}</Button></>}</DialogActions>
  </Dialog>
  <Drawer anchor={phone?'bottom':'right'} open={!!evidence} onClose={closeEvidence} slotProps={{transition:{onExited:restoreEvidenceFocus},paper:{className:'ui-evidence-drawer',sx:{width:phone?'100%':420,maxWidth:'100%',height:phone?'94dvh':'100%',borderRadius:phone?'16px 16px 0 0':0,p:3}}}}>
   {evidence&&<><Stack direction="row" alignItems="center" justifyContent="space-between"><Typography variant="h2">证据与来源</Typography><IconButton aria-label="关闭证据" onClick={closeEvidence}><X size={20}/></IconButton></Stack><Typography variant="h6" sx={{my:2,lineHeight:1.5}}>{evidence.title}</Typography><StatusBadge status={evidence.reviewStatus}/><Box component="dl" className="ui-evidence-meta">{[['文档',evidence.docId||'未记录'],['页码',evidence.pageStart?`${evidence.pageStart}${evidence.pageEnd&&evidence.pageEnd!==evidence.pageStart?'–'+evidence.pageEnd:''}`:'页码未记录'],['来源版本',evidence.sourceRevision||'未记录'],['知识版本',evidence.knowledgeRevision||'未记录'],['片段',evidence.id||'未记录']].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</Box><Box component="blockquote" className="ui-evidence-quote">{evidence.quote||'当前来源没有保存原文摘录。'}</Box><Stack gap={1.5} sx={{mt:2}}>{evidence.fileUrl?<Button component="a" href={evidence.fileUrl} target="_blank" rel="noopener noreferrer" variant="contained" startIcon={<ExternalLink size={16}/>}>{evidence.pageStart&&evidence.fileUrl.includes('#page=')?'打开原文件页':'打开原文件'}</Button>:<Alert severity="info">当前记录未关联可打开的原文件，可先核对已保存的摘录。</Alert>}<Button startIcon={<Copy size={16}/>} onClick={async()=>{try{await navigator.clipboard.writeText([evidence.title,evidence.docId,evidence.pageStart?'第 '+evidence.pageStart+' 页':'页码未记录',evidence.quote].filter(Boolean).join('\n'));notify('来源信息已复制')}catch{notify('复制未完成，可选择来源文字手动复制','warning')}}}>复制来源信息</Button>{evidence.reviewUrl&&<Button component="a" href={evidence.reviewUrl}>转到此断言审核</Button>}</Stack></>}
  </Drawer>
  <Snackbar open={!!notice} autoHideDuration={notice?.severity==='error'?null:4500} onClose={()=>setNotice(null)} anchorOrigin={{vertical:'bottom',horizontal:'center'}}><Alert severity={notice?.severity||'success'} onClose={()=>setNotice(null)} sx={{maxWidth:'90vw'}}>{notice?.message}</Alert></Snackbar>
 </UIContext.Provider></ThemeProvider>;
}

export function useDirtyDraft({id,dirty,content,baseVersion,onRestore,onDiscard,title}) {
 const ui=useUI(),latest=useRef(null),[saved,setSaved]=useState(null);
 const key='hazmat-ui-draft:'+id;
 const stash=useCallback(()=>{storeValue(key,{content:latest.current.content,baseVersion:latest.current.baseVersion,at:new Date().toISOString()},sessionStorage);ui.notify('修改已暂存在当前浏览器，尚未提交审核')},[key,ui.notify]);
 latest.current={dirty,content,baseVersion,onDiscard};
 useEffect(()=>ui.registerGuard(key,()=>({dirty:latest.current.dirty,title,stash,discard:()=>{latest.current.dirty=false;latest.current.onDiscard?.()}})),[key,ui.registerGuard,title,stash]);
 useEffect(()=>{setSaved(readStored(key,null,sessionStorage))},[key]);
 const clear=useCallback(()=>{try{sessionStorage.removeItem(key)}catch{}setSaved(null)},[key]);
 const recovery=saved&&<Alert severity={saved.baseVersion===baseVersion?'info':'warning'} sx={{my:2}} action={<Stack direction="row"><Button onClick={()=>{onRestore(saved.content,saved.baseVersion!==baseVersion);setSaved(null)}}>恢复本机修改</Button><Button onClick={clear}>丢弃</Button></Stack>}>{saved.baseVersion===baseVersion?'发现尚未提交的本机暂存。':'服务端版本已变化；恢复后请对照最新原文和版本重新核对。'}</Alert>;
 return {stash,clear,recovery};
}
