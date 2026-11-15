from .validation import validate_points,validate_plan
from .qr_cache import build_cache
from .spectrum import observed_spectrum
from .permutation import global_permutation
from .streaming import stream_analyze
from .fingerprint import fingerprint
from src.constants.numerics import LEGACY_CACHE_BYTE_LIMIT

def _use_legacy(n,grid):
 # 与原算法相同的全量缓存估算 2*F*N*8 字节；小样本走原路径逐位一致
 return 2*grid*n*8<=LEGACY_CACHE_BYTE_LIMIT

def analyze(study,points,plan):
 points=validate_points(points);f=validate_plan(plan)
 x=[p['position'] for p in points];y=[p['thickness'] for p in points]
 if _use_legacy(len(points),len(f)):
  cache=build_cache(x,f);result,centered=observed_spectrum(cache,y)
  test=global_permutation(cache,centered,result['rss0'],result['observed_max_power'],plan['permutations'],plan['seed'])
  result={**result,'global_test':test,'qr_cache_builds':1}
 else:
  result=stream_analyze(x,y,f,plan['permutations'],plan['seed'])
 return {**result,'source_study':study,'plan':plan,'n':len(points),'fingerprint':fingerprint(study,points,plan),'tie_rule':'lowest frequency within absolute power tolerance 1e-12 of maximum; upper-tail null ties use same tolerance','interpretation':'Frozen predeclared frequency grid. Sampling window, aliasing, leakage and grid spacing limit interpretation; the selected period is not a confidence interval or a manufacturing cause. Independent homoscedastic exchangeable errors are required.'}
