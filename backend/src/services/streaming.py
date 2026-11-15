import os, tempfile, shutil
import numpy as np
from src.constants.numerics import QR_RANK_TOL,POWER_TIE_TOL,FREQ_BLOCK,PERM_BLOCK
from src.config.settings import ARTIFACT_DIR

# 分块流式引擎：每个频率的SVD/QR只计算一次，Q块落临时文件后以mmap复用，
# 常驻工作集只有“一个频率块Q + 一个置换块y”，不随F*N整体增长。
# 数学口径与 qr_cache.py + spectrum.py + permutation.py 完全一致（同一QR分解），
# 仅改变计算顺序与存储方式；小样本仍由原引擎处理以保证逐位一致。

def _temp_dir():
 base=ARTIFACT_DIR if os.path.isdir(ARTIFACT_DIR) and os.access(ARTIFACT_DIR,os.W_OK) else tempfile.gettempdir()
 return tempfile.mkdtemp(prefix='weave-blocks-',dir=base)

def build_freq_block(t,freq_block):
 n=len(t);entries=[];Q=[];valid=[]
 for index,frequency in enumerate(freq_block):
  phase=2*np.pi*frequency*t;c=np.cos(phase);s=np.sin(phase)
  means=np.array([c.mean(),s.mean()]);A=np.column_stack((c-means[0],s-means[1]))
  sv=np.linalg.svd(A,compute_uv=False)
  threshold=QR_RANK_TOL*max(float(sv[0]),np.sqrt(n))
  window=float(c.mean()**2+s.mean()**2)
  if sv[-1]<=threshold:
   entries.append({'frequency':float(frequency),'included':False,'reason':'中心化sin/cos秩不足或病态：sigma_min≤1e-10*max(sigma_max,sqrtN)','singular_values':sv.tolist(),'window_power':window})
   continue
  q,R=np.linalg.qr(A,mode='reduced')
  entries.append({'frequency':float(frequency),'included':True,'reason':None,'singular_values':sv.tolist(),'window_power':window,'means':means,'R':R})
  Q.append(q.T);valid.append(index)
 return entries,(np.stack(Q) if Q else None),valid

def _block_powers(Qt,y_perm,rss0):
 # Qt: (Fb,2,n), y_perm: (Bp,n) -> powers (Bp,Fb)
 coefficients=np.einsum('fkn,bn->bfk',Qt,y_perm)
 return np.clip(np.einsum('bfk,bfk->bf',coefficients,coefficients)/rss0,0,1)

