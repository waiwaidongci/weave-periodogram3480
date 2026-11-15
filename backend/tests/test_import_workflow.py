import pytest
from fastapi import HTTPException
from src.services import source as source_service
from src.schemas.study import StudyInput,ImportSessionInput,BatchInput,ImportCompleteInput
from src.schemas.point import PointPatch
from src.models import TraversePoint,ImportBatch
from sqlalchemy import select,func
from src.services import plans as plan_service
from src.schemas.plan import PlanInput
from src.services import runs as run_service
from src.schemas.run import RunInput
from src.constants import numerics

def pts(n,start=0,step=1.0,ref='B'):
 return [{'reference':f'{ref}-P{i:04d}','position':float(start+i*step),'thickness':0.5+0.01*i} for i in range(n)]
def batch(i,rows):return BatchInput(batch_index=i,points=rows)

def test_full_batched_import_out_of_order(db,actor):
 sess=source_service.start_import(db,ImportSessionInput(name='分批测线',filename='b.json',description='',expected_batches=3),actor)
 sid=sess['id']
 # 乱序到达：先批2再批0再批1
 source_service.upload_batch(db,sid,batch(2,pts(10,start=20,ref='C')),actor)
 source_service.upload_batch(db,sid,batch(0,pts(10,start=0,ref='A')),actor)
 s=source_service.upload_batch(db,sid,batch(1,pts(10,start=10,ref='B')),actor)
 assert s['received_batches']==3 and s['status']=='importing'
 got=source_service.import_batches(db,sid)
 assert [b['batch_index'] for b in got]==[0,1,2]
 done=source_service.complete_import(db,sid,ImportCompleteInput(),actor)
 assert done['status']=='ready' and done['point_count']==30
 assert db.scalar(select(func.count()).select_from(TraversePoint).where(TraversePoint.study_id==sid))==30

def test_cross_batch_duplicate_position_rejects_whole_batch(db,actor):
 sid=source_service.start_import(db,ImportSessionInput(name='重复位置',filename='d.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid,batch(0,pts(8,ref='A')),actor)
 before=db.scalar(select(func.count()).select_from(TraversePoint).where(TraversePoint.study_id==sid))
 # 第二批含一个与第一批相同的位置（其余全新）：整批拒绝，一个点都不写
 dup=pts(5,start=7,ref='D')
 with pytest.raises(HTTPException) as ei:source_service.upload_batch(db,sid,batch(1,dup),actor)
 assert ei.value.status_code==422
 after=db.scalar(select(func.count()).select_from(TraversePoint).where(TraversePoint.study_id==sid))
 assert before==after==8
 # 同一批内重复位置也整批拒绝
 with pytest.raises(HTTPException):source_service.upload_batch(db,sid,batch(1,pts(4,ref='E')+[{'reference':'X','position':0.0,'thickness':1.0}]),actor)

def test_cross_batch_duplicate_reference_rejects_whole_batch(db,actor):
 sid=source_service.start_import(db,ImportSessionInput(name='重复编号',filename='r.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid,batch(0,pts(6,ref='R')),actor)
 bad=[{'reference':'R-P0000','position':500.0,'thickness':1.0},{'reference':'Z-1','position':501.0,'thickness':1.0}]
 with pytest.raises(HTTPException) as ei:source_service.upload_batch(db,sid,batch(1,bad),actor)
 assert ei.value.status_code==422
 assert db.scalar(select(func.count()).select_from(TraversePoint).where(TraversePoint.study_id==sid))==6

def test_resubmit_same_batch_index_rejected(db,actor):
 sid=source_service.start_import(db,ImportSessionInput(name='重复批次',filename='x.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid,batch(0,pts(5,ref='A')),actor)
 with pytest.raises(HTTPException) as ei:source_service.upload_batch(db,sid,batch(0,pts(5,start=100,ref='B')),actor)
 assert ei.value.status_code==409
 with pytest.raises(HTTPException) as ei:source_service.upload_batch(db,sid,BatchInput(batch_index=5,points=pts(4,ref='C')),actor)
 assert ei.value.status_code==422

def test_incomplete_import_blocked_from_plan_run_edit(db,actor):
 sid=source_service.start_import(db,ImportSessionInput(name='未完成',filename='u.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid,batch(0,pts(20,ref='A')),actor)
 # 未完成不能冻结计划
 with pytest.raises(HTTPException) as ei:
  plan_service.create_plan(db,PlanInput(study_id=sid,name='计划P',protocol='看数据前固定范围',min_frequency=1/90,max_frequency=.1,grid_size=201,permutations=199,seed=234),actor)
 assert ei.value.status_code==409
 # 未完成不能排队（计划不存在也先被导入状态拦截）
 with pytest.raises(HTTPException):run_service.create_run(db,RunInput(study_id=sid,plan_id=999,name='运行R'),actor)
 # 未完成不能修订测点
 pid=db.scalar(select(TraversePoint.id).where(TraversePoint.study_id==sid))
 with pytest.raises(HTTPException) as ei:source_service.edit_point(db,pid,PointPatch(position=0.0,thickness=0.9),actor)
 assert ei.value.status_code==409
 # 缺批不能完成
 with pytest.raises(HTTPException):source_service.complete_import(db,sid,ImportCompleteInput(),actor)
 source_service.upload_batch(db,sid,batch(1,pts(20,start=100,ref='B')),actor)
 done=source_service.complete_import(db,sid,ImportCompleteInput(),actor)
 assert done['status']=='ready'

def test_span_and_total_limit_enforced_across_batches(db,actor,monkeypatch):
 monkeypatch.setattr(numerics,'MAX_POINTS',50)
 monkeypatch.setattr('src.services.source.MAX_POINTS',50)
 sid=source_service.start_import(db,ImportSessionInput(name='超限',filename='m.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid,batch(0,pts(30,ref='A')),actor)
 with pytest.raises(HTTPException) as ei:source_service.upload_batch(db,sid,batch(1,pts(30,start=100,ref='B')),actor)
 assert ei.value.status_code==422
 # 跨度超10000：第一批自身在范围内，第二批把总跨度顶破
 sid2=source_service.start_import(db,ImportSessionInput(name='跨距',filename='s.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid2,batch(0,[{'reference':f'A{i}','position':float(i),'thickness':0.5} for i in range(5)]),actor)
 with pytest.raises(HTTPException):source_service.upload_batch(db,sid2,batch(1,[{'reference':f'B{i}','position':10001.0+i,'thickness':0.5} for i in range(5)]),actor)

def test_single_study_imports_and_point_count(db,actor):
 s=source_service.create_study(db,StudyInput(name='单次',filename='o.json',points=pts(12)),actor)
 assert s['status']=='ready' and s['point_count']==12 and s['expected_batches']==1
 assert db.scalar(select(func.count()).select_from(ImportBatch).where(ImportBatch.study_id==s['id']))==1
