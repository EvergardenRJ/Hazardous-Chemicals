import { useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, ChevronLeft, ChevronRight, Clock3, Search, Star, X } from 'lucide-react';

export const PAGE_TYPES = {chemical:'化学品',equipment:'设备',concept:'概念',topic:'专题',source:'资料摘要',query:'问答专题',research:'研究',accident:'事故',standard:'标准'};
export function normalizeQuery(value) {
  return String(value||'').normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,'').trim();
}
export function readLocalList(key) {
  try { const value=JSON.parse(localStorage.getItem(key)||'[]'); return Array.isArray(value)?value.filter(v=>typeof v==='string').slice(0,200):[]; } catch { return []; }
}
export function saveLocalList(key, list) {
  try { localStorage.setItem(key,JSON.stringify(list)); } catch { /* Reading remains available without browser storage. */ }
}

export default function WikiCatalog({entries,entity,input,setInput,pageType,setPageType,filter,setFilter,favorites,recent,onOpen,onGenerate,onSearch,busy}) {
  const [scope,setScope]=useState('all'),[sort,setSort]=useState('name'),[page,setPage]=useState(1),[expanded,setExpanded]=useState(false);
  const listRef=useRef(null),searchRef=useRef(null);
  const counts=useMemo(()=>entries.reduce((out,e)=>{const key=e.page_type||'chemical';out[key]=(out[key]||0)+1;return out},{}),[entries]);
  const visible=useMemo(()=>{
    const q=normalizeQuery(input);
    const filtered=entries.filter(e=>(pageType==='all'||(e.page_type||'chemical')===pageType)
      &&(filter==='all'||(filter==='pending'&&e.review_counts?.pending>0)||(filter==='published'&&e.published_revision)||(filter==='stale'&&e.freshness!=='fresh'))
      &&(scope==='all'||(scope==='favorites'&&favorites.includes(e.entity))||(scope==='recent'&&recent.includes(e.entity)))
      &&normalizeQuery(e.entity).includes(q));
    return filtered.sort((a,b)=>scope==='recent'?recent.indexOf(a.entity)-recent.indexOf(b.entity):sort==='updated'?String(b.updated_at||'').localeCompare(String(a.updated_at||'')):a.entity.localeCompare(b.entity,'zh-CN',{numeric:true}));
  },[entries,pageType,filter,scope,input,sort,favorites,recent]);
  const pages=Math.max(1,Math.ceil(visible.length/40)),safePage=Math.min(page,pages);
  const rows=visible.slice((safePage-1)*40,safePage*40);
  useEffect(()=>setPage(1),[input,pageType,filter,scope,sort]);
  useEffect(()=>{listRef.current?.scrollTo(0,0)},[safePage]);
  useEffect(()=>{
    function key(e) {
      if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)&&!e.target.isContentEditable) {
        e.preventDefault();setExpanded(true);searchRef.current?.focus();
      }
    }
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[]);
  const exact=entries.find(e=>normalizeQuery(e.entity)===normalizeQuery(input));
  function openRow(e) { onOpen(e.entity,e.published_revision?'published':'draft');setExpanded(false); }
  return <aside className={'panel wiki-registry wiki-registry--new '+(expanded?'is-expanded':'')}>
    <button className="wiki-catalog-toggle" aria-expanded={expanded} aria-controls="wiki-catalog-body" onClick={()=>setExpanded(v=>!v)}><BookOpen size={17}/><strong>浏览条目</strong><span>{entries.length.toLocaleString('zh-CN')} 项</span><ChevronRight size={16}/></button>
    <div className="wiki-catalog-body" id="wiki-catalog-body">
      <div className="wiki-catalog-heading"><h2>条目目录</h2><span>{entries.length.toLocaleString('zh-CN')} 项</span></div>
      <label className="search-field wiki-catalog-search"><Search size={16}/><input ref={searchRef} value={input} onChange={e=>setInput(e.target.value)} placeholder="搜索条目名称" aria-label="搜索 Wiki" onKeyDown={e=>{if(e.key==='Enter'&&exact)openRow(exact)}}/>{input?<button type="button" onClick={()=>{setInput('');searchRef.current?.focus()}} aria-label="清空条目搜索"><X size={14}/></button>:<kbd>/</kbd>}</label>
      <div className="wiki-catalog-selects"><select value={pageType} onChange={e=>setPageType(e.target.value)} aria-label="Wiki 页面类型"><option value="all">全部类型 · {entries.length}</option>{Object.entries(PAGE_TYPES).filter(([key])=>counts[key]).map(([key,label])=><option key={key} value={key}>{label} · {counts[key]}</option>)}</select><select value={filter} onChange={e=>setFilter(e.target.value)} aria-label="条目状态"><option value="all">全部状态</option><option value="pending">草稿</option><option value="published">已发布</option><option value="stale">来源有变化</option></select></div>
      <div className="wiki-catalog-scopes" role="group" aria-label="目录范围">{[['all','全部',BookOpen],['favorites','收藏',Star],['recent','最近',Clock3]].map(([id,label,Icon])=><button key={id} aria-pressed={scope===id} className={scope===id?'active':''} onClick={()=>{setScope(id);if(id!=='all'){setPageType('all');setFilter('all');setInput('')}}}><Icon size={13}/>{label}</button>)}</div>
      <div className="wiki-catalog-count"><span aria-live="polite">找到 {visible.length.toLocaleString('zh-CN')} 项</span><select value={sort} onChange={e=>setSort(e.target.value)} aria-label="目录排序" disabled={scope==='recent'}><option value="name">按名称</option><option value="updated">最近更新</option></select></div>
      <div className="wiki-catalog" ref={listRef}>{rows.map(e=><button className={'wiki-catalog-entry '+(e.entity===entity?'active':'')} aria-current={e.entity===entity?'page':undefined} key={e.wiki_id||e.entity} onClick={()=>openRow(e)} onKeyDown={event=>{if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const buttons=[...listRef.current.querySelectorAll('.wiki-catalog-entry')];const index=buttons.indexOf(event.currentTarget);buttons[Math.max(0,Math.min(buttons.length-1,index+(event.key==='ArrowDown'?1:-1)))]?.focus()}}}><span className="wiki-catalog-entry-name"><strong>{e.entity}</strong>{favorites.includes(e.entity)&&<Star size={12} className="wiki-saved-star" aria-label="已收藏"/>}</span><small>{PAGE_TYPES[e.page_type]||'条目'}<span>{e.section_count||0} 节</span></small></button>)}
      {!visible.length&&<div className="wiki-catalog-empty"><Search size={23}/><strong>{scope==='favorites'?'还没有收藏条目':scope==='recent'?'还没有阅读记录':'没有匹配条目'}</strong><p>{scope==='favorites'?'打开条目后，点击标题旁的收藏按钮。':'试试其他名称，或清除筛选条件。'}</p><button onClick={()=>{setInput('');setPageType('all');setFilter('all');setScope('all')}}>清除筛选</button></div>}</div>
      {visible.length>40&&<div className="wiki-catalog-pagination"><button aria-label="目录上一页" disabled={safePage===1} onClick={()=>setPage(safePage-1)}><ChevronLeft size={16}/></button><span>{safePage} / {pages}</span><button aria-label="目录下一页" disabled={safePage===pages} onClick={()=>setPage(safePage+1)}><ChevronRight size={16}/></button></div>}
      {input.trim()&&<div className="wiki-catalog-create"><button className="button button--quiet" disabled={busy} onClick={()=>exact?openRow(exact):onGenerate()}><BookOpen size={14}/>{exact?'打开匹配条目':'生成新条目草稿'}</button><button className="wiki-inline-link" disabled={busy} onClick={onSearch}>检索已发布正文</button></div>}
      <p className="wiki-catalog-local">收藏与最近阅读保存在当前浏览器</p>
    </div>
  </aside>;
}
