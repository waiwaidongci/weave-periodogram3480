import numpy as np
from sqlalchemy import select
from fastapi import HTTPException
from src.models import FrequencyPlan,TraverseStudy
from src.utils.serialize import row
from .validation import validate_plan
from .audit import record

def create_plan(db,data,actor):
 study=db.get(TraverseStudy,data.study_id)
 if not study:raise HTTPException(404,'测线研究不存在')
 if study.status=='importing':raise HTTPException(409,'测线分批导入未完成，不能冻结频率计划')
 if db.scalar(select(FrequencyPlan).where(FrequencyPlan.name==data.name)):raise HTTPException(409,'计划名已存在')
 grid=np.linspace(data.min_frequency,data.max_frequency,data.grid_size).tolist();payload={**data.model_dump(),'frequencies':grid}
 try:validate_plan(payload)
 except ValueError as error:raise HTTPException(422,str(error))
 plan=FrequencyPlan(**payload,created_by=actor);db.add(plan);db.commit();record(db,actor,'plan.frozen',{'plan_id':plan.id,'grid_size':len(grid)});return row(plan)
