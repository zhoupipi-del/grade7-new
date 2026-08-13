"""
modules/tasks/models.py — Task Center Foundation V1 数据模型

责任闭环底座（周主任 2026-08-13 拍板，5 条架构规则）：
  - Task            任务主表（含责任快照 + closure 与 status 分离）
  - TaskAssignment  分派历史（追加式，is_current 标记当前；调岗后历史保留原责任人）
  - TaskEvent       状态流转事件流（detail JSON 快照）
  - TaskEvidence    处理证据（note / communication_record / file）
  - TaskComment     评论

关键设计：
  1. Task 不自己猜 Owner：owner_user_id 仅由 ResponsibleOwnerResolver 写入，
     unresolved → owner=NULL + unresolved_reason（unassigned / resolution_required）。
  2. 责任快照：tasks 主表保存 owner/role/scope/source/confidence/resolved_at/assignment_id，
     历史事实="某时刻依据某 assignment 分配给某老师"。
  3. Assignment 改变 ≠ 历史任务自动换人：task_assignments 只追加。
  5. DONE ≠ verified：status=DONE 时 closure_status='pending'（V1 不自动复核，但字段分离）。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, String, Text,
)
from sqlalchemy.orm import relationship

from core.models import Base, get_local_now


# ═══════════════════════════════════════════════════════════════
# 任务状态机（V1 只管理真实动作）
# ═══════════════════════════════════════════════════════════════
TASK_STATUS_OPEN = "OPEN"
TASK_STATUS_ACCEPTED = "ACCEPTED"
TASK_STATUS_IN_PROGRESS = "IN_PROGRESS"
TASK_STATUS_DONE = "DONE"
TASK_STATUS_REJECTED = "REJECTED"
TASK_STATUS_CANCELLED = "CANCELLED"

TASK_STATUS_ACTIVE = {TASK_STATUS_OPEN, TASK_STATUS_ACCEPTED, TASK_STATUS_IN_PROGRESS}
TASK_STATUS_TERMINAL = {TASK_STATUS_DONE, TASK_STATUS_REJECTED, TASK_STATUS_CANCELLED}

# closure 状态（与 status 分离：DONE ≠ verified）
CLOSURE_PENDING = "pending"
CLOSURE_VERIFIED = "verified"

# 事件类型
EV_CREATED = "created"
EV_ACCEPTED = "accepted"
EV_STARTED = "started"
EV_COMPLETED = "completed"
EV_REJECTED = "rejected"
EV_CANCELLED = "cancelled"
EV_REASSIGNED = "reassigned"
EV_EVIDENCE_ADDED = "evidence_added"
EV_COMMENT_ADDED = "comment_added"
EV_RESOLUTION_REQUIRED = "resolution_required"


class Task(Base):
    """任务主表（含责任快照）"""

    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    school_id = Column(BigInteger, nullable=False)
    task_type = Column(String(32), nullable=False, default="manual")
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default=TASK_STATUS_OPEN)
    priority = Column(String(10), nullable=False, default="normal")
    due_at = Column(DateTime, nullable=True)

    # ── 责任快照（由 ResponsibleOwnerResolver 写入，禁止猜测）──
    owner_user_id = Column(BigInteger, nullable=True)
    owner_name_snapshot = Column(String(100), nullable=True)
    responsibility_role = Column(String(32), nullable=True)
    responsibility_scope_type = Column(String(16), nullable=True)
    responsibility_scope_id = Column(BigInteger, nullable=True)
    resolution_source = Column(String(64), nullable=True)
    resolution_confidence = Column(String(16), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    assignment_id = Column(BigInteger, nullable=True)
    unresolved_reason = Column(String(200), nullable=True)

    # ── closure 与 status 分离（DONE ≠ verified）──
    closure_status = Column(String(16), nullable=True)
    closure_verified_at = Column(DateTime, nullable=True)
    closure_verified_by = Column(BigInteger, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    # 关系（懒加载即可，事件/证据/评论按需查询）
    assignments = relationship(
        "TaskAssignment", back_populates="task", lazy="selectin",
        order_by="TaskAssignment.id",
    )
    events = relationship(
        "TaskEvent", back_populates="task", lazy="selectin",
        order_by="TaskEvent.id",
    )
    evidence = relationship(
        "TaskEvidence", back_populates="task", lazy="selectin",
        order_by="TaskEvidence.id",
    )
    comments = relationship(
        "TaskComment", back_populates="task", lazy="selectin",
        order_by="TaskComment.id",
    )


class TaskAssignment(Base):
    """分派历史（追加式：每次分派/转交追加一行，is_current 翻转）"""

    __tablename__ = "task_assignments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, nullable=False)
    assignment_id = Column(BigInteger, nullable=True)          # 责任快照引用的 assignment 行
    owner_user_id = Column(BigInteger, nullable=True)
    owner_name_snapshot = Column(String(100), nullable=True)
    responsibility_role = Column(String(32), nullable=True)
    responsibility_scope_type = Column(String(16), nullable=True)
    responsibility_scope_id = Column(BigInteger, nullable=True)
    resolution_source = Column(String(64), nullable=True)
    resolution_confidence = Column(String(16), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    reassigned_from_user_id = Column(BigInteger, nullable=True)
    assigned_by = Column(BigInteger, nullable=False)
    assigned_at = Column(DateTime, default=get_local_now)
    is_current = Column(Boolean, nullable=False, default=True)

    task = relationship("Task", back_populates="assignments")


class TaskEvent(Base):
    """状态流转事件流"""

    __tablename__ = "task_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, nullable=False)
    event_type = Column(String(32), nullable=False)
    actor_user_id = Column(BigInteger, nullable=True)
    actor_name = Column(String(100), nullable=True)
    detail = Column(Text, nullable=True)  # JSON 快照（读写前归一化）
    created_at = Column(DateTime, default=get_local_now)

    task = relationship("Task", back_populates="events")


class TaskEvidence(Base):
    """处理证据：note（文字说明）/ communication_record（沟通记录）/ file（文件）"""

    __tablename__ = "task_evidence"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, nullable=False)
    kind = Column(String(32), nullable=False, default="note")
    content = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=get_local_now)

    task = relationship("Task", back_populates="evidence")


class TaskComment(Base):
    """评论"""

    __tablename__ = "task_comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, default=get_local_now)

    task = relationship("Task", back_populates="comments")
