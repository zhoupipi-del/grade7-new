"""
modules/lineage/models.py — 血缘事件数据模型

lineage_events 表记录每一次数据转换的溯源信息：
- 源实体 (source_type + source_id/batch)
- 目标实体 (target_type + target_id)
- 转换类型 (transformation)
- 因果链 (trace_id 串联)
"""

from core.models import Base, SchoolMixin, get_local_now
from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Index,
    String,
)


class LineageEvent(Base, SchoolMixin):
    """
    血缘事件表 — 数据溯源的核心载体

    设计原则：
    1. trace_id 串联同一因果链的所有事件（如: 违纪 → 扣分 → 快照更新）
    2. source_type/source_id 记录"谁触发了这次转换"
    3. target_type/target_id 记录"转换产生了什么"
    4. source_batch 支持批量源（如: 15条 evaluation_scores → 1个 student_score）
    5. context 保存转换时的关键上下文（student_id, semester, weights 等）
    6. lineage_depth 记录事件在因果链中的层级（0=源头, 1=一次派生, …）
    """

    __tablename__ = "lineage_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 因果链标识 — 同一因果链的所有事件共享 trace_id
    trace_id = Column(String(36), nullable=False, index=True)

    # 源实体信息（谁触发了这次转换）
    source_type = Column(String(50), nullable=False, index=True)
    # 取值: evaluation_score, discipline_sanction, discipline_record,
    #       behavior_record, attendance_record, grade_record,
    #       rdi_alert, ai_prescription, score_log, manual
    source_id = Column(BigInteger, nullable=True)
    # 批量源: 当 source_id 为 None 时，此字段记录 {"count": 15, "ids": [...]}
    source_batch = Column(JSON, nullable=True)

    # 目标实体信息（转换产生了什么）
    target_type = Column(String(50), nullable=False, index=True)
    # 取值: student_score, score_log, report_snapshot,
    #       evaluation_score, discipline_sanction, grade_record
    target_id = Column(BigInteger, nullable=True)

    # 转换类型
    transformation = Column(String(60), nullable=False, index=True)
    # 取值: recalculate_snapshot, apply_deduction, record_score,
    #       compute_penalty, upload_scores, recalc_grades,
    #       discipline_status_change, ai_prescription_bridge

    # 转换上下文 — 保存关键参数快照
    context = Column(JSON, nullable=True)
    # 示例: {"student_id": 42, "semester": "2025-2026-2",
    #        "dimension_weights": {...}, "before_total": 85.5, "after_total": 78.0}

    # 触发者
    triggered_by = Column(String(100), nullable=True)
    # 取值: "user:123" (用户操作), "system:celery" (定时任务),
    #       "hook:appeal_accepted" (Webhook回调), "system:policy_engine"

    # 血缘深度 — 0=源头事件, 1=一次派生, 2=二次派生...
    lineage_depth = Column(BigInteger, default=0, nullable=False)

    # 关联学生 — 方便按学生查询全链路
    student_id = Column(BigInteger, nullable=True, index=True)

    created_at = Column(DateTime, default=get_local_now, nullable=False)

    # 索引
    __table_args__ = (
        Index("idx_le_trace", "trace_id"),
        Index("idx_le_source", "source_type", "source_id"),
        Index("idx_le_target", "target_type", "target_id"),
        Index("idx_le_stu_time", "student_id", "created_at"),
        Index("idx_le_trans", "transformation", "created_at"),
    )


class MigrationBatch(Base, SchoolMixin):
    """
    数据迁移批次追踪表

    每一次从旧系统 / 外部数据源批量迁移数据时,
    在此表落盘一条批次记录, 记录源端信息、目标表、行数和状态。
    配合 data_adapter 的 sync_status 字段, 实现完整的数据溯源闭环。

    典型流程:
      1. 创建批次 (status=pending)
      2. 逐行/逐表迁移 (success_rows/failed_rows 递增)
      3. 完成或失败 (status=completed/completed_with_errors/failed)
      4. 审计时按 batch_id 查询该批次影响的所有记录
    """

    __tablename__ = "migration_batches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    batch_id = Column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        comment="批次 UUID, 用于关联数据行的 sync_batch",
    )
    source_type = Column(
        String(30),
        nullable=False,
        comment="源类型: mysql_legacy/sqlite_dump/excel/csv/api",
    )
    source_desc = Column(
        String(255),
        nullable=True,
        comment="源描述: 旧数据库IP/文件名/API URL",
    )
    target_table = Column(
        String(50),
        nullable=False,
        index=True,
        comment="目标表: students/classes/grade_records/...",
    )
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        comment="批次状态: pending/processing/completed/completed_with_errors/failed",
    )
    total_rows = Column(BigInteger, default=0, comment="源端总行数")
    success_rows = Column(BigInteger, default=0, comment="成功迁移行数")
    failed_rows = Column(BigInteger, default=0, comment="失败行数")
    skipped_rows = Column(BigInteger, default=0, comment="跳过行数(已存在/不匹配)")

    errors_summary = Column(JSON, nullable=True, comment="失败摘要(前50条)")
    mapping_config = Column(
        JSON,
        nullable=True,
        comment="迁移映射配置: 字段映射/满分缩放/科目别名等",
    )
    transform_script = Column(
        String(100),
        nullable=True,
        comment="使用的变换脚本: legacy_data_etl.py / legacy_score_sampler.py",
    )

    created_by = Column(BigInteger, nullable=True, comment="操作人 user_id")
    started_at = Column(DateTime, nullable=True, comment="迁移开始时间")
    completed_at = Column(DateTime, nullable=True, comment="迁移完成时间")
    created_at = Column(DateTime, default=get_local_now, nullable=False)
    updated_at = Column(
        DateTime,
        default=get_local_now,
        onupdate=get_local_now,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_mb_status", "status", "created_at"),
        Index("idx_mb_target", "target_table", "created_at"),
        {"comment": "数据迁移批次追踪表"},
    )
