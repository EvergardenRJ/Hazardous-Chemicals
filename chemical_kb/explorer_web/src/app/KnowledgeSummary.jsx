import {useEffect,useState} from 'react';
import {Alert,Button} from '@mui/material';
import {ArrowRight,FileText} from 'lucide-react';
import {api} from '../api';
import '../dashboard.css';

export default function KnowledgeSummary({onNavigate}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{const controller=new AbortController();setError('');api('/api/dashboard/bootstrap',{signal:controller.signal}).then(setData).catch(e=>{if(e.name!=='AbortError')setError('知识库摘要暂时无法读取。')});return()=>controller.abort()},[retry]);
 return <section className="dashboard-workspace dashboard-summary" aria-labelledby="home-summary-title">
  <header className="dash-page-head"><div><h2 id="home-summary-title">危化品数据洞察</h2><p>资料结构、专题覆盖与可核实的知识关联。</p></div><Button onClick={()=>onNavigate('insights')}>查看完整数据洞察 <ArrowRight size={16}/></Button></header>
  {error&&<Alert severity="warning" action={<Button onClick={()=>setRetry(v=>v+1)}>重试</Button>}>{error}</Alert>}
  <div className="dash-snapshot-metrics" aria-busy={!data&&!error}>{[['documents','资料文档','doc_id 去重'],['chunks','原文片段','chunk_id 去重'],['wiki','Wiki 条目','包含草稿'],['news','新闻文章','排除已移除记录']].map(([key,label,note])=><div key={key}><FileText size={20}/><span>{label}<strong>{data?.totals?.[key]!=null?Number(data.totals[key]).toLocaleString('zh-CN'):'—'}</strong><small>{note}</small></span></div>)}<p>{data?'全库快照 · 各对象按自身口径去重':error?'请重试读取摘要':'正在读取知识库摘要…'}</p></div>
 </section>;
}
