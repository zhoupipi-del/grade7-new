"""
modules/parent_portal/schemas.py — 家长门户 Pydantic schemas

1:1 映射前端 parent_portal.ts 的全部类型定义:
  - FeedbackType / FeedbackStatus / AppealTargetModule (枚举)
  - FeedbackItem / FeedbackListResponse (反馈)
  - ChildOverview / ParentDashboard (聚合概览)
  - AppealProxyResult (申诉代理)
  - FeedbackCreatePayload / FeedbackReplyPayload / AppealProxyPayload (请求体)
"""

import enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# 枚举 (1:1 映射前端 FeedbackType / FeedbackStatus / AppealTargetModule)
# ═══════════════════════════════════════════════════════════════

class FeedbackTypeEnum(str, enum.Enum):
    SUGGESTION = "suggestion"
    COMPLAINT = "complaint"
    PRAISE = "praise"
    CONSULTATION = "consultation"
    OTHER = "other"


class FeedbackStatusEnum(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    CLOSED = "closed"


class AppealTargetModuleEnum(str, enum.Enum):
    DISCIPLINE = "discipline"
    BEHAVIOR = "behavior"


# ═══════════════════════════════════════════════════════════════
# 中文标签映射 (1:1 映射前端 FEEDBACK_TYPE_META / FEEDBACK_STATUS_META)
# ═══════════════════════════════════════════════════════════════

FEEDBACK_TYPE_LABELS = {
    FeedbackTypeEnum.SUGGESTION: "建议",
    FeedbackTypeEnum.COMPLAINT: "投诉",
    FeedbackTypeEnum.PRAISE: "表扬",
    FeedbackTypeEnum.CONSULTATION: "咨询",
    FeedbackTypeEnum.OTHER: "其他",
}

FEEDBACK_STATUS_LABELS = {
    FeedbackStatusEnum.PENDING: "待处理",
    FeedbackStatusEnum.PROCESSING: "处理中",
    FeedbackStatusEnum.RESOLVED: "已解决",
    FeedbackStatusEnum.CLOSED: "已关闭",
}

APPEAL_TARGET_LABELS = {
    AppealTargetModuleEnum.DISCIPLINE: "处分申诉",
    AppealTargetModuleEnum.BEHAVIOR: "违纪申诉",
}


# ═══════════════════════════════════════════════════════════════
# 时间轴事件 (1:1 映射前端 ChildOverview.recent_timeline)
# ═══════════════════════════════════════════════════════════════

class TimelineEvent(BaseModel):
    event_id: str
    event_type: str = Field(..., description="事件类型: evaluation/score_log/behavior/attendance/risk")
    occurred_at: str
    title: str
    description: Optional[str] = None
    severity: str = Field("info", description="严重程度: success/warning/danger/info")


# ═══════════════════════════════════════════════════════════════
# 反馈条目 (1:1 映射前端 FeedbackItem)
# ═══════════════════════════════════════════════════════════════

class FeedbackItem(BaseModel):
    id: int
    student_id: int
    parent_id: int
    parent_name: Optional[str] = None
    feedback_type: FeedbackTypeEnum
    feedback_type_label: str = Field("", description="中文标签（自动填充）")
    title: str
    content: str
    status: FeedbackStatusEnum
    status_label: str = Field("", description="中文标签（自动填充）")
    handler_id: Optional[int] = None
    handler_name: Optional[str] = None
    handler_reply: Optional[str] = None
    handled_at: Optional[str] = None
    attachments: Optional[List[str]] = None
    source_context: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: Optional[str] = None


class FeedbackListResponse(BaseModel):
    items: List[FeedbackItem]
    total: int


# ═══════════════════════════════════════════════════════════════
# 孩子概览 (1:1 映射前端 ChildOverview)
# ═══════════════════════════════════════════════════════════════

class ChildOverview(BaseModel):
    """跨模块聚合: 评价快照 + 考勤统计 + 违纪统计 + 时间轴 + 风险等级"""
    student_id: int
    student_name: str
    student_no: str
    class_name: str
    grade_name: str

    # 评价快照（五维分数，来自 evaluation.StudentScore）
    total_score: Optional[float] = None
    moral_score: Optional[float] = None
    academic_score: Optional[float] = None
    health_score: Optional[float] = None
    art_score: Optional[float] = None
    social_score: Optional[float] = None

    # 统计计数
    attendance_normal_count: int = 0
    attendance_abnormal_count: int = 0
    behavior_record_count: int = 0
    positive_score_total: int = 0

    # 最近时间轴事件（来自 growth 模块聚合）
    recent_timeline: List[TimelineEvent] = []

    # 风险状态（来自 risk_models 模块）
    risk_level: Optional[str] = None
    risk_label: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# 家长仪表盘 (1:1 映射前端 ParentDashboard)
# ═══════════════════════════════════════════════════════════════

class ParentDashboard(BaseModel):
    """首页聚合: 孩子概览 + 未读通知 + 待处理反馈 + 最近反馈"""
    child: ChildOverview
    unread_notifications: int = 0
    pending_feedbacks: int = 0
    recent_feedbacks: List[FeedbackItem] = []
    _meta: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════
# 申诉代理结果 (1:1 映射前端 AppealProxyResult)
# ═══════════════════════════════════════════════════════════════

class AppealProxyResult(BaseModel):
    success: bool
    target_module: AppealTargetModuleEnum
    target_appeal_id: Optional[int] = None
    message: str
    source_context: Optional[Dict[str, Any]] = None
    _meta: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════
# 请求体 (1:1 映射前端 Payload 类型)
# ═══════════════════════════════════════════════════════════════

class FeedbackCreatePayload(BaseModel):
    """家长提交反馈 — student_id 由越权铁闸从 bound_student_id 自动注入"""
    student_id: int = Field(..., description="学生 ID（必须与当前家长 bound_student_id 一致）")
    feedback_type: FeedbackTypeEnum
    title: str = Field(..., max_length=200)
    content: str = Field(...)
    attachments: Optional[List[str]] = None


class FeedbackReplyPayload(BaseModel):
    """班主任/德育处处理反馈"""
    status: FeedbackStatusEnum = Field(FeedbackStatusEnum.RESOLVED)
    reply: str = Field(..., description="处理回复内容")


class AppealProxyPayload(BaseModel):
    """申诉代理 — Facade 路由到 discipline/behavior"""
    target_module: AppealTargetModuleEnum
    target_record_id: int = Field(..., description="目标原始记录 ID")
    student_id: int = Field(..., description="学生 ID（越权铁闸校验）")
    applicant_name: str = Field(..., max_length=50)
    applicant_phone: Optional[str] = None
    reason: str = Field(..., description="申诉理由")


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def fill_labels(item: FeedbackItem) -> FeedbackItem:
    """自动填充 feedback_type_label 和 status_label"""
    item.feedback_type_label = FEEDBACK_TYPE_LABELS.get(item.feedback_type, item.feedback_type)
    item.status_label = FEEDBACK_STATUS_LABELS.get(item.status, item.status)
    return item
