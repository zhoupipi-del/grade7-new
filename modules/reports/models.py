"""
modules/reports/models.py — 报告任务追踪模型

ReportTask: 持久化异步任务状态，用于「前端轮询」和「历史回溯」。
ReportSnapshot: 夜间预计算快照，让 PDF 渲染从分钟级降到秒级。
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, ForeignKey, Text, Index,
    JSON, Boolean,
)
from core.models import Base, SchoolMixin, get_local_now


class ReportTask(Base, SchoolMixin):
    """
    报告生成任务追踪表

    每条记录 = 一次异步 PDF 生成请求的完整生命周期。
    状态机: PENDING → PROGRESS → SUCCESS / FAILURE
    """
    __tablename__ = "report_tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    celery_task_id = Column(String(64), unique=True, nullable=False, index=True,
                            comment="Celery AsyncResult.task_id")
    report_type = Column(String(40), nullable=False, comment="报告类型: class_moral/student_individual")
    class_id = Column(BigInteger, nullable=True, index=True)
    student_id = Column(BigInteger, nullable=True, index=True)
    semester = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING", index=True,
                    comment="PENDING/PROGRESS/SUCCESS/FAILURE")
    progress = Column(Integer, default=0, comment="进度 0-100")
    status_text = Column(String(200), nullable=True, comment="当前步骤描述")
    result_json = Column(Text, nullable=True, comment="完成结果 JSON")
    error_message = Column(Text, nullable=True, comment="失败错误信息")
    created_by = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=get_local_now)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_rt_class_sem", "class_id", "semester"),
        Index("idx_rt_status", "status"),
    )


class ReportSnapshot(Base, SchoolMixin):
    """
    夜间预计算快照表 — PDF 渲染的"数据弹药库"

    每日 2:30 AM 由 Celery Beat 预计算全校所有班级的跨模块聚合数据，
    存为 JSON。白天用户触发 PDF 时直接读取快照，跳过 Stage 1（数据聚合），
    将 7-9 分钟任务降到 10 秒以内。
    """
    __tablename__ = "report_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    class_id = Column(BigInteger, nullable=False, index=True)
    semester = Column(String(20), nullable=False)
    snapshot_data = Column(JSON, nullable=False, comment="预聚合数据 JSON")
    student_count = Column(Integer, default=0, comment="班级学生数")
    is_stale = Column(Boolean, default=False, comment="数据变更后标记为 stale")
    computed_at = Column(DateTime, default=get_local_now, comment="快照计算时间")

    __table_args__ = (
        Index("idx_rs_class_sem", "class_id", "semester", unique=True),
    )
