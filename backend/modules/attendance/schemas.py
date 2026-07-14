"""
modules/attendance/schemas.py — 考勤模块 Pydantic 请求/响应模型

从 routers.py 内联定义中抽离，符合 Wings 3.0 六件套标准架构。
"""

from datetime import date

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
#  请求模型
# ═══════════════════════════════════════════════════════════════


class AttendanceRecordItem(BaseModel):
    """单条考勤记录"""

    student_id: int
    status: str = Field(..., pattern="^(present|late|early|absent|leave)$")
    note: str | None = ""


class BatchRecordRequest(BaseModel):
    """批量录入请求"""

    class_id: int
    grade_id: int
    record_date: date
    records: list[AttendanceRecordItem] = Field(..., min_length=1)


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

    leave_ids: list[int] = Field(..., min_length=1)
    action: str = Field(..., pattern="^(approve|reject)$")
