import {useState,useEffect,useCallback,useRef} from 'react';import {researchApi} from '../api/research';import type {Run,Note} from '../types/domain';
const HEAVY=['result','source_snapshot','plan_snapshot'] as const;
export function useResearch(){const [runs,R]=useState<Run[]>([]),[notes,N]=useState<Note[]>([]),[researchError,E]=useState('');const loaded=useRef<Record<number,Run>>({}),attempted=useRef<Set<number>>(new Set());
const openRun=useCallback(async(id:number)=>{const full=await researchApi.run(id);loaded.current[id]=full;R(prev=>prev.map(r=>r.id===id?{...r,...full}:r));return full},[]);
const reloadResearch=useCallback(async()=>{try{const [r,n]=await Promise.all([researchApi.runs(),researchApi.notes()]);
 // 列表是轻量摘要；已按需打开过的运行保留其完整载荷，避免轮询把result冲掉
 const merged=r.map((s:Run)=>{const full=loaded.current[s.id];return full?{...s,...Object.fromEntries(HEAVY.map(k=>[k,(full as any)[k]]).filter(([,v])=>v!==undefined))}:s});
 R(merged);N(n);E('');
 // 总览页需要最新一册的完整结果：自动按需拉取一次（失败则下个轮询周期重试）
 const latest=merged.find((x:Run)=>x.status==='completed'&&!x.result);
 if(latest&&!attempted.current.has(latest.id)){attempted.current.add(latest.id);openRun(latest.id).catch(()=>{attempted.current.delete(latest.id)})}
}catch(e:any){E(e.message)}},[openRun]);
useEffect(()=>{reloadResearch();const t=setInterval(reloadResearch,2500);return()=>clearInterval(t)},[reloadResearch]);
return {runs,notes,researchError,reloadResearch,openRun}}
