import {useState,useEffect} from 'react';
import {PageTitle} from '../components/common/PageTitle';
import {Notice} from '../components/common/Notice';
import {Table} from '../components/common/Table';
import {Status} from '../components/common/Status';
import {TracePlot} from '../components/TracePlot';
import {useTask} from '../hooks/useTask';
import {catalogApi} from '../api/catalog';
import {fmt} from '../utils/format';
import {STUDY_STATUS} from '../constants/enums';

const example={name:'不等距纯十八毫米测线',filename:'ld-pure-irregular-18mm.json',description:'独立织片不等距厚度；预设网格包含1/18',points:[0,1.25,2.75,4.25,6,7.5,9.25,11.75,14,16.5,19.25,22,24.5,27.75,31,35].map((position,i)=>({reference:'UI-P'+String(i+1).padStart(2,'0'),position,thickness:.5+.08*Math.cos(2*Math.PI*position/18-.7)}))};

export function SourcePage({studies,points,user,reloadCatalog,loadPoints}:any){
 const [id,S]=useState(0),[raw,R]=useState(JSON.stringify(example,null,2)),task=useTask();
 const study=studies.find(s=>s.id===(id||studies[0]?.id));
 const rows=points.filter(p=>p.study_id===study?.id);
 const importing=study?.status==='importing';
 const [sessId,setSessId]=useState<number>(0),[expected,Eb]=useState(3),[batchIndex,Bi]=useState(0),[batchRaw,Br]=useState('[]'),[batches,setBatches]=useState<any[]>([]);
 useEffect(()=>{if(study?.id)loadPoints(study.id).catch(()=>{});setSessId(0);setBatches([])},[study?.id]);
 async function refreshBatches(sid:number){setBatches(await catalogApi.batches(sid))}
 return <><PageTitle index="02" title="让位置保持原样，让厚度留下来路。" description="不把不等距位置强制转换为等距FFT；跨批重复位置/编号整批拒绝，未完成导入不供研究。"/>
 <label>来源测线<select value={study?.id||''} onChange={e=>S(+e.target.value)}>{studies.map(s=><option key={s.id} value={s.id}>{s.name}{s.status==='importing'?'（导入中）':''}</option>)}</select></label>
 {study&&<p>{study.filename} / {study.description} {study.status&&<><br/><Status value={study.status}/> 批次 {study.received_batches}/{study.expected_batches} ｜ 已接收 {study.point_count??rows.length} 测点</>}</p>}
 <TracePlot points={rows} title="原始不等距厚度底稿（按测线按需加载，最多5000点预览）"/>
 <div className="source-layout">
  <section>
   <h2>观测底稿 / 前24点</h2>
   {importing&&<p className="error-text">分批导入未完成：不能冻结计划、排队研究或修订测点。</p>}
   <Table headers={['编号','位置 mm','厚度 mm','修订']}>{rows.slice(0,24).map(p=><tr key={p.id}><td>{p.reference}</td><td>{fmt(p.position,5)}</td><td>{fmt(p.thickness,7)}</td><td>{user.role!=='viewer'&&!importing&&<button onClick={()=>{const value=prompt('修订厚度mm',String(p.thickness));if(value!==null)task.act(async()=>{await catalogApi.editPoint(p.id,{position:p.position,thickness:+value});await loadPoints(study.id)},'原始测点已修订；既有任务保留提交时快照')}}>修订厚度</button>}</td></tr>)}</Table>
  </section>
  <section className="input-sheet">
   <small>NEW IRREGULAR TRAVERSE</small>
   <h2>导入独立织片测线</h2>
   <p>单次4–100000点、位置唯一、跨度≤10000mm；超过请求上限时用右侧分批导入。原始点可无序，后端按位置排序。</p>
   {user.role!=='viewer'?<form onSubmit={e=>{e.preventDefault();task.act(async()=>{const s=await catalogApi.createStudy(JSON.parse(raw));await reloadCatalog();S(s.id)},'测线研究已保存，可冻结预设频率计划')}}>
    <label>测线 JSON<textarea value={raw} onChange={e=>R(e.target.value)} rows={10}/></label>
    <button className="primary" disabled={task.busy}>保存不等距测线 →</button>
   </form>:<p>观察员只读底稿；测线导入与修订由分析员处理。</p>}
  </section>
  {user.role!=='viewer'&&<section className="input-sheet">
   <small>BATCHED IMPORT / 最多十万测点</small>
   <h2>分批导入与排队</h2>
   {!sessId?<form onSubmit={e=>{e.preventDefault();task.act(async()=>{const s=await catalogApi.startImport({name:(JSON.parse(raw).name)+' 分批',filename:JSON.parse(raw).filename,description:JSON.parse(raw).description||'',expected_batches:expected});setSessId(s.id);S(s.id);await reloadCatalog();await refreshBatches(s.id)},'导入会话已建立，状态为导入中')}}>
    <label>计划批次数<input type="number" min={1} value={expected} onChange={e=>Eb(+e.target.value)} required/></label>
    <p>先开会话，再按批次上传；批次可乱序到达，序号必须落在 0..批次数−1。</p>
    <button className="primary" disabled={task.busy}>建立导入会话 →</button>
   </form>:<>
    <p>会话 #{sessId}，已接收 {study?.received_batches}/{study?.expected_batches} 批；跨批重复位置或编号会整批拒绝且不写入任何点。</p>
    <form onSubmit={e=>{e.preventDefault();task.act(async()=>{await catalogApi.uploadBatch(sessId,{batch_index:batchIndex,points:JSON.parse(batchRaw)});await reloadCatalog();await refreshBatches(sessId);Br('[]')},'批次已接收；若含跨批重复则整批拒绝')}}>
     <label>批次序号 batch_index（可乱序）<input type="number" min={0} max={expected-1} value={batchIndex} onChange={e=>Bi(+e.target.value)} required/></label>
     <label>本批测点 JSON 数组<textarea value={batchRaw} onChange={e=>Br(e.target.value)} rows={8} placeholder='[{"reference":"B0-P0001","position":0,"thickness":0.5}]'/></label>
     <button className="primary" disabled={task.busy}>上传该批次 →</button>
    </form>
    <Table headers={['批次','测点数']}>{batches.map(b=><tr key={b.id}><td>{b.batch_index}</td><td>{b.point_count}</td></tr>)}</Table>
    <button disabled={task.busy} onClick={()=>task.act(async()=>{const s=await catalogApi.completeImport(sessId);setSessId(0);await reloadCatalog();S(s.id);if(study)await loadPoints(s.id)},'全部批次到齐，导入完成，可冻结计划与排队研究')}>完成导入 →</button>
   </>}
  </section>}
 </div>
 <Notice {...task}/>
 </>}
