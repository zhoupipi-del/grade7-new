"""
modules/attendance/routers.py — 考勤管理 API 路由

注册路径: /api/v1/attendance/*
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.services import AuthService
from core.models import User, UserRole
from core.routers import get_db, get_current_user
from .models import AttendanceRecord, LeaveRequest
from .services import AttendanceService

router = APIRouter(tags=["attendance"])


# ── Pydantic 请求/响应模型 ──

class AttendanceRecordItem(BaseModel):
    student_id: int
    status: str = Field(..., pattern="^(present|late|early|absent|leave)$")
    note: Optional[str] = ""


class BatchRecordRequest(BaseModel):
    class_id: int
    grade_id: int
    record_date: date
    records: List[AttendanceRecordItem] = Field(..., min_length=1)


class LeaveSubmitRequest(BaseModel):
    student_id: int
    class_id: int
    grade_id: int
    start_date: date
    end_date: date
    reason: str = Field(..., min_length=1, max_length=500)


class LeaveApproveRequest(BaseModel):
    leave_id: int


# ── 权限守卫 ──

async def require_attendance_access(current_user: User = Depends(get_current_user)):
    """考勤模块访问权限: 教师及以上角色均可"""
    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)
    if role in (UserRole.PARENT, UserRole.STUDENT):
        # 家长和学生只能查看，不能写入（在具体路由中区分）
        pass
    return current_user


# ═══════════════════════════════════════════════════════════════
# 考勤录入
# ═══════════════════════════════════════════════════════════════

@router.post("/records/batch")
async def batch_record_attendance(
    body: BatchRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_attendance_access),
):
    """
    批量录入班级考勤数据。
    仅班主任、年级组长、德育处管理员可操作。
    """
    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)
    if role in (UserRole.PARENT, UserRole.STUDENT):
        raise HTTPException(status_code=403, detail="无权录入考勤")

    school_id = current_user.school_id

    try:
        count = await AttendanceService.batch_record(
            db=db,
            school_id=school_id,
            class_id=body.class_id,
            grade_id=body.grade_id,
            record_date=body.record_date,
            records=[r.model_dump() for r in body.records],
        )
        return {"message": f"考勤录入成功", "count": count, "record_date": body.record_date.isoformat()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 考勤查询
# ═══════════════════════════════════════════════════════════════

@router.get("/records/class/{class_id}")
async def get_class_attendance(
    class_id: int,
    record_date: date = Query(..., description="查询日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某班级某日的考勤详情"""
    records = await AttendanceService.get_class_attendance(
        db=db,
        school_id=current_user.school_id,
        class_id=class_id,
        record_date=record_date,
    )
    return {"class_id": class_id, "record_date": record_date.isoformat(), "records": records, "count": len(records)}


@router.get("/records/student/{student_id}")
async def get_student_attendance(
    student_id: int,
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询某学生的考勤历史"""
    records = await AttendanceService.get_student_history(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        days=days,
    )
    return {"student_id": student_id, "days": days, "records": records, "count": len(records)}


# ═══════════════════════════════════════════════════════════════
# 考勤统计
# ═══════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_attendance_stats(
    grade_id: int = Query(..., description="年级 ID"),
    start_date: date = Query(..., description="开始日期"),
    end_date: date = Query(..., description="结束日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """年级考勤统计概览（按班级汇总）"""
    stats = await AttendanceService.get_grade_summary(
        db=db,
        school_id=current_user.school_id,
        grade_id=grade_id,
        start_date=start_date,
        end_date=end_date,
    )
    return stats


@router.get("/anomalies")
async def get_anomaly_alerts(
    days: int = Query(7, ge=1, le=30, description="监测天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """异常预警: 连续缺勤/频繁迟到的学生"""
    alerts = await AttendanceService.get_anomaly_alerts(
        db=db,
        school_id=current_user.school_id,
        days=days,
    )
    return {"alerts": alerts, "count": len(alerts), "period_days": days}


# ═══════════════════════════════════════════════════════════════
# 请假管理
# ═══════════════════════════════════════════════════════════════

@router.post("/leaves", status_code=201)
async def submit_leave_request(
    body: LeaveSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """家长提交请假申请"""
    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)
    if role != UserRole.PARENT:
        raise HTTPException(status_code=403, detail="仅家长可提交请假申请")

    if body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")

    leave = await AttendanceService.submit_leave(
        db=db,
        school_id=current_user.school_id,
        student_id=body.student_id,
        class_id=body.class_id,
        grade_id=body.grade_id,
        start_date=body.start_date,
        end_date=body.end_date,
        reason=body.reason,
        submitted_by=current_user.id,
    )

    return {
        "message": "请假申请已提交",
        "leave_id": leave.id,
        "status": leave.status,
    }


@router.post("/leaves/approve")
async def approve_leave_request(
    body: LeaveApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """班主任/年级组长审批请假"""
    role = current_user.role
    if isinstance(role, str):
        role = UserRole(role)
    if role not in (UserRole.CLASS_TEACHER, UserRole.GRADE_LEADER):
        raise HTTPException(status_code=403, detail="仅班主任或年级组长可审批请假")

    try:
        leave = await AttendanceService.approve_leave(
            db=db,
            leave_id=body.leave_id,
            approver_id=current_user.id,
            approver_role=role.value if hasattr(role, "value") else role,
        )
        return {
            "message": "审批完成",
            "leave_id": leave.id,
            "status": leave.status,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
