"""
timetable 路由层 — 适配生产DB列结构

端点:
  GET    /classrooms                     — 教室列表
  POST   /classrooms                     — 新增教室
  GET    /courses                        — 课程列表
  POST   /courses                        — 新增课程
  GET    /slots                          — 课节列表
  POST   /slots                          — 新增课节 (含冲突检测)
  DELETE /slots/{slot_id}                — 删除课节
  POST   /slots/check-conflict           — 单独检测冲突
  GET    /weekly/{class_id}              — 班级周课表
  GET    /weekly/teacher/{teacher_id}    — 教师周课表
  GET    /conflicts                      — 冲突列表
  PUT    /conflicts/{conflict_id}/resolve — 解决冲突
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.routers import get_db, get_current_user
from core.models import User
from modules.timetable.services import TimetableService
from modules.timetable.schemas import (
    ClassroomCreate, ClassroomOut,
    CourseCreate, CourseOut,
    CourseSlotCreate, CourseSlotOut,
    WeeklyScheduleOut, TeacherWeeklyScheduleOut,
    ConflictCheckResult, ConflictOut,
)

logger = logging.getLogger("timetable.routers")
router = APIRouter()


# ── 教室 ──

@router.get("/classrooms", response_model=list[ClassroomOut])
async def list_classrooms(
    room_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService.list_classrooms(
        db=db, school_id=current_user.school_id, room_type=room_type,
    )

@router.post("/classrooms", status_code=201, response_model=ClassroomOut)
async def create_classroom(
    body: ClassroomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService.create_classroom(
        db=db, data=body, school_id=current_user.school_id,
    )


# ── 课程 ──

@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    subject_category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService.list_courses(
        db=db, school_id=current_user.school_id, subject_category=subject_category,
    )

@router.post("/courses", status_code=201, response_model=CourseOut)
async def create_course(
    body: CourseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService.create_course(
        db=db, data=body, school_id=current_user.school_id,
    )


# ── 课节 ──

@router.get("/slots", response_model=list[CourseSlotOut])
async def list_slots(
    class_id: Optional[int] = Query(None),
    teacher_id: Optional[int] = Query(None),
    semester: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService.list_slots(
        db=db, school_id=current_user.school_id,
        class_id=class_id, teacher_id=teacher_id, semester=semester,
    )

@router.post("/slots")
async def create_slot(
    body: CourseSlotCreate,
    auto_resolve: bool = Query(False, description="冲突时是否强制创建"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService.create_slot(
        db=db, data=body, school_id=current_user.school_id,
        auto_resolve=auto_resolve,
    )

@router.delete("/slots/{slot_id}")
async def delete_slot(
    slot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ok = await TimetableService.delete_slot(db, slot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="课节不存在")
    return {"status": "deleted", "slot_id": slot_id}

@router.post("/slots/check-conflict", response_model=ConflictCheckResult)
async def check_conflict(
    body: CourseSlotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService._check_conflicts(
        db, body, school_id=current_user.school_id,
    )


# ── 周课表 ──

@router.get("/weekly/{class_id}", response_model=WeeklyScheduleOut)
async def get_weekly_schedule(
    class_id: int,
    semester: str = Query(..., description="学期: 2025-2026-1"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await TimetableService.get_weekly_schedule(
        db=db, class_id=class_id, semester=semester,
        school_id=current_user.school_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="班级不存在")
    return result

@router.get("/weekly/teacher/{teacher_id}", response_model=TeacherWeeklyScheduleOut)
async def get_teacher_weekly_schedule(
    teacher_id: int,
    semester: str = Query(..., description="学期: 2025-2026-1"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await TimetableService.get_teacher_weekly_schedule(
        db=db, teacher_id=teacher_id, semester=semester,
        school_id=current_user.school_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="教师不存在")
    return result


# ── 冲突管理 ──

@router.get("/conflicts")
async def list_conflicts(
    is_resolved: Optional[bool] = Query(None, description="true=已解决, false=未解决"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await TimetableService.list_conflicts(
        db=db, school_id=current_user.school_id,
        is_resolved=is_resolved, page=page, page_size=page_size,
    )

@router.put("/conflicts/{conflict_id}/resolve", response_model=ConflictOut)
async def resolve_conflict(
    conflict_id: int,
    resolution: str = Query(..., description="resolved_by_move/resolved_by_cancel/ignored"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await TimetableService.resolve_conflict(
        db=db, conflict_id=conflict_id, resolution=resolution,
        resolved_by=current_user.id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="冲突记录不存在")
    return result
