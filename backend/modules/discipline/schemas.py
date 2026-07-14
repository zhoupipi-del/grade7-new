"""
modules/discipline/schemas.py — 处分管理 Pydantic 数据模型
"""

from datetime import date

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
# 处分创建 / 编辑
# ═══════════════════════════════════════════════════════════════


class SanctionCreate(BaseModel):
    """班主任提报处分"""

    student_id: int = Field(..., description="被处分学生 ID")
    level: str = Field(..., description="处分等级: WARNING/SERIOUS_WARN/DEMERIT/PROBATION")
    reason: str = Field(..., min_length=1, max_length=1000, description="处分事由")
    document_no: str | None = Field(None, max_length=50, description="红头文件编号")
    behavior_record_id: int | None = Field(None, description="关联的违纪记录 ID（溯源）")
    punish_date: date | None = None


class SanctionUpdate(BaseModel):
    """编辑待审批的处分（仅 PENDING 状态可编辑）"""

    level: str | None = None
    reason: str | None = None
    document_no: str | None = None
    punish_date: date | None = None


# ═══════════════════════════════════════════════════════════════
# 行政审批 (二级审批: grade_leader 初审 + ms_admin 终审)
# ═══════════════════════════════════════════════════════════════


class SanctionReview(BaseModel):
    """审批动作（初审/终审/驳回 共用）"""

    comment: str | None = Field(None, max_length=500, description="审批意见")


class SanctionRevoke(BaseModel):
    """撤销处分"""

    revoke_reason: str = Field(..., min_length=1, max_length=500, description="撤销原因／改过评语")
    revoke_date: date | None = Field(None, description="撤销日期，默认今天")


# ═══════════════════════════════════════════════════════════════
# 处分输出
# ═══════════════════════════════════════════════════════════════


class SanctionOut(BaseModel):
    id: int
    school_id: int
    student_id: int
    student_name: str | None = None
    student_no: str | None = None
    class_id: int
    class_name: str | None = None
    grade_id: int
    grade_name: str | None = None
    behavior_record_id: int | None = None
    level: str
    level_label: str | None = None
    status: str
    status_label: str | None = None
    reason: str
    document_no: str | None = None
    punish_date: str | None = None
    revoke_date: str | None = None
    revoke_reason: str | None = None
    creator_id: int
    creator_name: str | None = None
    approver_id: int | None = None
    approver_name: str | None = None
    grade_leader_id: int | None = None  # 年级组长初审人 ID
    grade_leader_name: str | None = None  # 年级组长姓名
    grade_leader_comment: str | None = None  # 初审意见
    grade_leader_reviewed_at: str | None = None  # 初审时间
    approver_comment: str | None = None  # 终审意见
    penalty_points: int | None = None  # 本次处分对应的扣分值
    is_veto: bool | None = None  # 是否触发一票否决
    evidence_snapshot: str | None = None  # Phase 2: 铁证快照 JSON
    auto_generated: bool | None = None  # Phase 2: 是否自动生成
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════
# Phase 2: 自动化引擎 — 草稿箱模式
# ═══════════════════════════════════════════════════════════════


class DraftEvidence(BaseModel):
    """铁证快照: 单条严重违纪证据"""

    behavior_id: int
    incident_date: str
    description: str
    location: str | None = None
    points: int


class DraftOut(SanctionOut):
    """处分草稿输出（继承 SanctionOut，追加草稿专属字段）"""

    evidence: list[DraftEvidence] | None = None  # 解析后的铁证列表
    triggered_at: str | None = None  # 触发时间


class DraftSubmit(BaseModel):
    """班主任确认提交草稿 → PENDING"""

    confirm_reason: str | None = Field(None, max_length=500, description="班主任补充意见")


class DraftListQuery(BaseModel):
    """草稿列表查询参数"""

    class_id: int | None = None
    grade_id: int | None = None
    student_id: int | None = None
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


# ═══════════════════════════════════════════════════════════════
# 统计
# ═══════════════════════════════════════════════════════════════


class SanctionStatsOut(BaseModel):
    total: int
    by_level: dict  # {"WARNING": 3, "DEMERIT": 1, ...}
    by_status: dict  # {"ACTIVE": 2, "PENDING": 1, "REVOKED": 1, ...}
    by_class: dict  # {"2501": 2, "2502": 1, ...}
    active_count: int  # 当前生效中的处分总数
    veto_count: int  # 触发一票否决的学生数


class EscalationCheckOut(BaseModel):
    """违纪一键升级 → 处分草案建议"""

    student_id: int
    student_name: str | None = None
    total_points: int  # 累计违纪扣分
    active_behavior_count: int  # 活跃违纪次数
    suggested_level: str | None = None  # 建议处分等级
    suggested_reason: str | None = None  # 自动生成的事由
    existing_sanctions: int  # 已有处分数
    can_escalate: bool  # 是否允许升级为处分


# ═══════════════════════════════════════════════════════════════
# Phase 4: 家校申诉 Webhook
# ═══════════════════════════════════════════════════════════════


class AppealWebhookCreate(BaseModel):
    """Webhook 接收外部系统（微信小程序）POST 的申诉请求"""

    idempotency_key: str = Field(..., min_length=1, max_length=100, description="外部系统幂等键")
    sanction_id: int = Field(..., description="被申诉的处分 ID")
    applicant_name: str = Field(..., min_length=1, max_length=50, description="申诉人姓名")
    applicant_phone: str | None = Field(None, max_length=20, description="联系电话")
    reason: str = Field(..., min_length=1, max_length=2000, description="申诉事由")


class AppealReview(BaseModel):
    """德育处复核申诉"""

    comment: str | None = Field(None, max_length=500, description="复核意见")
    action: str = Field(..., description="复核动作: ACCEPTED / REJECTED")


class AppealOut(BaseModel):
    """申诉输出"""

    id: int
    school_id: int
    sanction_id: int
    sanction_level: str | None = None
    sanction_level_label: str | None = None
    sanction_reason: str | None = None
    sanction_status: str | None = None
    student_id: int | None = None
    student_name: str | None = None
    applicant_name: str
    applicant_phone: str | None = None
    reason: str
    idempotency_key: str
    status: str
    status_label: str | None = None
    reviewer_id: int | None = None
    reviewer_name: str | None = None
    review_comment: str | None = None
    reviewed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}
