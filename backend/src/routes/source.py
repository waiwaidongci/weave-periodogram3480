from fastapi import APIRouter,Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import get_db
from src.controllers.dependencies import current_user,writers
from src.models import TraverseStudy,TraversePoint
from src.schemas.study import StudyInput,ImportSessionInput,BatchInput,ImportCompleteInput
from src.schemas.point import PointPatch
from src.services.source import create_study,edit_point,start_import,upload_batch,complete_import,import_batches
from src.utils.serialize import row
router=APIRouter()
@router.get('/studies')
def studies(db:Session=Depends(get_db),user=Depends(current_user)):return [row(s) for s in db.scalars(select(TraverseStudy).order_by(TraverseStudy.id))]
@router.post('/studies')
def create(data:StudyInput,db:Session=Depends(get_db),user=Depends(writers)):return create_study(db,data,user.email)
@router.post('/studies/import-sessions')
def start(data:ImportSessionInput,db:Session=Depends(get_db),user=Depends(writers)):return start_import(db,data,user.email)
@router.post('/studies/{id}/batches')
def batch(id:int,data:BatchInput,db:Session=Depends(get_db),user=Depends(writers)):return upload_batch(db,id,data,user.email)
@router.post('/studies/{id}/complete')
def complete(id:int,data:ImportCompleteInput,db:Session=Depends(get_db),user=Depends(writers)):return complete_import(db,id,data,user.email)
@router.get('/studies/{id}/batches')
def batches(id:int,db:Session=Depends(get_db),user=Depends(current_user)):return import_batches(db,id)
@router.get('/points')
def points(study_id:int|None=None,limit:int=500,offset:int=0,db:Session=Depends(get_db),user=Depends(current_user)):
 stmt=select(TraversePoint).order_by(TraversePoint.study_id,TraversePoint.position)
 if study_id is not None:stmt=stmt.where(TraversePoint.study_id==study_id)
 limit=max(1,min(limit,5000));offset=max(0,offset)
 return [row(p) for p in db.scalars(stmt.limit(limit).offset(offset))]
@router.patch('/points/{id}')
def point(id:int,data:PointPatch,db:Session=Depends(get_db),user=Depends(writers)):return edit_point(db,id,data,user.email)