def stream_analyze(x_raw,y_raw,frequencies,B,seed):
 x=np.asarray(x_raw,dtype=float);y=np.asarray(y_raw,dtype=float);f=np.asarray(frequencies,dtype=float)
 n=len(x);t=x-float(x[0])
 # 与 spectrum.centered_response 完全相同的中心化：先减首值再中心化
 origin_y=float(y[0]);offset=y-origin_y;mean_offset=float(offset.mean());centered=offset-mean_offset
 rss0=float(centered@centered)
 if rss0<=0:raise ValueError('恒定厚度RSS0=0，无可定义的谱功率')

 workdir=_temp_dir();block_files=[]
 all_entries=[None]*len(f);observed_scores=np.full(len(f),np.nan);included=[]
 blocks=[(start,min(start+FREQ_BLOCK,len(f))) for start in range(0,len(f),FREQ_BLOCK)]
 try:
  # 第一遍：每频率只做一次SVD+QR，Q块落盘mmap；元数据常驻（每频率仅几十个double）
  for bi,(start,stop) in enumerate(blocks):
   glob_idx=list(range(start,stop))
   entries,Qt,valid=build_freq_block(t,f[glob_idx])
   for local,glob in enumerate(glob_idx):all_entries[glob]=entries[local]
   if Qt is not None:
    path=os.path.join(workdir,f'q-{bi}.npy')
    np.save(path,Qt);block_files.append((bi,path,glob_idx,valid))
    scores=_block_powers(Qt,centered[None,:],rss0)[0]
    for local,local_valid in enumerate(valid):
     glob=glob_idx[local_valid];observed_scores[glob]=float(scores[local]);included.append(glob)
   del Qt
  if not included:raise ValueError('全部频率退化，无可用谱')
  valid_scores=observed_scores[included]
  maximum=float(np.nanmax(valid_scores))
  choice_pos=int(np.flatnonzero(valid_scores>=maximum-POWER_TIE_TOL)[0]);choice=included[choice_pos]

  # 置换：与 global_permutation 同种子、同生成顺序（rng.permutation 调用次序一致）；
  # 外层置换块保证RNG顺序，内层频率块经mmap复用第一遍的QR，不再重复SVD/QR。
  rng=np.random.default_rng(seed);null=[];exceed=0;remaining=B
  while remaining>0:
   size=min(PERM_BLOCK,remaining)
   yperm=np.empty((size,n))
   for k in range(size):yperm[k]=centered[rng.permutation(n)]
   block_max=np.full(size,-np.inf)
   for bi,path,glob_idx,valid in block_files:
    Qt=np.load(path,mmap_mode='r')
    scores=_block_powers(Qt,yperm,rss0)[:,valid]
    block_max=np.maximum(block_max,scores.max(axis=1))
   for v in block_max:
    v=float(v);null.append(v)
    if v>=maximum-POWER_TIE_TOL:exceed+=1
   remaining-=size
  count=exceed;p=(count+1)/(B+1)
  hist,edges=np.histogram(np.asarray(null),bins=np.linspace(0,1,21))

  # 选频条目重算拟合（仅单个频率，内存O(n)），口径同 observed_spectrum
  entry=all_entries[choice]
  phase=2*np.pi*entry['frequency']*t;c=np.cos(phase);s=np.sin(phase)
  A=np.column_stack((c-entry['means'][0],s-entry['means'][1]))
  q,_=np.linalg.qr(A,mode='reduced')
  a,b=np.linalg.solve(entry['R'],q.T@centered)
  mean=origin_y+mean_offset
  intercept=mean-a*entry['means'][0]-b*entry['means'][1]
  fitted=intercept+a*c+b*s
 finally:
  shutil.rmtree(workdir,ignore_errors=True)
 rss=float(np.sum((y-fitted)**2));amplitude=float(np.hypot(a,b));phase_rad=float(np.arctan2(b,a))
 scoremap={idx:float(observed_scores[idx]) for idx in included}
 spectrum=[{'frequency':e['frequency'],'period':1/e['frequency'],'included':e['included'],'reason':e['reason'],'singular_values':e['singular_values'],'power':scoremap.get(i),'rss':rss0*(1-scoremap[i]) if i in scoremap else None,'window_power':e['window_power']} for i,e in enumerate(all_entries)]
 return {
  'rss0':rss0,'observed_max_power':maximum,'spectrum':spectrum,
  'included_frequencies':len(included),'excluded_frequencies':len(f)-len(included),
  'best':{'frequency':entry['frequency'],'period':1/entry['frequency'],'power':float(observed_scores[choice]),'intercept':float(intercept),'cos_coefficient':float(a),'sin_coefficient':float(b),'amplitude':amplitude,'phase_rad':phase_rad,'phase_origin':float(x[0]),'phase_definition':'c + A*cos(2*pi*f*(x-x0)-phi), phi=atan2(sin_coefficient,cos_coefficient)','rss':rss},
  'fit':[{'position':float(xv),'observed':float(v),'fitted':float(pred),'residual':float(v-pred)} for xv,v,pred in zip(x,y,fitted)],
  'global_test':{'permutations':B,'seed':seed,'null_maxima':null,'exceedances_with_ties':count,'global_p':p,'minimum_monte_carlo_p':1/(B+1),'power_tie_tolerance':POWER_TIE_TOL,'histogram':{'counts':hist.tolist(),'edges':edges.tolist()},'definition':'Fixed x, permute y labels; refit every included frequency using one cached QR basis, then take full-grid maximum. p=(1+#nullmax>=observedmax-tol)/(B+1).','assumptions':'iid exchangeable, homoscedastic errors under no spatial periodic signal; not single-frequency p, period CI, process cause, or online diagnosis.'},
  'coordinate_origin':float(x[0]),'engine':'streaming-blocked-v1',
 }
