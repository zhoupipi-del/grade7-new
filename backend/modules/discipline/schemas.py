"""
modules/discipline/schemas.py — 处分管理 Pydantic 数据模型
"""

from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 处分创建 / 编辑
# ═══════════════════════════════════════════════════════════════

class SanctionCreate(BaseModel):
    """班主任提报处分"""
    student_id: int = Field(..., description="被处分学生 ID")
    level: str = Field(..., description="处分等级: WARNING/SERIOUS_WARN/DEMERIT/PROBATION")
    reason: str = Field(..., min_length=1, max_length=1000, description="处分事由")
    document_no: Optional[str] = Field(None, max_length=50, description="红头文件编号")
    behavior_record_id: Optional[int] = Field(None, description="关联的违纪记录 ID（溯源）")
    punish_date: Optional[date] = None


class SanctionUpdate(BaseModel):
    """编辑待审批的处分（仅 PENDING 状态可编辑）"""
    level: Optional[str] = None
    reason: Optional[str] = None
    document_no: Optional[str] = None
    punish_date: Optional[date] = None


# ═══════════════════════════════════════════════════════════════
# 行政审批 (二级审批: grade_leader 初审 + ms_admin 终审)
# ═══════════════════════════════════════════════════════════════

class SanctionReview(BaseModel):
    """审批动作（初审/终审/驳回 共用）"""
    comment: Optional[str] = Field(None, max_length=500, description="审批意见")


class SanctionRevoke(BaseModel):
    """撤销处分"""
    revoke_reason: str = Field(..., min_length=1, max_length=500, description="撤销原因／改过评语")
    revoke_date: Optional[date] = Field(None, description="撤销日期，默认今天")


# ═══════════════════════════════════════════════════════════════
# 处分输出
# ═══════════════════════════════════════════════════════════════

class SanctionOut(BaseModel):
    id: int
    school_id: int
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int
    grade_name: Optional[str] = None
    behavior_record_id: Optional[int] = None
    level: str
    level_label: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    reason: str
    document_no: Optional[str] = None
    punish_date: Optional[str] = None
    revoke_date: Optional[str] = None
    revoke_reason: Optional[str] = None
    creator_id: int
    creator_name: Optional[str] = None
    approver_id: Optional[int] = None
    approver_name: Optional[str] = None
    grade_leader_id: Optional[int] = None     # 年级组长初审人 ID
    grade_leader_name: Optional[str] = None   # 年级组长姓名
    grade_leader_comment: Optional[str] = None  # 初审意见
    grade_leader_reviewed_at: Optional[str] = None  # 初审时间
    approver_comment: Optional[str] = None    # 终审意见
    penalty_points: Optional[int] = None    # 本次处分对应的扣分值
    is_veto: Optional[bool] = None           # 是否触发一票否决
    evidence_snapshot: Optional[str] = None  # Phase 2: 铁证快照 JSON
    auto_generated: Optional[bool] = None    # Phase 2: 是否自动生成
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════
# Phase 2: 自动化引擎 — 草稿箱模式
# ═══════════════════════════════════════════════════════════════

class DraftEvidence(BaseModel):
    """铁证快照: 单条严重违纪证据"""
    behavior_id: int
    incident_date: str
    description: str
    location: Optional[str] = None
    points: int


class DraftOut(SanctionOut):
    """处分草稿输出（继承 SanctionOut，追加草稿专属字段）"""
    evidence: Optional[List[DraftEvidence]] = None  # 解析后的铁证列表
    triggered_at: Optional[str] = None              # 触发时间


class DraftSubmit(BaseModel):
    """班主任确认提交草稿 → PENDING"""
    confirm_reason: Optional[str] = Field(None, max_length=500, description="班主任补充意见")


class DraftListQuery(BaseModel):
    """草稿列表查询参数"""
    class_id: Optional[int] = None
    grade_id: Optional[int] = None
    student_id: Optional[int] = None
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


# ═══════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════

class SanctionStatsOut(BaseModel):
    total: int
    by_level: dict        # {"WARNING": 3, "DEMERIT": 1, ...}
    by_status: dict       # {"ACTIVE": 2, "PENDING": 1, "REVOKED": 1, ...}
    by_class: dict        # {"2501": 2, "2502": 1, ...}
    active_count: int     # 当前生效中的处分总数
    veto_count: int       # 触发一票否决的学生数


class EscalationCheckOut(BaseModel):
    """违纪一键升级 → 处分草案建议"""
    student_id: int
    student_name: Optional[str] = None
    total_points: int        # 累计违纪扣分
    active_behavior_count: int  # 活跃违纪次数
    suggested_level: Optional[str] = None  # 建议处分等级
    suggested_reason: Optional[str] = None  # 自动生成的事由
    existing_sanctions: int  # 已有处分数
    can_escalate: bool       # 是否允许升级为处分


# ═══════════════════════════════════════════════════════════════
# Phase 4: 家校申诉 Webhook
# ═══════════════════════════════════════════════════════════════

class AppealWebhookCreate(BaseModel):
    """Webhook 接收外部系统（微信小程序）POST 的申诉请求"""
    idempotency_key: str = Field(..., min_length=1, max_length=100, description="外部系统幂等键")
    sanction_id: int = Field(..., description="被申诉的处分 ID")
    applicant_name: str = Field(..., min_length=1, max_length=50, description="申诉人姓名")
    applicant_phone: Optional[str] = Field(None, max_length=20, description="联系电话")
    reason: str = Field(..., min_length=1, max_length=2000, description="申诉事由")


class AppealReview(BaseModel):
    """德育处复核申诉"""
    comment: Optional[str] = Field(None, max_length=500, description="复核意见")
    action: str = Field(..., description="复核动作: ACCEPTED / REJECTED")


class AppealOut(BaseModel):
    """申诉输出"""
    id: int
    school_id: int
    sanction_id: int
    sanction_level: Optional[str] = None
    sanction_level_label: Optional[str] = None
    sanction_reason: Optional[str] = None
    sanction_status: Optional[str] = None
    student_id: Optional[int] = None
    student_name: Optional[str] = None
    applicant_name: str
    applicant_phone: Optional[str] = None
    reason: str
    idempotency_key: str
    status: str
    status_label: Optional[str] = None
    reviewer_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}
