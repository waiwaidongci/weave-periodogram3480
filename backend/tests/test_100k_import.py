import numpy as np
from sqlalchemy import select,func
from src.services import source as source_service
from src.services import plans as plan_service
from src.schemas.study import ImportSessionInput,BatchInput,ImportCompleteInput
from src.schemas.plan import PlanInput
from src.models import TraversePoint,FrequencyPlan
from src.services.analysis import analyze
from src.constants.numerics import MAX_POINTS

def make_batch(rng,start_idx,count,pos_lo,pos_hi,prefix):
 # 区间内唯一随机位置，跨度受控
 pos=np.sort(rng.uniform(pos_lo,pos_hi,count))
 return [{'reference':f'{prefix}-P{start_idx+i:06d}','position':float(pos[i]),'thickness':float(0.5+0.05*rng.uniform())} for i in range(count)]

def test_100k_batched_import_full_flow(db,actor):
 rng=np.random.default_rng(2026)
 n_batches=10;per=MAX_POINTS//n_batches  # 每批10000，共100000
 sid=source_service.start_import(db,ImportSessionInput(name='十万测点测线',filename='huge.json',expected_batches=n_batches),actor)['id']
 order=list(range(n_batches));rng.shuffle(order)  # 乱序提交
 # 把0..10000mm切成10个不相交位置区间，保证跨批位置不冲突
 for bi in order:
  rows=make_batch(rng,bi*per,per,bi*1000.0,(bi+1)*1000.0-0.01,f'B{bi}')
  s=source_service.upload_batch(db,sid,BatchInput(batch_index=bi,points=rows),actor)
  assert s['point_count']<=MAX_POINTS
 # 单批超过10000点会被schema/校验拒绝（请求体上限）
 try:
  BatchInput(batch_index=0,points=make_batch(rng,0,10001,0,9000,'Z'))
  assert False
 except Exception:pass
 # 完成主会话（恰好十万点边界合法）
 done=source_service.complete_import(db,sid,ImportCompleteInput(),actor)
 assert done['status']=='ready' and done['point_count']==MAX_POINTS
 total=db.scalar(select(func.count()).select_from(TraversePoint).where(TraversePoint.study_id==sid))
 assert total==MAX_POINTS
 # 完成后可冻结计划并分析（走流式引擎，结果结构完整）
 plan_service.create_plan(db,PlanInput(study_id=sid,name='十万测线计划',protocol='看数据前固定周期范围10到90mm',min_frequency=1/90,max_frequency=.1,grid_size=201,permutations=199,seed=234),actor)
 plan=db.scalar(select(FrequencyPlan).where(FrequencyPlan.study_id==sid))
 study,points=source_service.source_data(db,sid)
 assert len(points)==MAX_POINTS
 r=analyze(study,points,{'name':plan.name,'protocol':plan.protocol,'min_frequency':plan.min_frequency,'max_frequency':plan.max_frequency,'grid_size':plan.grid_size,'frequencies':plan.frequencies,'permutations':plan.permutations,'seed':plan.seed})
 assert r['engine']=='streaming-blocked-v1'
 assert len(r['fit'])==MAX_POINTS and len(r['spectrum'])==201 and len(r['global_test']['null_maxima'])==199
