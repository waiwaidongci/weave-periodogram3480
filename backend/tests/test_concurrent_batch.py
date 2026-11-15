import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from src.services import source as source_service
from src.schemas.study import ImportSessionInput,BatchInput
from src.models import TraversePoint,ImportBatch

def pts(n,start,ref):
 return [{'reference':f'{ref}-P{i:04d}','position':float(start+i*1.5),'thickness':0.5+0.01*i} for i in range(n)]

def test_duplicate_batch_index_is_rejected_and_keeps_points_atomic(db,actor):
 sid=source_service.start_import(db,ImportSessionInput(name='批次唯一',filename='c.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid,BatchInput(batch_index=0,points=pts(6,0,'A')),actor)
 # 显式重复提交同序号：409，测点数量不变
 with pytest.raises(HTTPException) as ei:source_service.upload_batch(db,sid,BatchInput(batch_index=0,points=pts(4,200,'C')),actor)
 assert ei.value.status_code==409
 assert db.scalar(select(func.count()).select_from(TraversePoint).where(TraversePoint.study_id==sid))==6
 assert db.scalar(select(func.count()).select_from(ImportBatch).where(ImportBatch.study_id==sid))==1

def test_integrity_conflict_path_returns_whole_batch_rejection(db,actor,monkeypatch):
 # 模拟并发下唯一约束在flush阶段才触发：服务层必须回滚并转成422整批拒绝
 sid=source_service.start_import(db,ImportSessionInput(name='约束冲突',filename='i.json',expected_batches=2),actor)['id']
 source_service.upload_batch(db,sid,BatchInput(batch_index=0,points=pts(5,0,'A')),actor)
 from sqlalchemy.exc import IntegrityError
 def boom(*a,**k):raise IntegrityError('insert',{},Exception('unique violation'))
 monkeypatch.setattr(db,'commit',boom)
 with pytest.raises(HTTPException) as ei:source_service.upload_batch(db,sid,BatchInput(batch_index=1,points=pts(5,100,'B')),actor)
 assert ei.value.status_code==422
 # 回滚后会话仍可用，且没有残留半截点
 db.rollback()
 assert db.scalar(select(func.count()).select_from(TraversePoint).where(TraversePoint.study_id==sid))==5
