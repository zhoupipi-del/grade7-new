"""
modules/exam/routers.py — 考试管理 API 端点（24 个端点）

端点清单:
  考试科目安排 (5):
    POST   /subjects              — 创建科目安排 (MS_ADMIN)
    GET    /subjects              — 列出科目安排 (认证用户)
    GET    /subjects/{id}         — 获取单个 (认证用户)
    PUT    /subjects/{id}         — 更新 (MS_ADMIN)
    DELETE /subjects/{id}         — 删除 (MS_ADMIN)

  考场管理 (6):
    POST   /rooms                 — 创建考场 (MS_ADMIN)
    GET    /rooms                 — 列出考场 (认证用户)
    GET    /rooms/{id}            — 获取单个 (认证用户)
    PUT    /rooms/{id}            — 更新 (MS_ADMIN)
    PATCH  /rooms/{id}/toggle     — 启停 (MS_ADMIN)
    POST   /rooms/seed            — 从班级表批量生成 (MS_ADMIN)

  考试安排 (4):
    POST   /arrangements          — 创建排考 (MS_ADMIN)
    GET    /arrangements          — 列出排考 (认证用户)
    PUT    /arrangements/{id}     — 更新 (MS_ADMIN)
    DELETE /arrangements/{id}     — 删除 (MS_ADMIN)

  座位分配 (3):
    POST   /seats/assign          — 批量编排 (MS_ADMIN)
    GET    /seats                 — 查询座位 (认证用户)
    PUT    /seats/{id}/override   — 手动修改 (MS_ADMIN, 补丁3)

  监考安排 (4):
    POST   /invigilators          — 指派监考 (MS_ADMIN, 补丁2: 冲突→409)
    GET    /invigilators          — 查询监考 (认证用户)
    DELETE /invigilators/{id}     — 取消监考 (MS_ADMIN)
    GET    /invigilators/conflicts/{user_id} — 查询冲突 (MS_ADMIN)

  录入窗口 (7):
    POST   /entry-windows         — 创建窗口 (MS_ADMIN)
    POST   /entry-windows/bulk    — 批量创建 (MS_ADMIN)
    GET    /entry-windows         — 查询窗口 (认证用户)
    PATCH  /entry-windows/{id}/open  — 开放录入 (MS_ADMIN)
    PATCH  /entry-windows/{id}/close — 关闭录入 (MS_ADMIN)
    GET    /entry-windows/progress — 录入进度 (认证用户)
    GET    /entry-windows/check    — 检查录入权限 (认证用户)
"""

from datetime import date

from core.models import User, UserRole
from core.routers import get_current_user, get_db, require_role
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    ArrangementCreate,
    ArrangementOut,
    ArrangementUpdate,
    EntryWindowBulkCreateRequest,
    EntryWindowBulkCreateResult,
    EntryWindowCreate,
    EntryWindowOut,
    InvigilatorCreate,
    InvigilatorOut,
    RoomCreate,
    RoomItem,
    RoomOut,
    RoomSeedRequest,
    RoomSeedResult,
    RoomUpdate,
    SeatAssignmentOut,
    SeatAssignRequest,
    SeatAssignResult,
    SeatOverrideUpdate,
    SubjectScheduleCreate,
    SubjectScheduleOut,
    SubjectScheduleUpdate,
)
from .services import (
    ArrangementService,
    EntryWindowService,
    InvigilatorService,
    RoomService,
    SeatService,
    SubjectScheduleService,
)

router = APIRouter(tags=["exam"])


