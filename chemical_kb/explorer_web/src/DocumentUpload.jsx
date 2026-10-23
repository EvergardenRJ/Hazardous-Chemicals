import { useEffect, useRef, useState } from 'react';
import { LoaderCircle, UploadCloud } from 'lucide-react';
import { api, post } from './api';
const STORAGE='hazchem-demo-upload';
const allowed=/\.(pdf|docx|doc|md|txt)$/i;
function savedJob(){try{return JSON.parse(sessionStorage.getItem(STORAGE)||'null')}catch{return null}}
export default function DocumentUpload({onCompleted}) {
 const inputRef=useRef(null),completeRef=useRef(onCompleted);
 completeRef.current=onCompleted;
 const [file,setFile]=useState(null),[busy,setBusy]=useState(false),[job,setJob]=useState(savedJob),[message,setMessage]=useState(''),[error,setError]=useState('');
 const running=!!job&&job.state!=='failed';
 function remember(value){setJob(value);try{if(value)sessionStorage.setItem(STORAGE,JSON.stringify(value));else sessionStorage.removeItem(STORAGE)}catch{}}
 useEffect(()=>{
  if(!job||job.state==='failed')return;
  let active=true,timer,controller=new AbortController();
  async function poll(){
   try{
    const data=await api('/api/demo/jobs',{signal:controller.signal});if(!active)return;
    const current=data.jobs.find(row=>row.id===job.id);
    if(!current){setError('任务暂未出现在最近记录中。请刷新后检查，避免重复上传。');return}
    if(current.state==='completed'){setMessage(job.filename+' 已入库，共 '+(current.result?.chunks??0)+' 个片段。');setError('');remember(null);completeRef.current?.();return}
    if(current.state==='failed'){setError(current.error||'后台处理失败，可重试。');remember({...job,state:'failed'});return}
    setMessage(job.filename+(current.state==='running'?' 正在解析、切片并建立索引…':' 已排队，等待后台处理…'));setError('');
   }catch(e){if(!active||e.name==='AbortError')return;setError('暂时无法读取处理进度：'+e.message)}
   if(active)timer=setTimeout(poll,3000);
  }
  poll();return()=>{active=false;clearTimeout(timer);controller.abort()};
 },[job?.id,job?.state]);
 async function upload(){
  if(!file||busy||running)return;setMessage('');setError('');
  if(!allowed.test(file.name)){setError('支持 PDF、DOCX、DOC、Markdown、TXT，请选择正确格式。');return}
  if(file.size>50*1024*1024){setError('文件超过 50 MB，请选择较小的文档。');return}
  setBusy(true);
  try{
   const body=new FormData();body.append('file',file);const result=await api('/api/documents/upload',{method:'POST',body});
   if(result.job_id){remember({id:result.job_id,filename:result.filename,state:'queued'});setMessage(result.filename+' 已提交后台处理…')}
   else setMessage(result.filename+' 已保存，请核对后台处理状态。');
   setFile(null);if(inputRef.current)inputRef.current.value='';
  }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function retry(){
  if(!job||busy)return;setBusy(true);setError('');
  try{await post('/api/demo/jobs/'+encodeURIComponent(job.id)+'/retry',{});remember({...job,state:'queued'})}
  catch(e){setError(e.message)}finally{setBusy(false)}
 }
 function selectFile(next){setFile(next);setError('');if(!running)setMessage('')}
 return <section className="dash-panel data-upload" aria-labelledby="data-upload-title" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy&&!running)selectFile(e.dataTransfer.files?.[0]||null)}}>
  <div className="data-upload-head"><div><span className="dash-kicker">资料接入</span><h2 id="data-upload-title">上传新文档</h2><p>上传后由后台自动解析、切片并建立检索索引；扫描 PDF 使用 OCR。可离开当前页面，返回后继续查看进度。</p></div><UploadCloud size={28} aria-hidden="true"/></div>
  <div className="data-upload-actions"><label className="data-upload-picker"><UploadCloud size={22}/><strong>{file?.name||'选择或拖入文档'}</strong><span>PDF、DOCX、DOC、Markdown、TXT，最大 50 MB</span><input ref={inputRef} type="file" disabled={busy||running} accept=".pdf,.docx,.doc,.md,.txt" onChange={e=>selectFile(e.target.files?.[0]||null)}/></label>
  <button className="dash-button dash-primary" type="button" onClick={upload} disabled={!file||busy||running}>{busy||running?<LoaderCircle className="spin" size={16}/>:<UploadCloud size={16}/>} {busy?'正在提交…':running?'后台处理中…':'上传并入库'}</button></div>
  {message&&<div className="dash-notice" role="status">{message}</div>}
  {error&&<div className="dash-error" role="alert">{error}</div>}
  {job?.state==='failed'&&<button className="dash-button" disabled={busy} onClick={retry}>重试后台处理</button>}
  <p className="dash-footnote">入库完成表示可检索原文，不代表已完成知识图谱抽取或人工审核。</p>
 </section>;
}
