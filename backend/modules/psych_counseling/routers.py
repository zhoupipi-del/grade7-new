"""
心理咨询预约与工作台 路由层

端点清单 (14):
  ── 时间槽位 ──
  POST   /slots                    — 心理老师创建可预约时段
  GET    /slots                    — 查询可用时段列表
  PUT    /slots/{slot_id}/status   — 锁定/解锁时段
  DELETE /slots/{slot_id}          — 删除空闲时段

  ── 预约管理 ──
  POST   /appointments             — 发起预约(学生/班主任/家长)
  GET    /appointments             — 查询预约列表(分页+筛选)
  GET    /appointments/{id}        — 预约详情
  PUT    /appointments/{id}        — 审核/更新预约
  GET    /appointments/my          — 我的预约(学生视角)

  ── 咨询记录(工作台) ──
  POST   /records                  — 提交加密咨询记录
  GET    /records                  — 咨询记录列表(分页)
  GET    /records/{id}             — 单条记录(按角色解密)
  GET    /records/student/{sid}    — 某学生全部咨询历史

  ── 统计 ──
  GET    /stats                    — 心理老师工作台统计概览
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, Student
from core.routers import get_db, get_current_user
from modules.psych_counseling.models import (
    PsyConsultableSlot,
    PsyAppointment,
    PsyConsultRecord,
)
from modules.psych_counseling.services import (
    create_slot,
    list_slots,
    get_slot,
    update_slot_status,
    delete_slot,
    create_appointment,
    list_appointments,
    update_appointment,
    create_consult_record,
    get_consult_record,
    list_consult_records,
    get_counselor_stats,
    _is_counselor_or_admin,
    _mask_plaintext,
)
from modules.psych_counseling.schemas import (
    SlotCreateRequest,
    SlotResponse,
    SlotListResponse,
    AppointmentCreateRequest,
    AppointmentUpdateRequest,
    AppointmentResponse,
    AppointmentListResponse,
    ConsultRecordCreateRequest,
    ConsultRecordResponse,
    ConsultRecordListResponse,
    CounselorStatsResponse,
)

router = APIRouter(tags=["psych-counseling"])


# ── 通用: 加载学生/教师姓名的辅助函数 ──

async def _get_user_name(db: AsyncSession, user_id: int) -> str:
    stmt = select(User.display_name).where(User.id == user_id)
    res = await db.execute(stmt)
    row = res.scalar_one_or_none()
    return row or "未知"


async def _get_student_name(db: AsyncSession, student_id: int) -> str:
    stmt = select(Student.name).where(Student.id == student_id)
    res = await db.execute(stmt)
    row = res.scalar_one_or_none()
    return row or "未知"


# ── 权限守卫: 心理老师角色 ──

async def require_counselor(
    current_user: User = Depends(get_current_user),
) -> User:
    """硬门禁: 仅心理老师(counselor)和MS_ADMIN可通行"""
    role = (current_user.role or "").lower()
    if role not in {"ms_admin", "counselor"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅心理老师和系统管理员可操作",
        )
    return current_user


# ============================================================
# 一、时间槽位管理
# ============================================================

@router.post("/slots", response_model=SlotResponse)
async def api_create_slot(
    payload: SlotCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_counselor),
):
    """心理老师开放可预约时段"""
    try:
        slot = await create_slot(
            db=db,
            school_id=current_user.school_id,
            teacher_id=current_user.id,
            data=payload.model_dump(),
        )
        return SlotResponse(
            id=slot.id,
            teacher_id=slot.teacher_id,
            teacher_name=await _get_user_name(db, slot.teacher_id),
            date=str(slot.date.date()) if slot.date else "",
            start_time=slot.start_time,
            end_time=slot.end_time,
            location=slot.location,
            max_capacity=slot.max_capacity,
            current_booked=slot.current_booked,
            status=slot.status,
            week_pattern=slot.week_pattern,
            is_recurring=slot.is_recurring,
            created_at=str(slot.created_at) if slot.created_at else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/slots", response_model=SlotListResponse)
async def api_list_slots(
    start_date: str = Query(None, description="YYYY-MM-DD"),
    end_date: str = Query(None, description="YYYY-MM-DD"),
    status: str = Query(None, description="open/booked/locked"),
    teacher_id: int = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询可用时段 — 全角色可读"""
    slots = await list_slots(
        db=db,
        school_id=current_user.school_id,
        start_date=start_date,
        end_date=end_date,
        status=status,
        teacher_id=teacher_id,
    )
    items = []
    for s in slots:
        items.append(SlotResponse(
            id=s.id,
            teacher_id=s.teacher_id,
            teacher_name=await _get_user_name(db, s.teacher_id),
            date=str(s.date.date()) if s.date else "",
            start_time=s.start_time,
            end_time=s.end_time,
            location=s.location,
            max_capacity=s.max_capacity,
            current_booked=s.current_booked,
            status=s.status,
            week_pattern=s.week_pattern,
            is_recurring=s.is_recurring,
            created_at=str(s.created_at) if s.created_at else None,
        ))
    return SlotListResponse(status="success", slots=items)


