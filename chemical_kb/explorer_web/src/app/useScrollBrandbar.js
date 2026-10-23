import {useEffect,useState} from 'react';

export default function useScrollBrandbar(page,mainRef){
 const [hidden,setHidden]=useState(false);
 useEffect(()=>{
  setHidden(false);
  const positions=new WeakMap();let direction=0,distance=0,lockedUntil=0,current=false;
  const toggle=value=>{if(current===value)return;current=value;setHidden(value);lockedUntil=performance.now()+280;distance=0};
  const scroll=event=>{
   const target=event.target;if(!(target instanceof HTMLElement)||!target.matches('.workspace-scroll,.dashboard-workspace,.graph-page'))return;
   const top=target.scrollTop,previous=positions.get(target)||0;positions.set(target,top);
   if(top<=20){toggle(false);return}
   if(performance.now()<lockedUntil)return;
   const delta=top-previous;if(Math.abs(delta)<2)return;
   const nextDirection=Math.sign(delta);distance=nextDirection===direction?distance+Math.abs(delta):Math.abs(delta);direction=nextDirection;
   if(direction>0&&distance>=36&&top>60)toggle(true);
   if(direction<0&&distance>=16)toggle(false);
  };
  const focus=event=>{if(event.target.closest?.('.ui-topbar'))toggle(false)};
  const main=mainRef.current;main?.addEventListener('scroll',scroll,true);main?.addEventListener('focusin',focus);
  return()=>{main?.removeEventListener('scroll',scroll,true);main?.removeEventListener('focusin',focus)};
 },[page,mainRef]);
 return hidden;
}
