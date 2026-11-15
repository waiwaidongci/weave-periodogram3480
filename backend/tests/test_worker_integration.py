import os, json, tempfile
import numpy as np
from sqlalchemy import select
from src.services import source as source_service
from src.services import plans as plan_service
from src.schemas.study import StudyInput
from src.schemas.plan import PlanInput
from src.models import SpectrumRun,FrequencyPlan,TraversePoint
from src.utils.serialize import row
import src.config.settings as settings
from src import worker

def pts(n,constant=False):
 r=np.random.default_rng(5);hi=min(2.3,9000.0/max(n,1));lo=min(0.8,hi*0.35)
 x=np.r_[0.,np.cumsum(r.uniform(lo,hi,n-1))]
 y=np.full(n,0.5) if constant else .5+.075*np.cos(2*np.pi*x/18-.7)+r.normal(0,.014,n)
 return [{'reference':f'P{i:05d}','position':float(x[i]),'thickness':float(y[i])} for i in range(n)]

def _queue(db,actor,n,constant=False):
 study=source_service.create_study(db,StudyInput(name=f'W{n}{constant}',filename='w.json',points=pts(n,constant)),actor)
 plan_service.create_plan(db,PlanInput(study_id=study['id'],name=f'WP{n}',protocol='看数据前固定周期范围10到90mm',min_frequency=1/90,max_frequency=.1,grid_size=201,permutations=199,seed=234),actor)
 from src.models import FrequencyPlan
 plan=db.scalar(select(FrequencyPlan).where(FrequencyPlan.study_id==study['id']))
 points=[row(p) for p in db.scalars(select(TraversePoint).where(TraversePoint.study_id==study['id']))]
 run=SpectrumRun(study_id=study['id'],plan_id=plan.id,name=f'WR{n}{constant}',source_snapshot={'study':study,'points':points},plan_snapshot=row(plan),status='queued',created_by=actor)
 db.add(run);db.commit();return run.id

def test_worker_completes_and_writes_artifact(db,actor,monkeypatch):
 d=tempfile.mkdtemp();monkeypatch.setattr(settings,'ARTIFACT_DIR',d);monkeypatch.setattr(worker,'ARTIFACT_DIR',d)
 rid=_queue(db,actor,300)
 worker.analyze_run(rid)  # 直接调用任务函数，不经过broker
 run=db.get(SpectrumRun,rid)
 assert run.status=='completed' and run.global_p is not None and run.peak_frequency is not None
 blob=json.loads(open(os.path.join(d,f'weave-{rid}.json'),encoding='utf-8').read())
 assert blob['fingerprint']==run.result['fingerprint'] and len(blob['fit'])==300
 assert len(blob['global_test']['null_maxima'])==199

def test_worker_failure_marks_failed(db,actor,monkeypatch):
 d=tempfile.mkdtemp();monkeypatch.setattr(settings,'ARTIFACT_DIR',d);monkeypatch.setattr(worker,'ARTIFACT_DIR',d)
 rid=_queue(db,actor,200,constant=True)  # 恒厚RSS0=0
 worker.analyze_run(rid)
 run=db.get(SpectrumRun,rid)
 assert run.status=='failed' and 'RSS0' in (run.error or '')

def test_worker_uses_streaming_for_large_run(db,actor,monkeypatch):
 d=tempfile.mkdtemp();monkeypatch.setattr(settings,'ARTIFACT_DIR',d);monkeypatch.setattr(worker,'ARTIFACT_DIR',d)
 rid=_queue(db,actor,25000)
 worker.analyze_run(rid)
 run=db.get(SpectrumRun,rid)
 assert run.status=='completed',run.error
 assert run.result['engine']=='streaming-blocked-v1'
 assert len(run.result['spectrum'])==201 and len(run.result['fit'])==25000
