import os
DATABASE_URL=os.getenv('DATABASE_URL','postgresql+psycopg://weave:weave_demo@db:5432/weave')
REDIS_URL=os.getenv('REDIS_URL','redis://redis:6379/0')
JWT_SECRET=os.environ['JWT_SECRET']
SEED_DEMO=os.getenv('SEED_DEMO','true').lower()=='true'
ARTIFACT_DIR=os.getenv('ARTIFACT_DIR','/artifacts')
# 分批导入十万测点会在短时间产生较多写请求，默认配额放宽到600/分钟；仍可用环境变量覆盖
RATE_LIMIT_WRITES=int(os.getenv('RATE_LIMIT_WRITES','600'))
