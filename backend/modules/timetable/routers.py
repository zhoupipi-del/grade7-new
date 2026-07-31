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
from datetime import datetime

from core.models import User, UserRole
from core.redis_client import get_redis
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query, status
from modules.timetable.models import TimetableScheduleInstance
from modules.timetable.schemas import (
    ClassroomCreate,
    ClassroomOut,
    ConflictCheckResult,
    ConflictOut,
    CourseCreate,
    CourseOut,
    CourseSlotCreate,
    CourseSlotOut,
    TeacherWeeklyScheduleOut,
    TimetableAdjustmentRequest,
    WeeklyScheduleOut,
)
from modules.timetable.services import TimetableService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("timetable.routers")
router = APIRouter()


# ── 教室 ──


@router.get("/classrooms", response_model=list[ClassroomOut])
async def list_classrooms(
    room_type: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    return await TimetableService.list_classrooms(
        db=db,
        school_id=current_user.school_id,
        room_type=room_type,
    )


@router.post("/classrooms", status_code=201, response_model=ClassroomOut)
async def create_classroom(
    body: ClassroomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    return await TimetableService.create_classroom(
        db=db,
        data=body,
        school_id=current_user.school_id,
    )


# ── 课程 ──


@router.get("/courses", response_model=list[CourseOut])
async def list_courses(
    subject_category: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    return await TimetableService.list_courses(
        db=db,
        school_id=current_user.school_id,
        subject_category=subject_category,
    )


@router.post("/courses", status_code=201, response_model=CourseOut)
async def create_course(
    body: CourseCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    return await TimetableService.create_course(
        db=db,
        data=body,
        school_id=current_user.school_id,
    )


# ── 课节 ──


@router.get("/slots", response_model=list[CourseSlotOut])
async def list_slots(
    class_id: int | None = Query(None),
    teacher_id: int | None = Query(None),
    semester: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    return await TimetableService.list_slots(
        db=db,
        school_id=current_user.school_id,
        class_id=class_id,
        teacher_id=teacher_id,
        semester=semester,
    )


@router.post("/slots")
async def create_slot(
    body: CourseSlotCreate,
    auto_resolve: bool = Query(False, description="冲突时是否强制创建"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    return await TimetableService.create_slot(
        db=db,
        data=body,
        school_id=current_user.school_id,
        auto_resolve=auto_resolve,
    )


@router.delete("/slots/{slot_id}")
async def delete_slot(
    slot_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
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
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
):
    return await TimetableService._check_conflicts(
        db,
        body,
        school_id=current_user.school_id,
    )


# ── 周课表 ──


@router.get("/weekly/{class_id}", response_model=WeeklyScheduleOut)
async def get_weekly_schedule(
    class_id: int,
    semester: str = Query(..., description="学期: 2025-2026-1"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    result = await TimetableService.get_weekly_schedule(
        db=db,
        class_id=class_id,
        semester=semester,
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
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    result = await TimetableService.get_teacher_weekly_schedule(
        db=db,
        teacher_id=teacher_id,
        semester=semester,
        school_id=current_user.school_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="教师不存在")
    return result


# ── 冲突管理 ──


@router.get("/conflicts")
async def list_conflicts(
    is_resolved: bool | None = Query(None, description="true=已解决, false=未解决"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    return await TimetableService.list_conflicts(
        db=db,
        school_id=current_user.school_id,
        is_resolved=is_resolved,
        page=page,
        page_size=page_size,
    )


@router.put("/conflicts/{conflict_id}/resolve", response_model=ConflictOut)
async def resolve_conflict(
    conflict_id: int,
    resolution: str = Query(..., description="resolved_by_move/resolved_by_cancel/ignored"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    result = await TimetableService.resolve_conflict(
        db=db,
        conflict_id=conflict_id,
        resolution=resolution,
        resolved_by=current_user.id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="冲突记录不存在")
    return result


# ── 教务变轨 (Wings 3.1 阵地⑦) ──


@router.get("/instances")
async def list_schedule_instances(
    class_id: int = Query(..., description="班级ID"),
    start_date: str = Query(..., description="起始日期 YYYY-MM-DD"),
    end_date: str = Query(..., description="结束日期 YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """查询班级在指定日期范围内的日历级课表实例"""
    try:
        d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误, 需要 YYYY-MM-DD")

    stmt = (
        select(TimetableScheduleInstance)
        .where(
            TimetableScheduleInstance.school_id == current_user.school_id,
            TimetableScheduleInstance.class_id == class_id,
            TimetableScheduleInstance.date >= d_start,
            TimetableScheduleInstance.date <= d_end,
        )
        .order_by(TimetableScheduleInstance.date, TimetableScheduleInstance.period_index)
    )

    result = await db.execute(stmt)
    instances = result.scalars().all()

    return {
        "total": len(instances),
        "instances": [
            {
                "id": inst.id,
                "class_id": inst.class_id,
                "date": inst.date.isoformat(),
                "slot_id": inst.slot_id,
                "period_index": inst.period_index,
                "subject_id": inst.subject_id,
                "teacher_id": inst.teacher_id,
                "is_adjusted": inst.is_adjusted,
            }
            for inst in instances
        ],
    }


@router.put("/instances/{instance_id}/adjust")
async def adjust_timetable_instance(
    instance_id: int,
    payload: TimetableAdjustmentRequest,
    current_user: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER)),
    db: AsyncSession = Depends(get_db),
):
    """
    Wings 3.1 阵地⑦：教务变轨端点
    修改指定课时实例, 同步引爆 Redis 对应班级当天的缓存, 确保 CEP 引擎毫秒级感知
    """
    logger.info(
        f"⚡ 收到教务变轨请求: 实例ID={instance_id} "
        f"-> 学科={payload.subject_id}, 教师={payload.teacher_id}"
    )

    # 1. 锁定原始时空实例 (带 school_id 多租户铁闸)
    stmt = select(TimetableScheduleInstance).where(
        TimetableScheduleInstance.id == instance_id,
        TimetableScheduleInstance.school_id == current_user.school_id,
    )
    res = await db.execute(stmt)
    instance = res.scalar_one_or_none()

    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到指定ID [{instance_id}] 的课表实例",
        )

    old_subject_id = instance.subject_id
    old_teacher_id = instance.teacher_id
    target_class_id = instance.class_id
    target_date_str = instance.date.isoformat()

    try:
        # 2. 状态机原子性变轨
        instance.subject_id = payload.subject_id
        instance.teacher_id = payload.teacher_id
        instance.is_adjusted = True
        # adjustment_reason 存入 adjustment_log_id 字段做溯源 (无独立 note 列)
        # 如果有调课原因, 记到日志里供审计追溯
        if payload.adjustment_reason:
            logger.info(
                f"📋 变轨原因: instance_id={instance_id} reason={payload.adjustment_reason}"
            )

        await db.commit()
        logger.info(
            f"💾 MySQL 变轨落盘成功: 实例ID={instance_id} "
            f"[学科 {old_subject_id} -> {payload.subject_id}, "
            f"教师 {old_teacher_id} -> {payload.teacher_id}]"
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"❌ MySQL 变轨事务回滚, 原因: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="数据库变轨落盘失败",
        )

    # 3. 核心决杀: 精准引爆 Redis 双层缓存网
    cache_key = f"wings:timetable:instances:{target_class_id}:{target_date_str}"
    redis = get_redis()

    if redis is not None:
        try:
            evict_res = await redis.delete(cache_key)
            if evict_res:
                logger.info(
                    f"🔥 [Cache Evict] 成功蒸发 Redis 动态缓存键: {cache_key}, "
                    f"下一波流量将强制下穿 MySQL 获取最新坐标!"
                )
            else:
                logger.warning(
                    f"⚠️ [Cache Evict] 尝试清除缓存键 {cache_key}, "
                    f"但该键当前在 Redis 中不存在 (可能已自然过期)"
                )
        except Exception as redis_err:
            # 缓存清除失败不阻断主业务, 但拉响最高级别日志
            logger.critical(
                f"🚨 [CRITICAL] Redis 缓存蒸发管道遭遇阻塞! "
                f"键名={cache_key}, 错误: {str(redis_err)}"
            )
    else:
        logger.warning("⚠️ Redis 客户端不可用, 跳过缓存蒸发 (降级模式)")

    return {
        "status": "success",
        "msg": "教务变轨成功, 时空同步网已更新",
        "data": {
            "instance_id": instance_id,
            "class_id": target_class_id,
            "date": target_date_str,
            "old_subject_id": old_subject_id,
            "new_subject_id": payload.subject_id,
            "old_teacher_id": old_teacher_id,
            "new_teacher_id": payload.teacher_id,
            "adjusted": True,
        },
    }