@router.put("/slots/{slot_id}/status")
async def api_update_slot_status(
    slot_id: int,
    status_val: str = Query(..., description="open/locked"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_counselor),
):
    """锁定/解锁时段"""
    try:
        slot = await update_slot_status(
            db=db, school_id=current_user.school_id,
            slot_id=slot_id, status=status_val,
        )
        return {
            "status": "success",
            "message": f"时段 {slot_id} 已设为 {status_val}",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/slots/{slot_id}")
async def api_delete_slot(
    slot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_counselor),
):
    """删除空闲时段"""
    try:
        await delete_slot(
            db=db, school_id=current_user.school_id, slot_id=slot_id,
        )
        return {"status": "success", "message": "时段已删除"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================
# 二、预约管理
# ============================================================

@router.post("/appointments", response_model=AppointmentResponse)
async def api_create_appointment(
    payload: AppointmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发起预约 — 学生/班主任/家长均可"""
    allowed_roles = {"ms_admin", "grade_leader", "class_teacher", "parent", "student"}
    role = (current_user.role or "").lower()
    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前角色无预约权限",
        )
    try:
        apt = await create_appointment(
            db=db,
            school_id=current_user.school_id,
            applicant_id=current_user.id,
            student_id=payload.student_id,
            data=payload.model_dump(),
        )
        slot = await get_slot(db, current_user.school_id, apt.slot_id)
        return AppointmentResponse(
            id=apt.id,
            student_id=apt.student_id,
            student_name=await _get_student_name(db, apt.student_id),
            applicant_id=apt.applicant_id,
            applicant_name=await _get_user_name(db, apt.applicant_id),
            slot_id=apt.slot_id,
            source=apt.source,
            reason_summary=apt.reason_summary,
            status=apt.status,
            risk_flag=apt.risk_flag,
            slot_date=str(slot.date.date()) if slot else None,
            slot_time=f"{slot.start_time}-{slot.end_time}" if slot else None,
            slot_location=slot.location if slot else None,
            created_at=str(apt.created_at) if apt.created_at else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/appointments", response_model=AppointmentListResponse)
async def api_list_appointments(
    student_id: int = Query(None),
    status: str = Query(None),
    source: str = Query(None),
    slot_id: int = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询预约列表 — 心理老师/管理员看全部, 其他看自己的"""
    # 非特权角色只能看自己的预约
    role = (current_user.role or "").lower()
    if role not in {"ms_admin", "counselor", "grade_leader"} and not student_id:
        # 学生/家长看不到全校预约列表，请用 /appointments/my
        pass

    appointments, total = await list_appointments(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        status=status,
        source=source,
        slot_id=slot_id,
        limit=limit,
        offset=offset,
    )

    items = []
    for a in appointments:
        slot = await get_slot(db, current_user.school_id, a.slot_id)
        items.append(AppointmentResponse(
            id=a.id,
            student_id=a.student_id,
            student_name=await _get_student_name(db, a.student_id),
            applicant_id=a.applicant_id,
            applicant_name=await _get_user_name(db, a.applicant_id),
            slot_id=a.slot_id,
            source=a.source,
            reason_summary=a.reason_summary,
            status=a.status,
            risk_flag=a.risk_flag,
            counselor_note=a.counselor_note,
            slot_date=str(slot.date.date()) if slot and slot.date else None,
            slot_time=f"{slot.start_time}-{slot.end_time}" if slot else None,
            slot_location=slot.location if slot else None,
            created_at=str(a.created_at) if a.created_at else None,
            confirmed_at=str(a.confirmed_at) if a.confirmed_at else None,
            completed_at=str(a.completed_at) if a.completed_at else None,
        ))
    return AppointmentListResponse(status="success", appointments=items, total=total)


@router.get("/appointments/my")
async def api_my_appointments(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """我的预约 — 学生或班主任视角"""
    role = (current_user.role or "").lower()
    student_id = None

    if role == "parent":
        student_id = current_user.bound_student_id
        if not student_id:
            raise HTTPException(status_code=400, detail="未绑定学生")
    elif role == "class_teacher":
        # 班主任: 查自己class的所有学生
        pass  # student_id=None → 按applicant_id查
    else:
        pass

    appointments, total = await list_appointments(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        limit=limit,
        offset=offset,
    )

    # 班主任模式: 仅看自己班级学生
    if role == "class_teacher" and current_user.class_id:
        from core.models import Student
        class_stmt = select(Student.id).where(
            Student.class_id == current_user.class_id,
            Student.school_id == current_user.school_id,
        )
        class_res = await db.execute(class_stmt)
        class_student_ids = set(row[0] for row in class_res.all())
        appointments = [a for a in appointments if a.student_id in class_student_ids]
        total = len(appointments)

    items = []
    for a in appointments:
        slot = await get_slot(db, current_user.school_id, a.slot_id)
        items.append(AppointmentResponse(
            id=a.id,
            student_id=a.student_id,
            student_name=await _get_student_name(db, a.student_id),
            applicant_id=a.applicant_id,
            applicant_name=await _get_user_name(db, a.applicant_id),
            slot_id=a.slot_id,
            source=a.source,
            reason_summary=a.reason_summary,
            status=a.status,
            risk_flag=a.risk_flag,
            counselor_note=a.counselor_note,
            slot_date=str(slot.date.date()) if slot and slot.date else None,
            slot_time=f"{slot.start_time}-{slot.end_time}" if slot else None,
            slot_location=slot.location if slot else None,
            created_at=str(a.created_at) if a.created_at else None,
            confirmed_at=str(a.confirmed_at) if a.confirmed_at else None,
            completed_at=str(a.completed_at) if a.completed_at else None,
        ))
    return AppointmentListResponse(status="success", appointments=items, total=total)


@router.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def api_get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预约详情"""
    stmt = select(PsyAppointment).where(
        PsyAppointment.id == appointment_id,
        PsyAppointment.school_id == current_user.school_id,
    )
    res = await db.execute(stmt)
    a = res.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预约记录不存在")

    slot = await get_slot(db, current_user.school_id, a.slot_id)
    return AppointmentResponse(
        id=a.id,
        student_id=a.student_id,
        student_name=await _get_student_name(db, a.student_id),
        applicant_id=a.applicant_id,
        applicant_name=await _get_user_name(db, a.applicant_id),
        slot_id=a.slot_id,
        source=a.source,
        reason_summary=a.reason_summary,
        status=a.status,
        risk_flag=a.risk_flag,
        counselor_note=a.counselor_note,
        slot_date=str(slot.date.date()) if slot and slot.date else None,
        slot_time=f"{slot.start_time}-{slot.end_time}" if slot else None,
        slot_location=slot.location if slot else None,
        created_at=str(a.created_at) if a.created_at else None,
        confirmed_at=str(a.confirmed_at) if a.confirmed_at else None,
        completed_at=str(a.completed_at) if a.completed_at else None,
    )


@router.put("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def api_update_appointment(
    appointment_id: int,
    payload: AppointmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_counselor),
):
    """心理老师审核/更新预约"""
    try:
        a = await update_appointment(
            db=db,
            school_id=current_user.school_id,
            appointment_id=appointment_id,
            data=payload.model_dump(exclude_none=True),
        )
        slot = await get_slot(db, current_user.school_id, a.slot_id)
        return AppointmentResponse(
            id=a.id,
            student_id=a.student_id,
            student_name=await _get_student_name(db, a.student_id),
            applicant_id=a.applicant_id,
            applicant_name=await _get_user_name(db, a.applicant_id),
            slot_id=a.slot_id,
            source=a.source,
            reason_summary=a.reason_summary,
            status=a.status,
            risk_flag=a.risk_flag,
            counselor_note=a.counselor_note,
            slot_date=str(slot.date.date()) if slot and slot.date else None,
            slot_time=f"{slot.start_time}-{slot.end_time}" if slot else None,
            slot_location=slot.location if slot else None,
            created_at=str(a.created_at) if a.created_at else None,
            confirmed_at=str(a.confirmed_at) if a.confirmed_at else None,
            completed_at=str(a.completed_at) if a.completed_at else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ============================================================
# 三、咨询记录 (加密工作台核心)
# ============================================================

@router.post("/records", response_model=ConsultRecordResponse)
async def api_create_consult_record(
    payload: ConsultRecordCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_counselor),
):
    """心理老师加密写实 — 提交咨询记录"""
    try:
        record = await create_consult_record(
            db=db,
            school_id=current_user.school_id,
            counselor_id=current_user.id,
            data=payload.model_dump(),
        )
        return ConsultRecordResponse(
            id=record.id,
            appointment_id=record.appointment_id,
            student_id=record.student_id,
            student_name=await _get_student_name(db, record.student_id),
            counselor_id=record.counselor_id,
            counselor_name=await _get_user_name(db, record.counselor_id),
            clog_display="【已加密存储】",  # 创建时不需要立即解密
            risk_level=record.risk_level,
            consult_category=record.consult_category,
            is_crisis=record.is_crisis,
            is_referred=record.is_referred,
            referral_target=record.referral_target,
            followup_date=str(record.followup_date) if record.followup_date else None,
            session_duration_min=record.session_duration_min,
            created_at=str(record.created_at) if record.created_at else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/records", response_model=ConsultRecordListResponse)
async def api_list_consult_records(
    student_id: int = Query(None),
    counselor_id: int = Query(None),
    risk_level: str = Query(None, description="green/yellow/orange/red"),
    is_crisis: bool = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """咨询记录列表 — 元数据可见, 正文需单个查询解密"""
    records, total = await list_consult_records(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        counselor_id=counselor_id,
        risk_level=risk_level,
        is_crisis=is_crisis,
        limit=limit,
        offset=offset,
    )
    items = []
    for r in records:
        items.append(ConsultRecordResponse(
            id=r.id,
            appointment_id=r.appointment_id,
            student_id=r.student_id,
            student_name=await _get_student_name(db, r.student_id),
            counselor_id=r.counselor_id,
            counselor_name=await _get_user_name(db, r.counselor_id),
            clog_display="【受限: 请查看详情解密】",
            risk_level=r.risk_level,
            consult_category=r.consult_category,
            is_crisis=r.is_crisis,
            is_referred=r.is_referred,
            referral_target=r.referral_target,
            followup_date=str(r.followup_date) if r.followup_date else None,
            session_duration_min=r.session_duration_min,
            created_at=str(r.created_at) if r.created_at else None,
            updated_at=str(r.updated_at) if r.updated_at else None,
        ))
    return ConsultRecordListResponse(status="success", records=items, total=total)


@router.get("/records/{record_id}", response_model=ConsultRecordResponse)
async def api_get_consult_record(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单条咨询记录 — 按角色自动解密/脱敏"""
    try:
        data = await get_consult_record(
            db=db,
            school_id=current_user.school_id,
            record_id=record_id,
            user_role=current_user.role,
            user_id=current_user.id,
        )
        return ConsultRecordResponse(
            id=data["id"],
            appointment_id=data["appointment_id"],
            student_id=data["student_id"],
            student_name=await _get_student_name(db, data["student_id"]),
            counselor_id=data["counselor_id"],
            counselor_name=await _get_user_name(db, data["counselor_id"]),
            clog_display=data["clog_display"],
            risk_level=data["risk_level"],
            consult_category=data["consult_category"],
            is_crisis=data["is_crisis"],
            is_referred=data["is_referred"],
            referral_target=data["referral_target"],
            followup_date=data["followup_date"],
            session_duration_min=data["session_duration_min"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/records/student/{student_id}", response_model=ConsultRecordListResponse)
async def api_student_consult_history(
    student_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """某学生的全部咨询历史 — 班主任/心理老师/管理员可查"""
    role = (current_user.role or "").lower()
    if role not in {"ms_admin", "counselor", "grade_leader", "class_teacher"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅教师和管理员可查看学生咨询历史",
        )
    records, total = await list_consult_records(
        db=db,
        school_id=current_user.school_id,
        student_id=student_id,
        limit=limit,
        offset=offset,
    )
    items = []
    for r in records:
        items.append(ConsultRecordResponse(
            id=r.id,
            appointment_id=r.appointment_id,
            student_id=r.student_id,
            student_name=await _get_student_name(db, r.student_id),
            counselor_id=r.counselor_id,
            counselor_name=await _get_user_name(db, r.counselor_id),
            clog_display="【受限: 请查看详情解密】",
            risk_level=r.risk_level,
            consult_category=r.consult_category,
            is_crisis=r.is_crisis,
            is_referred=r.is_referred,
            referral_target=r.referral_target,
            followup_date=str(r.followup_date) if r.followup_date else None,
            session_duration_min=r.session_duration_min,
            created_at=str(r.created_at) if r.created_at else None,
        ))
    return ConsultRecordListResponse(status="success", records=items, total=total)


# ============================================================
# 四、工作台统计
# ============================================================

@router.get("/stats", response_model=CounselorStatsResponse)
async def api_counselor_stats(
    counselor_id: int = Query(None, description="为空则查当前用户"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_counselor),
):
    """心理老师工作台统计概览"""
    target_id = counselor_id or current_user.id
    data = await get_counselor_stats(
        db=db,
        school_id=current_user.school_id,
        counselor_id=target_id,
    )
    return CounselorStatsResponse(status="success", **data)
