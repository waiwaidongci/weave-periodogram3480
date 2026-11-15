import numpy as np
from src.constants.numerics import MIN_POINTS,MAX_POINTS,MAX_BATCH_POINTS,MAX_SPAN_MM

def _arrays(points):
 if any(type(p['position']) is bool or type(p['thickness']) is bool for p in points):raise ValueError('数值不能是bool')
 x=np.asarray([p['position'] for p in points],dtype=float);y=np.asarray([p['thickness'] for p in points],dtype=float)
 if not np.isfinite(x).all() or not np.isfinite(y).all() or (x<0).any() or (x>1e12).any() or (y<0).any() or (y>1e6).any():raise ValueError('位置/厚度须有限且在允许范围')
 return x,y

def validate_batch(points):
 # 单批校验：只做范围与批内唯一性；跨批冲突由导入会话对照已存点整批拒绝
 if not points:raise ValueError('批次至少包含1个测点')
 if len(points)>MAX_BATCH_POINTS:raise ValueError(f'单批测点不能超过{MAX_BATCH_POINTS}个')
 refs=[p['reference'] for p in points]
 if len(set(refs))!=len(refs):raise ValueError('批次内测点编号重复，整批拒绝')
 x,_=_arrays(points)
 if len(set(x.tolist()))!=len(x):raise ValueError('批次内位置重复，整批拒绝')
 if np.ptp(x)>MAX_SPAN_MM:raise ValueError(f'测线跨度≤{MAX_SPAN_MM}mm')
 return points

def validate_points(points):
 if not MIN_POINTS<=len(points)<=MAX_POINTS or len({p['reference'] for p in points})!=len(points):raise ValueError(f'需要{MIN_POINTS}..{MAX_POINTS}个唯一测点编号')
 x,_=_arrays(points)
 if len(set(x.tolist()))!=len(x) or np.ptp(x)>MAX_SPAN_MM:raise ValueError(f'位置不能重复，测线跨度≤{MAX_SPAN_MM}mm')
 return sorted(points,key=lambda p:p['position'])

def validate_plan(plan):
 f=np.asarray(plan['frequencies'],dtype=float)
 if f.ndim!=1 or not 3<=len(f)<=401 or not np.isfinite(f).all() or (f<=0).any() or (f>1).any() or (np.diff(f)<=0).any():raise ValueError('频率须3..401个有限严格递增正值且≤1周期/mm')
 if type(plan['permutations']) is not int or not 199<=plan['permutations']<=499 or type(plan['seed']) is not int or not 0<=plan['seed']<=1000000000:raise ValueError('置换次数199..499与seed须合法整数')
 return f