# ═══════════════════════════════════════════════════════════════
# 考试科目安排 (5)
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/subjects",
    response_model=SubjectScheduleOut,
    summary="创建考试科目安排",
    description="为某场考试添加科目安排（科目×日期×时间×满分），需 MS_ADMIN",
)
async def create_subject_schedule(
    body: SubjectScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """创建考试科目安排。同一考试同一科目不可重复。"""
    try:
        return await SubjectScheduleService.create(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/subjects",
    response_model=list[SubjectScheduleOut],
    summary="列出考试科目安排",
    description="按考试ID列出科目安排，可选仅返回启用的",
)
async def list_subject_schedules(
    exam_id: int = Query(..., description="考试ID"),
    active_only: bool = Query(default=False, description="仅返回启用的"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出某场考试的科目安排，按 sort_order 排序。"""
    return await SubjectScheduleService.list_by_exam(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        active_only=active_only,
    )


@router.get(
    "/subjects/{schedule_id}",
    response_model=SubjectScheduleOut,
    summary="获取单个科目安排",
)
async def get_subject_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await SubjectScheduleService.get(
        db=db,
        school_id=current_user.school_id,
        schedule_id=schedule_id,
    )
    if not result:
        raise HTTPException(status_code=404, detail="科目安排不存在")
    return result


@router.put(
    "/subjects/{schedule_id}",
    response_model=SubjectScheduleOut,
    summary="更新科目安排",
)
async def update_subject_schedule(
    schedule_id: int,
    body: SubjectScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        return await SubjectScheduleService.update(
            db=db,
            school_id=current_user.school_id,
            schedule_id=schedule_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/subjects/{schedule_id}",
    summary="删除科目安排",
)
async def delete_subject_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        await SubjectScheduleService.delete(
            db=db,
            school_id=current_user.school_id,
            schedule_id=schedule_id,
        )
        return {"detail": "已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 考场管理 (6)
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/rooms",
    response_model=RoomOut,
    summary="创建考场",
    description="手动添加考场（教室/体育馆/实验室），需 MS_ADMIN",
)
async def create_room(
    body: RoomCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        return await RoomService.create(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/rooms",
    response_model=list[RoomItem],
    summary="列出考场",
    description="获取学校所有考场，可按类型过滤",
)
async def list_rooms(
    room_type: str | None = Query(default=None, description="类型: classroom/hall/lab"),
    active_only: bool = Query(default=False, description="仅返回启用的"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await RoomService.list(
        db=db,
        school_id=current_user.school_id,
        room_type=room_type,
        active_only=active_only,
    )


@router.get(
    "/rooms/{room_id}",
    response_model=RoomOut,
    summary="获取单个考场",
)
async def get_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = await RoomService.get(
        db=db,
        school_id=current_user.school_id,
        room_id=room_id,
    )
    if not room:
        raise HTTPException(status_code=404, detail="考场不存在")
    return room


@router.put(
    "/rooms/{room_id}",
    response_model=RoomOut,
    summary="更新考场",
)
async def update_room(
    room_id: int,
    body: RoomUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        return await RoomService.update(
            db=db,
            school_id=current_user.school_id,
            room_id=room_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/rooms/{room_id}/toggle",
    response_model=RoomOut,
    summary="启停考场",
)
async def toggle_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        return await RoomService.toggle_active(
            db=db,
            school_id=current_user.school_id,
            room_id=room_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/rooms/seed",
    response_model=RoomSeedResult,
    summary="从班级表批量生成考场",
    description="把班级教室初始化为考场记录，已存在的自动跳过",
)
async def seed_rooms(
    body: RoomSeedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """从 classes 表自动生成考场，room_code 格式 R-{class_id}。"""
    return await RoomService.seed_from_classes(
        db=db,
        school_id=current_user.school_id,
        data=body,
    )


# ═══════════════════════════════════════════════════════════════
# 考试安排 (4)
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/arrangements",
    response_model=ArrangementOut,
    summary="创建考试安排",
    description="排考: 科目×考场×时间段，需 MS_ADMIN",
)
async def create_arrangement(
    body: ArrangementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        return await ArrangementService.create(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/arrangements",
    summary="列出考试安排",
    description="按考试/科目/考场/日期过滤",
)
async def list_arrangements(
    exam_id: int | None = Query(default=None, description="考试ID"),
    subject_id: int | None = Query(default=None, description="科目ID"),
    room_id: int | None = Query(default=None, description="考场ID"),
    exam_date: date | None = Query(default=None, description="考试日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    arrangements = await ArrangementService.list(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        subject_id=subject_id,
        room_id=room_id,
        exam_date=exam_date,
    )
    return [ArrangementOut.model_validate(a) for a in arrangements]


@router.put(
    "/arrangements/{arrangement_id}",
    response_model=ArrangementOut,
    summary="更新考试安排",
)
async def update_arrangement(
    arrangement_id: int,
    body: ArrangementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        return await ArrangementService.update(
            db=db,
            school_id=current_user.school_id,
            arrangement_id=arrangement_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/arrangements/{arrangement_id}",
    summary="删除考试安排",
)
async def delete_arrangement(
    arrangement_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        await ArrangementService.delete(
            db=db,
            school_id=current_user.school_id,
            arrangement_id=arrangement_id,
        )
        return {"detail": "已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 座位分配 (3)
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/seats/assign",
    response_model=SeatAssignResult,
    summary="批量编排座位",
    description="按 random/serpentine 方式批量分配座位，需 MS_ADMIN。\n\n"
    "⚠️ 补丁3: is_manual_override=1 的座位在重排时跳过，保护特殊需求。",
)
async def assign_seats(
    body: SeatAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    批量座位编排:

    - **random**: 随机打乱后顺序填入考场
    - **serpentine**: 按最近一次考试总分排名蛇形分配（防优生扎堆）

    重排时自动保留 is_manual_override=1 的人工覆盖座位。
    """
    try:
        return await SeatService.assign_seats(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/seats",
    summary="查询座位分配",
    description="按考试+科目查询座位分配详情（含学生姓名、考场名）",
)
async def list_seats(
    exam_id: int = Query(..., description="考试ID"),
    subject_id: int = Query(..., description="科目ID"),
    room_id: int | None = Query(default=None, description="按考场过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询座位分配，按考场+座位号排序。"""
    return await SeatService.list_by_exam_subject(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        subject_id=subject_id,
        room_id=room_id,
    )


@router.put(
    "/seats/{assignment_id}/override",
    response_model=SeatAssignmentOut,
    summary="手动修改座位（补丁3）",
    description="手动修改学生座位，自动标记 is_manual_override=1。\n\n"
    "用于特殊需求：伤残/视力障碍/靠门第一排等。\n"
    "修改后算法重排时跳过此座位。",
)
async def override_seat(
    assignment_id: int,
    body: SeatOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        return await SeatService.manual_override(
            db=db,
            school_id=current_user.school_id,
            assignment_id=assignment_id,
            data=body,
        )
    except ValueError as e:
        if "已被其他学生占用" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# 监考安排 (4)
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/invigilators",
    response_model=InvigilatorOut,
    summary="指派监考教师",
    description="为某考场指派主/副监考教师，需 MS_ADMIN。\n\n"
    "⚠️ 补丁2: 同一教师同一日期的时间段不可重叠，\n"
    "冲突时返回 409 Conflict。",
)
async def assign_invigilator(
    body: InvigilatorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    指派监考教师:

    - 前置校验：开始时间 < 结束时间
    - **补丁2**: 时间重叠冲突检测 — 同一教师同一日期的时间段不可重叠
    - 冲突时返回 409 Conflict，包含冲突详情
    """
    try:
        return await InvigilatorService.assign(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
    except ValueError as e:
        if "TIME_OVERLAP_CONFLICT" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/invigilators",
    summary="查询监考安排",
    description="按考试/科目/考场/教师/日期过滤，含教师姓名和考场名",
)
async def list_invigilators(
    exam_id: int | None = Query(default=None, description="考试ID"),
    subject_id: int | None = Query(default=None, description="科目ID"),
    room_id: int | None = Query(default=None, description="考场ID"),
    user_id: int | None = Query(default=None, description="教师用户ID"),
    exam_date: date | None = Query(default=None, description="考试日期"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询监考安排，按日期+时间排序。"""
    return await InvigilatorService.list(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        subject_id=subject_id,
        room_id=room_id,
        user_id=user_id,
        exam_date=exam_date,
    )


@router.delete(
    "/invigilators/{invigilator_id}",
    summary="取消监考安排",
)
async def delete_invigilator(
    invigilator_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    try:
        await InvigilatorService.delete(
            db=db,
            school_id=current_user.school_id,
            invigilator_id=invigilator_id,
        )
        return {"detail": "已取消"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/invigilators/conflicts/{user_id}",
    summary="查询教师监考冲突",
    description="扫描某教师所有监考安排，找出存在时间段重叠的记录对",
)
async def check_invigilator_conflicts(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """查询教师监考时间冲突列表。"""
    return await InvigilatorService.check_conflicts(
        db=db,
        school_id=current_user.school_id,
        user_id=user_id,
    )


# ═══════════════════════════════════════════════════════════════
# 成绩录入窗口 (7)
# ═══════════════════════════════════════════════════════════════


@router.post(
    "/entry-windows",
    response_model=EntryWindowOut,
    summary="创建录入窗口",
    description="为某科目创建成绩录入窗口，需 MS_ADMIN。\n\n"
    "⚠️ 补丁1: class_id=NULL 表示全校通开，非NULL精确到班级。",
)
async def create_entry_window(
    body: EntryWindowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """
    创建成绩录入窗口:

    - **class_id=NULL**: 全校该科目通开（粗粒度）
    - **class_id=指定值**: 精确到班级（防跨班级篡改）
    - 指定 class_id 时自动填充 expected_count（班级人数）
    """
    try:
        return await EntryWindowService.create(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/entry-windows/bulk",
    response_model=EntryWindowBulkCreateResult,
    summary="批量创建录入窗口",
    description="为一场考试的所有科目×所有班级批量创建窗口，需 MS_ADMIN",
)
async def bulk_create_entry_windows(
    body: EntryWindowBulkCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """批量创建录入窗口，已存在的自动跳过。"""
    try:
        return await EntryWindowService.bulk_create(
            db=db,
            school_id=current_user.school_id,
            data=body,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/entry-windows",
    response_model=list[EntryWindowOut],
    summary="查询录入窗口",
    description="按考试/科目/班级/状态过滤",
)
async def list_entry_windows(
    exam_id: int | None = Query(default=None, description="考试ID"),
    subject_id: int | None = Query(default=None, description="科目ID"),
    class_id: int | None = Query(default=None, description="班级ID"),
    status: str | None = Query(default=None, description="状态: pending/open/closed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await EntryWindowService.list(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        subject_id=subject_id,
        class_id=class_id,
        status=status,
    )


@router.patch(
    "/entry-windows/{window_id}/open",
    response_model=EntryWindowOut,
    summary="开放录入窗口",
    description="将窗口状态从 pending 变更为 open，需 MS_ADMIN",
)
async def open_entry_window(
    window_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """开放录入窗口 (pending → open)。班主任在 open 状态下才能录入成绩。"""
    try:
        return await EntryWindowService.open_window(
            db=db,
            school_id=current_user.school_id,
            window_id=window_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/entry-windows/{window_id}/close",
    response_model=EntryWindowOut,
    summary="关闭录入窗口",
    description="将窗口状态从 open 变更为 closed，需 MS_ADMIN",
)
async def close_entry_window(
    window_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_role(UserRole.MS_ADMIN)),
):
    """关闭录入窗口 (open → closed)。关闭后班主任无法再录入成绩。"""
    try:
        return await EntryWindowService.close_window(
            db=db,
            school_id=current_user.school_id,
            window_id=window_id,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/entry-windows/progress",
    summary="查询录入进度",
    description="按考试+科目查询录入进度（已录入/应录入/完成率）",
)
async def get_entry_progress(
    exam_id: int = Query(..., description="考试ID"),
    subject_id: int | None = Query(default=None, description="科目ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询成绩录入进度，返回各状态窗口数和完成率。"""
    return await EntryWindowService.get_progress(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        subject_id=subject_id,
    )


@router.get(
    "/entry-windows/check",
    summary="检查录入权限",
    description="检查某班级某科目是否可以录入成绩（窗口是否 open）",
)
async def check_entry_permission(
    exam_id: int = Query(..., description="考试ID"),
    subject_id: int = Query(..., description="科目ID"),
    class_id: int = Query(..., description="班级ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    检查录入权限:

    ⚠️ 补丁1: 双重检查
    1. 先查 class-specific 窗口 (class_id = 指定班级)
    2. 如无，再查 school-wide 窗口 (class_id IS NULL)
    3. 任一 open 即可录入
    """
    can_enter = await EntryWindowService.check_entry_permission(
        db=db,
        school_id=current_user.school_id,
        exam_id=exam_id,
        subject_id=subject_id,
        class_id=class_id,
    )
    return {
        "can_enter": can_enter,
        "exam_id": exam_id,
        "subject_id": subject_id,
        "class_id": class_id,
    }
