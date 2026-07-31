"""
modules/parent_portal/models.py — 家长门户数据模型

两张新表:
  1. ParentFeedback — 双向闭环反馈（家长提交 → 班主任处理 → 家长收到回复）
  2. ParentAppealsProxy — 申诉代理追踪（Facade 路由到 discipline/behavior）

两张表都继承 SchoolMixin 实现多租户隔离，含 parent_id → student_id 绑定字段。

越权防御铁闸:
  - 所有端点必须校验 current_user.bound_student_id 与请求参数 student_id 一致
  - 家长只能访问自己绑定孩子的数据，横向穿透是绝对红线
"""

import enum
from sqlalchemy import (
    Column, BigInteger, Integer, String, Boolean, DateTime, JSON, Text,
    Index, ForeignKey,
)
from core.models import Base, SchoolMixin, get_local_now


# ═══════════════════════════════════════════════════════════════
# 反馈类型枚举
# ═══════════════════════════════════════════════════════════════

class FeedbackType(str, enum.Enum):
    SUGGESTION = "suggestion"       # 建议
    COMPLAINT = "complaint"         # 投诉
    PRAISE = "praise"               # 表扬
    CONSULTATION = "consultation"   # 咨询
    OTHER = "other"                 # 其他


class FeedbackStatus(str, enum.Enum):
    PENDING = "pending"             # 待处理
    PROCESSING = "processing"       # 处理中
    RESOLVED = "resolved"           # 已解决
    CLOSED = "closed"               # 已关闭


class AppealTargetModule(str, enum.Enum):
    DISCIPLINE = "discipline"       # 处分申诉
    BEHAVIOR = "behavior"           # 违纪申诉


# ═══════════════════════════════════════════════════════════════
# 表 1 — 家长反馈（双向闭环）
# ═══════════════════════════════════════════════════════════════

FEEDBACK_TYPE_LABELS = {
    FeedbackType.SUGGESTION: "建议",
    FeedbackType.COMPLAINT: "投诉",
    FeedbackType.PRAISE: "表扬",
    FeedbackType.CONSULTATION: "咨询",
    FeedbackType.OTHER: "其他",
}

FEEDBACK_STATUS_LABELS = {
    FeedbackStatus.PENDING: "待处理",
    FeedbackStatus.PROCESSING: "处理中",
    FeedbackStatus.RESOLVED: "已解决",
    FeedbackStatus.CLOSED: "已关闭",
}

APPEAL_TARGET_LABELS = {
    AppealTargetModule.DISCIPLINE: "处分申诉",
    AppealTargetModule.BEHAVIOR: "违纪申诉",
}


class ParentFeedback(Base, SchoolMixin):
    """
    家长反馈表 — 双向闭环状态机:
      pending → processing → resolved → closed

    血缘追踪: source_context JSON 记录来源上下文（渠道、触发事件等）
    通知联动: 提交时自动通知班主任，处理时自动通知家长
    """
    __tablename__ = "parent_feedbacks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 绑定关系（越权铁闸核心字段）
    parent_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True,
                        comment="提交反馈的家长 user_id")
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True,
                        comment="反馈关联的学生 id（必须与 parent_id.bound_student_id 一致）")
    parent_name = Column(String(50), nullable=True, comment="家长姓名-冗余减少JOIN")

    # 反馈内容
    feedback_type = Column(String(20), nullable=False, comment="反馈类型: suggestion/complaint/praise/consultation/other")
    title = Column(String(200), nullable=False, comment="反馈标题")
    content = Column(Text, nullable=False, comment="反馈正文")
    attachments = Column(JSON, nullable=True, comment="附件 URL 列表")

    # 状态机
    status = Column(String(20), nullable=False, default=FeedbackStatus.PENDING.value,
                    comment="反馈状态: pending/processing/resolved/closed")

    # 处理人（班主任/德育处）
    handler_id = Column(BigInteger, ForeignKey("users.id"), nullable=True, comment="处理人 user_id")
    handler_name = Column(String(50), nullable=True, comment="处理人姓名")
    handler_reply = Column(Text, nullable=True, comment="处理回复内容")
    handled_at = Column(DateTime, nullable=True, comment="处理时间")

    # 血缘追踪
    source_context = Column(JSON, nullable=True, comment="来源上下文（渠道、触发事件等）")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_pf_school_status", "school_id", "status"),
        Index("idx_pf_parent_student", "parent_id", "student_id"),
    )


# ═══════════════════════════════════════════════════════════════
# 表 2 — 申诉代理追踪（Facade 路由到 discipline/behavior）
# ═══════════════════════════════════════════════════════════════

class ParentAppealsProxy(Base, SchoolMixin):
    """
    申诉代理追踪表 — Facade 模式:
      家长提交申诉 → 本表记录追踪 → 实际路由到 discipline/behavior 模块已有审批流

    设计原则:
      - 本表不存储申诉内容本身（reason/applicant_name 存在 source_context 中）
      - 只做路由追踪: target_module + target_record_id + target_appeal_id
      - 双向闭环: 家长可查询申诉进度，处理结果回传
    """
    __tablename__ = "parent_appeals_proxy"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # 绑定关系（越权铁闸核心字段）
    parent_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True,
                        comment="发起申诉的家长 user_id")
    student_id = Column(BigInteger, ForeignKey("students.id"), nullable=False, index=True,
                        comment="申诉关联的学生 id")

    # 申诉代理路由
    target_module = Column(String(20), nullable=False,
                           comment="目标模块: discipline/behavior")
    target_record_id = Column(BigInteger, nullable=False,
                               comment="目标原始记录 id（处分id 或 违纪记录id）")
    target_appeal_id = Column(BigInteger, nullable=True,
                              comment="目标模块生成的审批工单 id（路由成功后回填）")

    # 申诉内容（快照，防止原记录修改影响）
    applicant_name = Column(String(50), nullable=False, comment="申请人姓名")
    applicant_phone = Column(String(20), nullable=True, comment="申请人电话")
    reason = Column(Text, nullable=False, comment="申诉理由")

    # 代理状态
    proxy_status = Column(String(20), nullable=False, default="submitted",
                          comment="代理状态: submitted/routed/processing/completed/rejected")

    # 血缘追踪
    source_context = Column(JSON, nullable=True, comment="来源上下文")

    created_at = Column(DateTime, default=get_local_now)
    updated_at = Column(DateTime, default=get_local_now, onupdate=get_local_now)

    __table_args__ = (
        Index("idx_pap_school_module", "school_id", "target_module"),
        Index("idx_pap_parent_student", "parent_id", "student_id"),
    )
