from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models import TraverseStudy,TraversePoint,ImportBatch
from src.utils.serialize import row
from .validation import validate_points,validate_batch
from .audit import record
from src.constants.numerics import MAX_POINTS,MIN_POINTS,MAX_SPAN_MM

def _get_study(db,id):
 study=db.get(TraverseStudy,id)
 if not study:raise HTTPException(404,'测线研究不存在')
 return study

def create_study(db,data,actor):
 if db.scalar(select(TraverseStudy).where(TraverseStudy.name==data.name)):raise HTTPException(409,'测线研究名已存在')
 try:points=validate_points([p.model_dump() for p in data.points])
 except ValueError as error:raise HTTPException(422,str(error))
 study=TraverseStudy(**data.model_dump(exclude={'points'}),status='ready',expected_batches=1,received_batches=1,point_count=len(points))
 db.add(study);db.flush()
 db.add_all([TraversePoint(study_id=study.id,**point) for point in points])
 db.add(ImportBatch(study_id=study.id,batch_index=0,point_count=len(points),created_by=actor))
 db.commit();record(db,actor,'study.imported',{'study_id':study.id,'points':len(points),'mode':'single'});return row(study)

def start_import(db,data,actor):
 if db.scalar(select(TraverseStudy).where(TraverseStudy.name==data.name)):raise HTTPException(409,'测线研究名已存在')
 study=TraverseStudy(name=data.name,filename=data.filename,description=data.description,status='importing',expected_batches=data.expected_batches,received_batches=0,point_count=0)
 db.add(study);db.commit();record(db,actor,'import.started',{'study_id':study.id,'expected_batches':study.expected_batches})
 return row(study)

def upload_batch(db,id,data,actor):
 study=_get_study(db,id)
 if study.status!='importing':raise HTTPException(409,'测线导入已完成，不能再追加批次')
 if data.batch_index>=study.expected_batches:raise HTTPException(422,'批次序号超出声明的批次数，整批拒绝')
 if db.scalar(select(ImportBatch).where(ImportBatch.study_id==id,ImportBatch.batch_index==data.batch_index)):raise HTTPException(409,'该批次已接收，重复提交整批拒绝')
 batch=[p.model_dump() for p in data.points]
 try:validate_batch(batch)
 except ValueError as error:raise HTTPException(422,str(error))
 # 跨批重复位置/编号：对照已落库测点，任一冲突整批拒绝，本批不写入任何点
 existing_refs=set(db.scalars(select(TraversePoint.reference).where(TraversePoint.study_id==id)).all())
 existing_pos=np_positions(db,id)
 incoming_refs={p['reference'] for p in batch}
 if incoming_refs & existing_refs:raise HTTPException(422,'测点编号与已导入批次重复，整批拒绝')
 incoming_pos=[p['position'] for p in batch]
 if any(p in existing_pos for p in incoming_pos):raise HTTPException(422,'位置与已导入批次重复，整批拒绝')
 if study.point_count+len(batch)>MAX_POINTS:raise HTTPException(422,f'测线测点总数不能超过{MAX_POINTS}，整批拒绝')
 # 全量跨度（含历史批次）复核
 all_pos=existing_pos+incoming_pos
 if max(all_pos)-min(all_pos)>MAX_SPAN_MM:raise HTTPException(422,f'测线跨度≤{MAX_SPAN_MM}mm，整批拒绝')
 try:
  db.add_all([TraversePoint(study_id=id,**point) for point in batch])
  db.add(ImportBatch(study_id=id,batch_index=data.batch_index,point_count=len(batch),created_by=actor))
  study.received_batches+=1;study.point_count+=len(batch)
  db.commit()
 except IntegrityError:
  # 并发提交同序号/同唯一键：整批回滚，不写入任何点
  db.rollback();raise HTTPException(422,'批次与在途提交冲突（序号或唯一键重复），整批拒绝')
 record(db,actor,'import.batch',{'study_id':id,'batch_index':data.batch_index,'points':len(batch)})
 return row(study)

def np_positions(db,id):
 return [float(v) for v in db.scalars(select(TraversePoint.position).where(TraversePoint.study_id==id)).all()]

def complete_import(db,id,data,actor):
 study=_get_study(db,id)
 if study.status!='importing':raise HTTPException(409,'测线导入已完成')
 expected=data.expected_batches if data.expected_batches is not None else study.expected_batches
 if expected!=study.expected_batches:raise HTTPException(422,'声明批次数与导入会话不一致')
 if study.received_batches<study.expected_batches:raise HTTPException(409,f'尚有批次未接收（{study.received_batches}/{study.expected_batches}），不能完成导入')
 # 序号连续性：0..expected-1 全部到齐（乱序到达也允许）
 got=set(db.scalars(select(ImportBatch.batch_index).where(ImportBatch.study_id==id)).all())
 if got!=set(range(study.expected_batches)):raise HTTPException(409,'批次序号不连续，不能完成导入')
 if study.point_count<MIN_POINTS:raise HTTPException(422,f'完成导入至少需要{MIN_POINTS}个测点')
 # 终态全量校验（唯一性、跨度、范围）
 points=[row(p) for p in db.scalars(select(TraversePoint).where(TraversePoint.study_id==id))]
 try:validate_points(points)
 except ValueError as error:raise HTTPException(422,str(error))
 study.status='ready';db.commit();record(db,actor,'import.completed',{'study_id':id,'points':study.point_count,'batches':study.received_batches})
 return row(study)

def import_batches(db,id):
 _get_study(db,id)
 return [row(b) for b in db.scalars(select(ImportBatch).where(ImportBatch.study_id==id).order_by(ImportBatch.batch_index))]

def source_data(db,id):
 study=_get_study(db,id)
 return row(study),[row(p) for p in db.scalars(select(TraversePoint).where(TraversePoint.study_id==id).order_by(TraversePoint.position))]

def edit_point(db,id,data,actor):
 point=db.get(TraversePoint,id)
 if not point:raise HTTPException(404,'测点不存在')
 study=_get_study(db,point.study_id)
 if study.status=='importing':raise HTTPException(409,'测线导入未完成，不能修订测点')
 _,points=source_data(db,point.study_id);candidate=[dict(p,position=data.position,thickness=data.thickness) if p['id']==id else p for p in points]
 try:validate_points(candidate)
 except ValueError as error:raise HTTPException(422,str(error))
 point.position=data.position;point.thickness=data.thickness;db.commit();record(db,actor,'point.revised',{'point_id':id});return row(point)
