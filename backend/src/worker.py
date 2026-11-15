import json,resource,glob,os,shutil,tempfile
from pathlib import Path
from celery import Celery
from src.config.database import SessionLocal
from src.config.settings import REDIS_URL,ARTIFACT_DIR
from src.models import SpectrumRun
from src.services.analysis import analyze
from src.services.audit import record
from src.constants.numerics import ANALYSIS_MEMORY_LIMIT_MIB

def _cleanup_stale_blocks():
 # 上次任务被强杀可能遗留mmap块目录；worker并发1，启动时清理是安全的
 base=ARTIFACT_DIR if os.path.isdir(ARTIFACT_DIR) and os.access(ARTIFACT_DIR,os.W_OK) else tempfile.gettempdir()
 for d in glob.glob(os.path.join(base,'weave-blocks-*')):shutil.rmtree(d,ignore_errors=True)
_cleanup_stale_blocks()
app=Celery('weave_periodogram',broker=REDIS_URL,backend=REDIS_URL)
app.conf.update(task_track_started=True,worker_prefetch_multiplier=1,task_acks_late=True)
# 十万测点/401频点/499置换为现有最大频率计划，分块流式计算需要更长窗口；内存红线仍为256MiB
@app.task(name='weave.analyze',soft_time_limit=1800,time_limit=2100)
def analyze_run(id):
 with SessionLocal() as db:
  run=db.get(SpectrumRun,id)
  if not run or run.status=='completed':return
  run.status='running';db.commit()
  try:
   snapshot=run.source_snapshot
   result=analyze(snapshot['study'],snapshot['points'],run.plan_snapshot)
   snapshot=None  # 释放十万测点源快照，降低结果落库阶段的常驻内存
   Path(ARTIFACT_DIR).mkdir(parents=True,exist_ok=True)
   Path(ARTIFACT_DIR,f'weave-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
   run.result=result;run.peak_frequency=result['best']['frequency'];run.max_power=result['observed_max_power'];run.global_p=result['global_test']['global_p'];run.status='completed';run.error=None;db.commit()
   peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
   detail={'run_id':id,'global_p':run.global_p,'peak_rss_mib':round(peak,1),'engine':result.get('engine','legacy')}
   if peak>ANALYSIS_MEMORY_LIMIT_MIB:detail['memory_warning']=f'峰值{peak:.0f}MiB超过{ANALYSIS_MEMORY_LIMIT_MIB}MiB红线'
   record(db,'worker','run.completed',detail)
  except Exception as error:
   db.rollback();run=db.get(SpectrumRun,id);run.status='failed';run.error=str(error)[:1000];db.commit();record(db,'worker','run.failed',{'run_id':id,'error':run.error})
