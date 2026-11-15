import numpy as np
from src.services.analysis import analyze
from src.services.qr_cache import build_cache
from src.services.spectrum import observed_spectrum
from src.services.permutation import global_permutation
from src.services.streaming import stream_analyze
import src.services.streaming as st
from src.constants.numerics import LEGACY_CACHE_BYTE_LIMIT

rng=np.random.default_rng(234)
def dataset(n,kind=0,seed=7):
 r=np.random.default_rng(seed)
 # 间距按N自适应，保证任意规模跨度都≤10000mm且位置唯一
 hi=min(2.3,9000.0/max(n,1));lo=min(0.8,hi*0.35)
 x=np.r_[0.,np.cumsum(r.uniform(lo,hi,n-1))]
 if kind==0:y=.5+.075*np.cos(2*np.pi*(x-x[0])/18-.7)+r.normal(0,.014,n)
 elif kind==1:y=.55+.055*np.sin(2*np.pi*x/30)+.04*np.cos(2*np.pi*x/12)+r.normal(0,.014,n)
 else:y=.5+.02*r.normal(size=n)
 return x,y
def points(x,y):return [{'reference':f'P{i:05d}','position':float(x[i]),'thickness':float(y[i])} for i in range(len(x))]
def plan(grid=201,B=199):
 f=np.linspace(1/90,.1,grid).tolist()
 return {'name':'p','protocol':'','min_frequency':f[0],'max_frequency':f[-1],'grid_size':grid,'frequencies':f,'permutations':B,'seed':234}
STUDY={'id':1,'name':'S','filename':'f.csv','description':'','status':'ready'}

def test_small_samples_use_legacy_engine():
 # 小样本必须走原算法路径，保证与改造前逐位一致
 for n in (4,16,120,240):
  assert 2*201*n*8<=LEGACY_CACHE_BYTE_LIMIT
  x,y=dataset(n);r=analyze(STUDY,points(x,y),plan())
  assert 'engine' not in r

def test_legacy_and_streaming_bit_identical_observed_outputs():
 x,y=dataset(3000);f=np.linspace(1/90,.1,201)
 cache=build_cache(x.tolist(),f.tolist());legacy,centered=observed_spectrum(cache,y.tolist())
 gt=global_permutation(cache,centered,legacy['rss0'],legacy['observed_max_power'],199,234)
 s=stream_analyze(x.tolist(),y.tolist(),f.tolist(),199,234)
 # 观测侧：最大峰、RSS0、最佳频率拟合、全谱、逐点拟合全部逐位一致
 assert legacy['observed_max_power']==s['observed_max_power']
 assert legacy['rss0']==s['rss0']
 for key in ('frequency','power','intercept','cos_coefficient','sin_coefficient','amplitude','phase_rad','rss'):
  assert legacy['best'][key]==s['best'][key]
 for a,b in zip(legacy['spectrum'],s['spectrum']):
  assert a['frequency']==b['frequency'] and a['included']==b['included']
  assert a['power']==b['power'] and a['rss']==b['rss']
  assert a['window_power']==b['window_power'] and a['singular_values']==b['singular_values']
 assert legacy['fit']==s['fit']
 # 置换：RNG序列相同，p与直方图逐位一致；null仅允许ULP级求和差异
 assert gt['global_p']==s['global_test']['global_p']
 assert gt['histogram']['counts']==s['global_test']['histogram']['counts']
 assert gt['exceedances_with_ties']==s['global_test']['exceedances_with_ties']
 assert max(abs(a-b) for a,b in zip(gt['null_maxima'],s['global_test']['null_maxima']))<1e-15
 assert len(s['global_test']['null_maxima'])==199

def test_results_invariant_to_block_sizes():
 x,y=dataset(4000);f=np.linspace(1/90,.1,201)
 base=stream_analyze(x,y,f,199,234)
 for fb,pb in ((1,1),(7,5),(24,8),(64,199),(101,37)):
  st.FREQ_BLOCK=fb;st.PERM_BLOCK=pb
  r=stream_analyze(x,y,f,199,234)
  assert r['observed_max_power']==base['observed_max_power']
  assert r['spectrum']==base['spectrum'] and r['fit']==base['fit']
  assert r['global_test']['global_p']==base['global_test']['global_p']
  assert max(abs(a-b) for a,b in zip(r['global_test']['null_maxima'],base['global_test']['null_maxima']))<1e-15
 st.FREQ_BLOCK=24;st.PERM_BLOCK=8

def test_analyze_wrapper_switch_and_shape():
 x,y=dataset(30000);p=plan()
 assert 2*p['grid_size']*30000*8>LEGACY_CACHE_BYTE_LIMIT
 r=analyze(STUDY,points(x,y),p)
 assert r['engine']=='streaming-blocked-v1'
 assert len(r['spectrum'])==201 and len(r['fit'])==30000
 assert len(r['global_test']['null_maxima'])==199 and r['n']==30000
 assert r['fingerprint'] and r['source_study']==STUDY

def test_constant_thickness_fails():
 x,_=dataset(2000);y=np.full(2000,.5)
 try:analyze(STUDY,points(x,y),plan());assert False
 except ValueError as e:assert 'RSS0' in str(e)
