from celery import Celery
from config import Config

celery_app = Celery(
    'grade7_new',
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND,
    include=['tasks']  # 关键：自动导入tasks.py，注册异步任务
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    task_time_limit=300,
    worker_prefetch_multiplier=1,
)
