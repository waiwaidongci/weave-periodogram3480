import sys,types
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from src.services import source as source_service
from src.services import plans as plan_service
from src.services import runs as run_service
from src.services import notes as note_service
from src.schemas.study import StudyInput
from src.schemas.plan import PlanInput
from src.schemas.run import RunInput
from src.schemas.note import NoteInput,ApprovalInput
from src.models import SpectrumRun,WeaveNote,TraversePoint
from src.services.analysis import analyze

def pts(n):
 import numpy as np
 r=np.random.default_rng(5);x=np.r_[0.,np.cumsum(r.uniform(.8,2.3,n-1))]
 y=.5+.075*np.cos(2*np.pi*x/18-.7)+r.normal(0,.014,n)
 return [{'reference':f'P{i:04d}','position':float(x[i]),'thickness':float(y[i])} for i in range(n)]

@pytest.fixture
def no_celery(monkeypatch):
 # 排队不依赖真实broker：拦截worker入队，直接在测试内同步执行analyze
 worker=types.ModuleType('src.worker')
 captured={}
 def fake_delay(run_id):captured['run_id']=run_id
 worker.analyze_run=types.SimpleNamespace(delay=fake_delay)
 monkeypatch.setitem(sys.modules,'src.worker',worker)
 return captured

def make_run(db,actor,no_celery,n=300):
 study=source_service.create_study(db,StudyInput(name='快照测线',filename='s.json',points=pts(n)),actor)
 plan_service.create_plan(db,PlanInput(study_id=study['id'],name='快照计划',protocol='看数据前固定周期范围10到90mm',min_frequency=1/90,max_frequency=.1,grid_size=201,permutations=199,seed=234),actor)
 plan=db.scalar(select(run_service.FrequencyPlan).where(run_service.FrequencyPlan.study_id==study['id']))
 summary=run_service.create_run(db,RunInput(study_id=study['id'],plan_id=plan.id,name='快照运行'),actor)
 run=db.get(SpectrumRun,summary['id'])
 # 模拟worker：用提交时快照计算并落结果
 result=analyze(run.source_snapshot['study'],run.source_snapshot['points'],run.plan_snapshot)
 run.result=result;run.peak_frequency=result['best']['frequency'];run.max_power=result['observed_max_power'];run.global_p=result['global_test']['global_p'];run.status='completed';db.commit()
 return study,run

def test_queued_snapshot_immune_to_later_revisions(db,actor,no_celery):
 study,run=make_run(db,actor,no_celery)
 original=run.source_snapshot['points']
 orig_fingerprint=run.result['fingerprint']
 # 排队后并发修订多个测点厚度与位置
 ids=db.scalars(select(TraversePoint.id).where(TraversePoint.study_id==study['id']).order_by(TraversePoint.position)).all()
 for k,pid in enumerate(ids[:25]):
  source_service.edit_point(db,pid,type('D',(),{'position':float(original[k]['position']),'thickness':0.9+0.001*k})(),actor)
 db.expire_all()
 run2=db.get(SpectrumRun,run.id)
 # 采用的测点（快照）原样保留，结果指纹不变
 assert run2.source_snapshot['points']==original
 assert run2.result['fingerprint']==orig_fingerprint
 assert run2.status=='completed'

def test_note_and_approval_kept_unchanged_after_revision(db,actor,no_celery):
 study,run=make_run(db,actor,no_celery)
 note_service.create_note(db,NoteInput(run_id=run.id,name='补测说明',interpretation='周期证据，非制造原因。',next_step='独立织片补测不等距位置。'),actor)
 note=db.scalar(select(WeaveNote).where(WeaveNote.run_id==run.id))
 note_service.approve_note(db,note.id,ApprovalInput(status='approved',review_note='批准，保持预设网格。'),'admin@lingdu.demo')
 approved_snapshot=note.result_snapshot
 # 事后修订测点
 ids=db.scalars(select(TraversePoint.id).where(TraversePoint.study_id==study['id']).order_by(TraversePoint.position)).all()
 source_service.edit_point(db,ids[0],type('D',(),{'position':run.source_snapshot['points'][0]['position'],'thickness':0.123})(),actor)
 db.expire_all()
 note2=db.get(WeaveNote,note.id);run2=db.get(SpectrumRun,run.id)
 # 批准状态、审核意见、批准快照、冻结结果全部原样保留
 assert note2.status=='approved' and note2.review_note=='批准，保持预设网格。'
 assert note2.result_snapshot==approved_snapshot
 assert note2.result_snapshot['fingerprint']==run2.result['fingerprint']
 # 重复审批409
 with pytest.raises(HTTPException) as ei:note_service.approve_note(db,note.id,ApprovalInput(status='rejected',review_note='退回重写'),'admin@lingdu.demo')
 assert ei.value.status_code==409

def test_run_summary_excludes_heavy_payloads(db,actor,no_celery):
 study,run=make_run(db,actor,no_celery,n=300)
 summary=run_service.run_summary(run)
 assert 'source_snapshot' not in summary and 'plan_snapshot' not in summary and 'result' not in summary
 assert summary['status']=='completed' and summary['global_p'] is not None
