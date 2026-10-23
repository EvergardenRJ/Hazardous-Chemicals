export const routeKeys = ['chemical','entity_id','as_of','wiki','section','view','revision','focus_id','mode','conversation_id','chemicalView','dashboard','article'];
export function readRoute() {
  const url = new URL(location.href);
  const raw = url.hash.slice(1) || 'overview';
  return {page:({resolve:'review','review-entities':'review',library:'data'})[raw]||raw, governanceTab:['resolve','review-entities'].includes(raw)?'entities':'assertions',params:Object.fromEntries(url.searchParams)};
}
export function routeUrl(page, changes={}, {clean=false}={}) {
  const url = new URL(location.href);
  if(clean) for(const key of routeKeys) if(!['as_of'].includes(key)) url.searchParams.delete(key);
  for(const [key,value] of Object.entries(changes)) value==null||value===''?url.searchParams.delete(key):url.searchParams.set(key,value);
  url.hash=page;
  return url;
}
export function commitRoute(url, replace=false) {
  if(url.href!==location.href) history[replace?'replaceState':'pushState']({},'',url);
  window.dispatchEvent(new Event('workspace:navigate'));
}
export function savePosition() {
  try { const el=document.querySelector('.workspace-scroll,.dashboard-workspace,.graph-page');const positions=JSON.parse(sessionStorage.getItem('ui-scroll-positions')||'{}');positions[location.href]=el?.scrollTop||0;sessionStorage.setItem('ui-scroll-positions',JSON.stringify(Object.fromEntries(Object.entries(positions).slice(-60)))); } catch {}
}
export function restorePosition(){
 let top;try{top=JSON.parse(sessionStorage.getItem('ui-scroll-positions')||'{}')[location.href]}catch{}if(top==null)return()=>{};
 let stopped=false;const stop=()=>{stopped=true;observer.disconnect();clearTimeout(timeout);window.removeEventListener('wheel',stop);window.removeEventListener('pointerdown',stop)};
 const restore=()=>{if(stopped)return;const el=document.querySelector('.workspace-scroll,.dashboard-workspace,.graph-page');if(el&&el.scrollHeight-el.clientHeight>=top){el.scrollTop=top;stop()}};
 const observer=new MutationObserver(restore),timeout=setTimeout(stop,20000);observer.observe(document.querySelector('.ui-main')||document.body,{subtree:true,childList:true});window.addEventListener('wheel',stop,{passive:true});window.addEventListener('pointerdown',stop,{passive:true});requestAnimationFrame(restore);return stop;
}
