"""
modules/attendance/schemas.py — 考勤模块 Pydantic 请求/响应模型

从 routers.py 内联定义中抽离，符合 Wings 3.0 六件套标准架构。
V2 扩展: LeaveStatus枚举 + 班级历史聚合 + 请假响应 + 批量审批载荷
"""

from datetime import date
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
#  枚举
# ═══════════════════════════════════════════════════════════════

class LeaveStatus(str, Enum):
    """请假状态枚举 — 两级审批流"""
    PENDING = "pending"
    CLASS_APPROVED = "class_approved"
    GRADE_APPROVED = "grade_approved"
    REJECTED = "rejected"


# ═══════════════════════════════════════════════════════════════
#  请求模型
# ═══════════════════════════════════════════════════════════════

class AttendanceRecordItem(BaseModel):
    """单条考勤记录"""
    student_id: int
    status: str = Field(..., pattern="^(present|late|early|absent|leave)$")
    note: Optional[str] = ""


class BatchRecordRequest(BaseModel):
    """批量录入请求"""
    class_id: int
    grade_id: int
    record_date: date
    records: List[AttendanceRecordItem] = Field(..., min_length=1)


class LeaveSubmitRequest(BaseModel):
    """请假提交请求"""
    student_id: int
    class_id: int
    grade_id: int
    start_date: date
    end_date: date
    reason: str = Field(..., min_length=1, max_length=500)


class LeaveApproveRequest(BaseModel):
    """请假审批请求"""
    leave_id: int


class LeaveBatchApproveRequest(BaseModel):
    """批量审批请求（年级组长批量审批/拒绝）"""
    leave_ids: List[int] = Field(..., min_length=1)
    action: str = Field(..., pattern="^(approve|reject)$")


class AttendanceHistoryQuery(BaseModel):
    """班级考勤历史查询参数"""
    start_date: date = Field(..., description="起始日期 YYYY-MM-DD")
    end_date: date = Field(..., description="结束日期 YYYY-MM-DD")


# ═══════════════════════════════════════════════════════════════
#  响应模型
# ═══════════════════════════════════════════════════════════════

class ClassHistoryMetric(BaseModel):
    """班级单日考勤聚合指标 — 大盘纵深数据"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    total: int = Field(..., description="总人数")
    present: int = Field(0, description="出勤")
    late: int = Field(0, description="迟到")
    early: int = Field(0, description="早退")
    absent: int = Field(0, description="缺勤(CRITICAL)")
    leave: int = Field(0, description="请假(INFO)")
    attendance_rate: float = Field(0.0, description="出勤率%")


class LeaveResponse(BaseModel):
    """请假申请响应 — 含学生姓名"""
    leave_id: int
    student_id: int
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    class_id: int
    grade_id: int
    start_date: str
    end_date: str
    reason: str
    status: str
    submitted_by: Optional[int] = None
    created_at: Optional[str] = None
    approved_at_class: Optional[str] = None
    approved_at_grade: Optional[str] = None


class BatchLeaveApprovalResult(BaseModel):
    """批量审批单条结果"""
    leave_id: int
    success: bool
    status: Optional[str] = None
    student_id: Optional[int] = None
    attendance_created: Optional[int] = None
    rectified_count: Optional[int] = Field(None, description="冲正 absent→leave 条数")
    error: Optional[str] = None
