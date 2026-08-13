"""
modules/behavior/schemas.py — 违纪行为 Pydantic 数据模型
"""

from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field


# ── 违纪记录 ──

class DisciplineCreate(BaseModel):
    student_id: int
    type: str = Field(..., description="违纪级别: warning/minor/major/serious")
    category: Optional[str] = Field(None, description="违纪类别: 打架/吸烟/迟到/仪容/课堂/其他")
    description: str = Field(..., min_length=1, max_length=500)
    action_taken: Optional[str] = Field(None, max_length=500)
    points: int = Field(0, ge=0)
    incident_date: Optional[date] = None
    # 数据来源（2026-08-13 Data Capture Audit）：
    #   人工登记场景(前端 UI) → 显式传 "teacher_manual"
    #   批量导入 / 规则引擎 / 测试 / 未知 → "import"/"system_generated"/"test_demo"/"legacy_unknown"
    #   不传 → 服务端默认 "legacy_unknown"（来源无法证明，绝不默认伪装成人工数据）
    source: Optional[str] = Field(
        None,
        description="数据来源: teacher_manual/system_generated/import/device/test_demo/legacy_unknown；不传默认 legacy_unknown",
    )


# ── QuickRegister（极简可信登记 · Step ⑦）──
# 前端只传「学生 + 事件类型 + 程度 + 备注」，其余一律服务端锁死：
#   school_id / created_by / class_id / grade_id 由服务端从 student 反查
#   source = teacher_manual（前端不可传）
#   type / category / points 由服务端规则计算（前端不可伪造）
# 注：迟到不放进事件类型，已有 attendance 模块，避免重复登记同一事实。

class QuickRegisterCreate(BaseModel):
    student_id: int = Field(..., description="学生 ID（必须从可见范围内选择）")
    event_type: str = Field(
        ...,
        description="事件类型: class_discipline/phone/conflict/appearance/other",
    )
    severity: str = Field(
        ...,
        description="程度: light(一般)/normal(较重)/serious(严重)",
    )
    description: Optional[str] = Field(None, max_length=500, description="备注（可选）")


class QuickRegisterStudentOut(BaseModel):
    id: int
    name: str
    student_no: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int

    model_config = {"from_attributes": True}


class QuickRegisterOut(BaseModel):
    id: int
    student_id: int
    student_name: Optional[str] = None
    class_name: Optional[str] = None
    event_type: str
    category: Optional[str] = None
    type: str
    severity: str
    description: str
    points: int
    incident_date: Optional[date] = None
    source: str
    created_by: int
    monthly_trusted_count: int

    model_config = {"from_attributes": True}


class DisciplineUpdate(BaseModel):
    type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    action_taken: Optional[str] = None
    points: Optional[int] = None
    incident_date: Optional[date] = None


class DisciplineOut(BaseModel):
    id: int
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_id: int
    class_name: Optional[str] = None
    grade_id: int
    type: str
    category: Optional[str] = None
    description: str
    action_taken: Optional[str] = None
    points: int
    status: str
    verify_status: str
    incident_date: Optional[date] = None
    created_by: int
    creator_name: Optional[str] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── 统计 ──

class DisciplineStatsOut(BaseModel):
    total: int
    by_type: dict  # {"warning": 5, "minor": 3, ...}
    by_category: dict  # {"打架": 2, "迟到": 6, ...}
    by_class: dict  # {"2501": 4, "2502": 3, ...}
    total_points: int
    monthly_trend: List[dict]  # [{"month": "06", "year": 2026, "count": 12}, ...]


# ── 申诉 ──

class AppealCreate(BaseModel):
    discipline_id: int
    reason: str = Field(..., min_length=1, max_length=500)


class AppealReview(BaseModel):
    status: str = Field(..., description="approved/rejected")
    review_comment: Optional[str] = None


class AppealOut(BaseModel):
    id: int
    discipline_id: int
    student_id: int
    student_name: Optional[str] = None
    reason: str
    status: str
    review_comment: Optional[str] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
