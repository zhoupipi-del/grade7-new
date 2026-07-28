"""
modules/reports/celery_app.py — Wings 3.0 Celery 引擎总线 v2.0

Phase 2A 重构：kombu.Exchange + Queue 显式声明，多队列物理隔离。

队列拓扑:
  high_priority — AI处方生成 (10-30s)，Worker concurrency=4
  maintenance   — PDF报告 + RDI风险扫描 (7-9min)，Worker concurrency=2
  periodic      — 定时任务 (Cron Beat)，Worker concurrency=1
  celery        — 默认队列 (兼容旧任务)，平滑过渡后废弃

强绑定 Docker Redis 6379 的 DB 2/3（与旧 Flask DB 0 完全隔离）。
"""

import logging
import os

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)

# ── Redis 连接 ──
# DB 2: broker（任务队列）  DB 3: result_backend（结果存储）
# 与旧 grade7-new 的 DB 0 完全物理隔离，互不干扰
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")

# 优先使用显式 CELERY_BROKER_URL（含完整认证），其次用 REDIS_PASSWORD 动态组装
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")
if not CELERY_BROKER_URL:
    if REDIS_PASSWORD:
        CELERY_BROKER_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/2"
    else:
        CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/2"
        logger.warning("[SECURITY] REDIS_PASSWORD 未设置，Celery broker 连接无密码保护！")

CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")
if not CELERY_RESULT_BACKEND:
    if REDIS_PASSWORD:
        CELERY_RESULT_BACKEND = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/3"
    else:
        CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}/3"
        logger.warning("[SECURITY] REDIS_PASSWORD 未设置，Celery result backend 连接无密码保护！")

celery_engine = Celery(
    "wings3_reports",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "modules.reports.tasks",
        "modules.ai_prescription.tasks",
        "modules.risk_models.tasks",  # Phase 2A: RDI 异步任务骨架
        "modules.approval.tasks",  # Phase 2B: 审批超时扫描器
        "modules.timetable.tasks",  # Wings 3.1: 时空发电机 (Beat 02:00)
    ],
)

# ═══════════════════════════════════════════════════════════════
# Exchange 声明 (direct 类型 — 精确路由，无通配符)
# ═══════════════════════════════════════════════════════════════
high_priority_exchange = Exchange("wings3.high_priority", type="direct")
maintenance_exchange = Exchange("wings3.maintenance", type="direct")
periodic_exchange = Exchange("wings3.periodic", type="direct")
default_exchange = Exchange("wings3.default", type="direct")

# ═══════════════════════════════════════════════════════════════
# Queue 显式声明
# ═══════════════════════════════════════════════════════════════
task_queues = (
    Queue("high_priority", high_priority_exchange, routing_key="high"),
    Queue("maintenance", maintenance_exchange, routing_key="maintenance"),
    Queue("periodic", periodic_exchange, routing_key="periodic"),
    Queue("celery", default_exchange, routing_key="default"),
)

celery_engine.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_time_limit=900,  # 15 分钟强行超时断路器
    task_soft_time_limit=840,  # 14 分钟软超时（提前 60s 发出 SoftTimeLimitExceeded）
    worker_prefetch_multiplier=1,  # 公平调度，避免长任务阻塞短任务
    result_expires=3600,  # 结果 1 小时后自动清理
    task_acks_late=True,  # 任务完成后才确认，防止 worker 崩溃丢任务
    task_reject_on_worker_lost=True,  # worker 崩溃时自动重新派发
    # ── 四队列物理隔离 ──
    task_default_queue="celery",
    task_queues=task_queues,
    task_routes={
        # 🔴 高优先级：AI 处方 (10-30s)
        "ai_prescription.*": {"queue": "high_priority"},
        # 🟡 重资产：PDF 报告 + RDI 风险扫描 (7-15min)
        "generate_class_moral_report": {"queue": "maintenance"},
        "reports.precompute_snapshots": {"queue": "maintenance"},
        "risk_models.*": {"queue": "maintenance"},
        # 🟢 定时任务：审计报表、数据备份 + 审批超时扫描 + 时空发电机
        "reports.periodic_*": {"queue": "periodic"},
        "approval.*": {"queue": "periodic"},  # Phase 2B
        "timetable.*": {"queue": "periodic"},  # Wings 3.1
    },
    # ── Celery Beat 调度 (Phase 2B: RDI 每日全量扫描已激活) ──
    beat_schedule={
        # 每日凌晨 1:00 全量 RDI 风险扫描
        "rdi-daily-scan": {
            "task": "risk_models.rdi_daily_scan",
            "schedule": crontab(hour=1, minute=0),
            "options": {"queue": "periodic"},
        },
        # 每 30 分钟审批超时扫描 (Phase 2B)
        "check-timeout-approvals": {
            "task": "approval.check_timeout_approvals",
            "schedule": crontab(minute="*/30"),
            "options": {"queue": "periodic"},
        },
        # 每日凌晨 2:30 PDF 报告夜间预计算 (Phase 3: PDF 引擎优化)
        "precompute-report-snapshots": {
            "task": "reports.precompute_snapshots",
            "schedule": crontab(hour=2, minute=30),
            "options": {"queue": "maintenance"},
        },
        # 每日凌晨 2:00 系统合规审计 (清网迁移: 原 Flask audit_report.py)
        "system-daily-audit": {
            "task": "reports.periodic_audit_report",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": "periodic"},
        },
        # Wings 3.1: 每日凌晨 2:00 时空发电机 — 滚动生成未来 7 天课表实例
        "timetable-auto-generate-instances": {
            "task": "timetable.auto_generate_instances",
            "schedule": crontab(hour=2, minute=0),
            "options": {"queue": "periodic"},
        },
    },
)
