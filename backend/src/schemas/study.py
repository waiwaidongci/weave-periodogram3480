from pydantic import BaseModel,Field,ConfigDict
from src.constants.numerics import MAX_POINTS,MAX_BATCH_POINTS
from .point import PointInput
class StudyInput(BaseModel):
 model_config=ConfigDict(str_strip_whitespace=True)
 name:str=Field(min_length=2,max_length=150)
 filename:str=Field(min_length=2,max_length=180)
 description:str=Field(default='',max_length=3000)
 points:list[PointInput]=Field(min_length=4,max_length=MAX_POINTS)
class ImportSessionInput(BaseModel):
 model_config=ConfigDict(str_strip_whitespace=True)
 name:str=Field(min_length=2,max_length=150)
 filename:str=Field(min_length=2,max_length=180)
 description:str=Field(default='',max_length=3000)
 expected_batches:int=Field(ge=1,le=100000,strict=True)
class BatchInput(BaseModel):
 # 乱序到达也按batch_index归档；重复或越界整批拒绝；单批≤10000点以控制请求体积
 batch_index:int=Field(ge=0,strict=True)
 points:list[PointInput]=Field(min_length=1,max_length=MAX_BATCH_POINTS)
class ImportCompleteInput(BaseModel):
 expected_batches:int|None=Field(default=None,ge=1,le=100000,strict=True)
