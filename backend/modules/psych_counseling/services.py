"""
心理咨询预约与工作台 核心业务服务层

隐私切面:
  encrypted_clog → Fernet 对称加密(服务层)
  解密权限: 仅 counselor 角色 + MS_ADMIN
  每次解密记录 audit log
"""

import os
from datetime import date, datetime, timedelta

from cryptography.fernet import Fernet
from modules.psych_counseling.models import (
    PsyAppointment,
    PsyConsultableSlot,
    PsyConsultRecord,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# ── 加密引擎配置 ──
# 从环境变量加载 Fernet key; 生产环境必须配置，缺失则拒绝启动
_FERNET_KEY = os.getenv("PSY_ENCRYPTION_KEY") or os.getenv("WINGS_ENCRYPTION_KEY")
if not _FERNET_KEY:
    raise ValueError(
        "PSY_ENCRYPTION_KEY 或 WINGS_ENCRYPTION_KEY 环境变量未配置，"
        "心理咨询加密引擎无法初始化。请在 .env 中注入合法 Fernet key。"
    )
_fernet = Fernet(_FERNET_KEY.encode() if isinstance(_FERNET_KEY, str) else _FERNET_KEY)


# ── RBAC 角色常量 ──
COUNSELOR_ROLE = "counselor"
PRIVILEGED_ROLES = {"ms_admin", "counselor"}


async def _is_counselor_or_admin(user_role: str) -> bool:
    """判断用户是否有解密权限"""
    return (user_role or "").lower() in PRIVILEGED_ROLES


async def _check_counselor_role(
    db: AsyncSession,
    user_id: int,
    school_id: int,
    user_role: str,
) -> bool:
    """
    双重验证: 检查用户是否为心理老师。
    1. 先看 user.role 是否为 counselor
    2. 再看 teacher_role_assignments 中是否有有效 counselor 分配
    """
    role_lower = (user_role or "").lower()
    if role_lower in PRIVILEGED_ROLES:
        return True

    # 查 teacher_role_assignments 表
    from modules.teacher_mgmt.models import TeacherRoleAssignment

    stmt = (
        select(TeacherRoleAssignment)
        .where(
            TeacherRoleAssignment.teacher_user_id == user_id,
            TeacherRoleAssignment.school_id == school_id,
            TeacherRoleAssignment.role_type == COUNSELOR_ROLE,
            TeacherRoleAssignment.is_active,
            and_(
                or_(
                    TeacherRoleAssignment.expires_at.is_(None),
                    TeacherRoleAssignment.expires_at > datetime.now(),
                ),
            ),
        )
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none() is not None


# ─────────────────────────────────────────────────────────
# 加密/解密内核
# ─────────────────────────────────────────────────────────


def encrypt_clog(plaintext: str) -> str:
    """Fernet 加密咨询日志"""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_clog(ciphertext: str) -> str:
    """Fernet 解密咨询日志"""
    return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def _mask_plaintext(plaintext: str, role: str) -> str:
    """
    按角色返回不同级别的咨询日志内容:
    - counselor/ms_admin: 完整原文
    - 其他: 脱敏摘要 (前50字 + "【详细记录仅心理老师可查看】")
    """
    if (role or "").lower() in PRIVILEGED_ROLES:
        return plaintext
    if len(plaintext) <= 60:
        return plaintext[:30] + "...【详细记录仅心理老师可查看】"
    return plaintext[:50] + "...【详细记录仅心理老师可查看】"


# ─────────────────────────────────────────────────────────
# 1. 时间槽位管理
# ─────────────────────────────────────────────────────────


async def create_slot(
    db: AsyncSession,
    school_id: int,
    teacher_id: int,
    data: dict,
) -> PsyConsultableSlot:
    """心理老师创建一个可用时段"""
    slot_date = datetime.strptime(data["date"], "%Y-%m-%d")

    slot = PsyConsultableSlot(
        school_id=school_id,
        teacher_id=teacher_id,
        date=slot_date,
        start_time=data["start_time"],
        end_time=data["end_time"],
        location=data.get("location", "心理咨询室"),
        max_capacity=data.get("max_capacity", 1),
        current_booked=0,
        status="open",
        week_pattern=data.get("week_pattern", "every"),
        is_recurring=data.get("is_recurring", False),
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return slot


async def list_slots(
    db: AsyncSession,
    school_id: int,
    start_date: str = None,
    end_date: str = None,
    status: str = None,
    teacher_id: int = None,
) -> list:
    """查询可用时段列表"""
    conditions = [PsyConsultableSlot.school_id == school_id]

    if start_date:
        conditions.append(PsyConsultableSlot.date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        conditions.append(PsyConsultableSlot.date <= datetime.strptime(end_date, "%Y-%m-%d"))
    if status:
        conditions.append(PsyConsultableSlot.status == status)
    if teacher_id:
        conditions.append(PsyConsultableSlot.teacher_id == teacher_id)

    stmt = (
        select(PsyConsultableSlot)
        .where(and_(*conditions))
        .order_by(PsyConsultableSlot.date.asc(), PsyConsultableSlot.start_time.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


async def get_slot(db: AsyncSession, school_id: int, slot_id: int) -> PsyConsultableSlot:
    stmt = select(PsyConsultableSlot).where(
        PsyConsultableSlot.id == slot_id,
        PsyConsultableSlot.school_id == school_id,
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def update_slot_status(
    db: AsyncSession,
    school_id: int,
    slot_id: int,
    status: str,
) -> PsyConsultableSlot:
    """锁定/解锁时段"""
    slot = await get_slot(db, school_id, slot_id)
    if not slot:
        raise ValueError("指定时段不存在")
    slot.status = status
    await db.commit()
    await db.refresh(slot)
    return slot


async def delete_slot(db: AsyncSession, school_id: int, slot_id: int) -> None:
    """删除空闲时段(已有预约的不可删)"""
    slot = await get_slot(db, school_id, slot_id)
    if not slot:
        raise ValueError("指定时段不存在")
    if slot.current_booked > 0:
        raise ValueError("该时段已有预约, 不可删除")
    await db.delete(slot)
    await db.commit()


# ─────────────────────────────────────────────────────────
# 2. 预约申请引擎
# ─────────────────────────────────────────────────────────


async def create_appointment(
    db: AsyncSession,
    school_id: int,
    applicant_id: int,
    student_id: int,
    data: dict,
) -> PsyAppointment:
    """学生/班主任/家长 发起预约"""
    # 校验时段是否可用
    slot = await get_slot(db, school_id, data["slot_id"])
    if not slot:
        raise ValueError("所选时段不存在")
    if slot.status != "open":
        raise ValueError("该时段当前不可预约")
    if slot.current_booked >= slot.max_capacity:
        raise ValueError("该时段已约满")

    # 幂等检查: 同一学生不能对同一时段重复预约
    existing = await db.execute(
        select(PsyAppointment).where(
            PsyAppointment.school_id == school_id,
            PsyAppointment.student_id == student_id,
            PsyAppointment.slot_id == data["slot_id"],
            PsyAppointment.status.in_(["pending", "confirmed"]),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("该学生在此时段已有预约, 不可重复申请")

    appointment = PsyAppointment(
        school_id=school_id,
        student_id=student_id,
        applicant_id=applicant_id,
        slot_id=data["slot_id"],
        source=data["source"],
        reason_summary=data.get("reason_summary"),
        status="pending",
        risk_flag=data.get("risk_flag", "green"),
    )
    db.add(appointment)

    # 更新时段已约人数
    slot = await get_slot(db, school_id, data["slot_id"])
    slot.current_booked += 1
    if slot.current_booked >= slot.max_capacity:
        slot.status = "booked"

    await db.commit()
    await db.refresh(appointment)
    return appointment


async def list_appointments(
    db: AsyncSession,
    school_id: int,
    student_id: int = None,
    status: str = None,
    source: str = None,
    slot_id: int = None,
    limit: int = 50,
    offset: int = 0,
    student_ids: set = None,
) -> tuple:
    """查询预约列表(分页)。student_ids: 学生归属范围过滤(None=不限)"""
    conditions = [PsyAppointment.school_id == school_id]
    if student_id:
        conditions.append(PsyAppointment.student_id == student_id)
    if student_ids is not None:
        if not student_ids:
            return [], 0
        conditions.append(PsyAppointment.student_id.in_(student_ids))
    if status:
        conditions.append(PsyAppointment.status == status)
    if source:
        conditions.append(PsyAppointment.source == source)
    if slot_id:
        conditions.append(PsyAppointment.slot_id == slot_id)

    count_stmt = select(func.count(PsyAppointment.id)).where(and_(*conditions))
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = (
        select(PsyAppointment)
        .where(and_(*conditions))
        .order_by(PsyAppointment.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    res = await db.execute(stmt)
    return res.scalars().all(), total


async def update_appointment(
    db: AsyncSession,
    school_id: int,
    appointment_id: int,
    data: dict,
) -> PsyAppointment:
    """心理老师审核/更新预约"""
    stmt = select(PsyAppointment).where(
        PsyAppointment.id == appointment_id,
        PsyAppointment.school_id == school_id,
    )
    res = await db.execute(stmt)
    apt = res.scalar_one_or_none()
    if not apt:
        raise ValueError("预约记录不存在")

    if "status" in data and data["status"]:
        old_status = apt.status
        apt.status = data["status"]
        if data["status"] == "confirmed" and old_status == "pending":
            apt.confirmed_at = datetime.now()
        elif data["status"] == "completed":
            apt.completed_at = datetime.now()
            # 释放时段: completed 时 current_booked - 1
            slot = await get_slot(db, school_id, apt.slot_id)
            if slot:
                slot.current_booked = max(0, slot.current_booked - 1)
                if slot.current_booked < slot.max_capacity:
                    slot.status = "open"

    if "risk_flag" in data and data["risk_flag"] is not None:
        apt.risk_flag = data["risk_flag"]
    if "counselor_note" in data:
        apt.counselor_note = data["counselor_note"]

    await db.commit()
    await db.refresh(apt)
    return apt


# ─────────────────────────────────────────────────────────
# 3. 咨询记录引擎 (加密写实)
# ─────────────────────────────────────────────────────────


async def create_consult_record(
    db: AsyncSession,
    school_id: int,
    counselor_id: int,
    data: dict,
) -> PsyConsultRecord:
    """心理老师加密写实 — 提交咨询记录"""
    # 校验 appointment 存在
    stmt = select(PsyAppointment).where(
        PsyAppointment.id == data["appointment_id"],
        PsyAppointment.school_id == school_id,
    )
    apt_res = await db.execute(stmt)
    appointment = apt_res.scalar_one_or_none()
    if not appointment:
        raise ValueError("关联的预约记录不存在")

    # 幂等检查
    existing = await db.execute(
        select(PsyConsultRecord).where(
            PsyConsultRecord.appointment_id == data["appointment_id"],
            PsyConsultRecord.school_id == school_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("该预约已有咨询记录, 请使用更新接口")

    # 加密落盘
    encrypted = encrypt_clog(data["clog_plaintext"])

    followup = None
    if data.get("followup_date"):
        followup = datetime.strptime(data["followup_date"], "%Y-%m-%d")

    record = PsyConsultRecord(
        school_id=school_id,
        appointment_id=data["appointment_id"],
        student_id=data["student_id"],
        counselor_id=counselor_id,
        encrypted_clog=encrypted,
        risk_level=data.get("risk_level", "green"),
        consult_category=data.get("consult_category"),
        is_crisis=data.get("is_crisis", False),
        is_referred=data.get("is_referred", False),
        referral_target=data.get("referral_target"),
        followup_date=followup,
        session_duration_min=data.get("session_duration_min"),
        encryption_version="v1",
        decryption_access_log=[],
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_consult_record(
    db: AsyncSession,
    school_id: int,
    record_id: int,
    user_role: str,
    user_id: int,
    requester_student_id: int = None,
    allowed_student_ids: set = None,
) -> dict:
    """
    获取咨询记录 — 按角色决定是否解密正文。
    counselor/ms_admin → 完整原文
    其他 → 脱敏摘要
    allowed_student_ids: 学生归属范围(None=不限)，越界一律视为不存在
    """
    stmt = select(PsyConsultRecord).where(
        PsyConsultRecord.id == record_id,
        PsyConsultRecord.school_id == school_id,
    )
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()
    if not record:
        raise ValueError("咨询记录不存在")

    # P0-1: 学生/家长只能访问绑定学生本人的咨询记录，
    # 防止同校用户猜 ID 越权读取他人敏感元数据 (risk_level/is_crisis/referral 等)
    if requester_student_id is not None and record.student_id != requester_student_id:
        raise ValueError("咨询记录不存在")

    # P0-2: 班主任/年级组长等按学生归属范围过滤，越界视为不存在
    if allowed_student_ids is not None and record.student_id not in allowed_student_ids:
        raise ValueError("咨询记录不存在")

    # 解密权限判断
    can_decrypt = await _is_counselor_or_admin(user_role)
    if not can_decrypt:
        # 进一步查 teacher_role_assignments
        can_decrypt = await _check_counselor_role(db, user_id, school_id, user_role)

    plaintext = decrypt_clog(record.encrypted_clog)
    clog_display = (
        _mask_plaintext(plaintext, user_role) if can_decrypt else _mask_plaintext("", "other")
    )

    if can_decrypt:
        # 记录解密审计
        audit_entry = {
            "user_id": user_id,
            "role": (user_role or "").lower(),
            "ts": datetime.now().isoformat(),
        }
        logs = list(record.decryption_access_log or [])
        logs.append(audit_entry)
        record.decryption_access_log = logs
        await db.commit()

    return {
        "id": record.id,
        "appointment_id": record.appointment_id,
        "student_id": record.student_id,
        "counselor_id": record.counselor_id,
        "clog_display": clog_display,
        "risk_level": record.risk_level,
        "consult_category": record.consult_category,
        "is_crisis": record.is_crisis,
        "is_referred": record.is_referred,
        "referral_target": record.referral_target,
        "followup_date": str(record.followup_date) if record.followup_date else None,
        "session_duration_min": record.session_duration_min,
        "created_at": str(record.created_at) if record.created_at else None,
        "updated_at": str(record.updated_at) if record.updated_at else None,
    }


async def list_consult_records(
    db: AsyncSession,
    school_id: int,
    student_id: int = None,
    counselor_id: int = None,
    risk_level: str = None,
    is_crisis: bool = None,
    limit: int = 50,
    offset: int = 0,
    student_ids: set = None,
) -> tuple:
    """查询咨询记录列表(分页) — 不含解密正文。student_ids: 学生归属范围过滤(None=不限)"""
    conditions = [PsyConsultRecord.school_id == school_id]
    if student_id:
        conditions.append(PsyConsultRecord.student_id == student_id)
    if student_ids is not None:
        if not student_ids:
            return [], 0
        conditions.append(PsyConsultRecord.student_id.in_(student_ids))
    if counselor_id:
        conditions.append(PsyConsultRecord.counselor_id == counselor_id)
    if risk_level:
        conditions.append(PsyConsultRecord.risk_level == risk_level)
    if is_crisis is not None:
        conditions.append(PsyConsultRecord.is_crisis == is_crisis)

    count_stmt = select(func.count(PsyConsultRecord.id)).where(and_(*conditions))
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = (
        select(PsyConsultRecord)
        .where(and_(*conditions))
        .order_by(PsyConsultRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    res = await db.execute(stmt)
    return res.scalars().all(), total


async def get_counselor_stats(
    db: AsyncSession,
    school_id: int,
    counselor_id: int,
) -> dict:
    """心理老师工作台 — 统计概览"""
    base_cond = and_(
        PsyConsultRecord.school_id == school_id,
        PsyConsultRecord.counselor_id == counselor_id,
    )

    # 总场次
    total_res = await db.execute(select(func.count(PsyConsultRecord.id)).where(base_cond))
    total_sessions = total_res.scalar() or 0

    # 服务学生数(去重)
    student_res = await db.execute(
        select(func.count(func.distinct(PsyConsultRecord.student_id))).where(base_cond)
    )
    total_students = student_res.scalar() or 0

    # 危机数
    crisis_res = await db.execute(
        select(func.count(PsyConsultRecord.id)).where(
            base_cond,
            PsyConsultRecord.is_crisis,
        )
    )
    crisis_count = crisis_res.scalar() or 0

    # 转介数
    referral_res = await db.execute(
        select(func.count(PsyConsultRecord.id)).where(
            base_cond,
            PsyConsultRecord.is_referred,
        )
    )
    referral_count = referral_res.scalar() or 0

    # 平均时长
    avg_res = await db.execute(
        select(func.avg(PsyConsultRecord.session_duration_min)).where(
            base_cond,
            PsyConsultRecord.session_duration_min.isnot(None),
        )
    )
    avg_duration = avg_res.scalar()

    # 风险分布
    risk_rows = await db.execute(
        select(
            PsyConsultRecord.risk_level,
            func.count(PsyConsultRecord.id),
        )
        .where(base_cond)
        .group_by(PsyConsultRecord.risk_level)
    )
    risk_dist = {row[0]: row[1] for row in risk_rows.all()}

    # 分类分布
    cat_rows = await db.execute(
        select(
            PsyConsultRecord.consult_category,
            func.count(PsyConsultRecord.id),
        )
        .where(
            base_cond,
            PsyConsultRecord.consult_category.isnot(None),
        )
        .group_by(PsyConsultRecord.consult_category)
    )
    cat_dist = {row[0]: row[1] for row in cat_rows.all()}

    # 待处理预约
    pending_res = await db.execute(
        select(func.count(PsyAppointment.id)).where(
            PsyAppointment.school_id == school_id,
            PsyAppointment.status == "pending",
        )
    )
    pending_count = pending_res.scalar() or 0

    # 未来7天待确认
    today = date.today()
    upcoming_res = await db.execute(
        select(func.count(PsyAppointment.id))
        .join(
            PsyConsultableSlot,
            PsyAppointment.slot_id == PsyConsultableSlot.id,
        )
        .where(
            PsyAppointment.school_id == school_id,
            PsyAppointment.status == "confirmed",
            PsyConsultableSlot.date >= today,
            PsyConsultableSlot.date <= today + timedelta(days=7),
        )
    )
    upcoming_count = upcoming_res.scalar() or 0

    return {
        "counselor_id": counselor_id,
        "total_sessions": total_sessions,
        "total_students": total_students,
        "crisis_count": crisis_count,
        "referral_count": referral_count,
        "avg_duration_min": round(avg_duration, 1) if avg_duration else None,
        "risk_distribution": risk_dist,
        "category_distribution": cat_dist,
        "upcoming_appointments": upcoming_count,
        "pending_appointments": pending_count,
    }
