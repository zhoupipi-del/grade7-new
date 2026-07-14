"""
心理档案 + 筛查流水 + 双轨预警 Nexus 路由层

端点清单 (14):
  ── 心理档案 ──
  GET    /profiles                       — 档案列表(分页+风险等级/标签筛选)
  GET    /profiles/{student_id}          — 档案详情(含筛查历史+咨询摘要)
  POST   /profiles/{student_id}          — 初始化学生心理档案
  PUT    /profiles/{student_id}          — 更新档案(风险等级/标签/备注)
  PUT    /profiles/{student_id}/tags     — 更新标签云
  DELETE /profiles/{student_id}          — 删除档案
  POST   /profiles/{student_id}/recompute — 重新聚合统计(咨询/筛查/干预次数)

  ── 筛查快照 ──
  POST   /screenings                     — 录入筛查快照
  GET    /screenings                     — 筛查列表(分页+筛选)
  GET    /screenings/{student_id}        — 学生筛查历史

  ── 双轨预警 Nexus ──
  GET    /nexus/comprehensive-risks      — 学业x心理双轨预警合成视图
  GET    /nexus/student/{student_id}     — 单个学生双轨详细画像

  ── 统计 ──
  GET    /dashboard                      — 心理档案仪表盘
  GET    /tags/suggestions               — 标签建议(高频标签)
"""

from core.models import Class, Grade, Student, User, get_local_now
from core.routers import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, Query, status
from modules.psych_profiles import services as svc
from modules.psych_profiles.models import PsyProfile
from modules.psych_profiles.schemas import (
    PsyProfileCreate,
    PsyProfileUpdate,
    PsyScreeningCreate,
    TagsUpdate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["心理档案与双轨预警"])


# ============================================================
# 角色门禁
# ============================================================
async def require_psych_write(
    current_user: User = Depends(get_current_user),
) -> User:
    """写操作门禁: MS_ADMIN / counselor / GRADE_LEADER"""
    role = (current_user.role or "").lower()
    if role not in {"ms_admin", "counselor", "grade_leader"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅系统管理员、心理老师和年级组长可操作心理档案",
        )
    return current_user


async def require_psych_read(
    current_user: User = Depends(get_current_user),
) -> User:
    """读操作门禁: MS_ADMIN / counselor / GRADE_LEADER / CLASS_TEACHER"""
    role = (current_user.role or "").lower()
    if role not in {"ms_admin", "counselor", "grade_leader", "class_teacher"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问心理档案数据",
        )
    return current_user


# ============================================================
# 辅助函数
# ============================================================
async def _get_student_info(db: AsyncSession, student_id: int):
    """获取学生基本信息 (name, class_name, grade_name)"""
    stmt = (
        select(Student, Class, Grade)
        .outerjoin(Class, Student.class_id == Class.id)
        .outerjoin(Grade, Student.grade_id == Grade.id)
        .where(Student.id == student_id)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        return None, None, None, None
    student, class_, grade = row
    return student, class_, grade, student


def _profile_to_response(profile: PsyProfile, student_name=None, class_name=None) -> dict:
    """将 ORM 对象转换为响应字典"""
    return {
        "id": profile.id,
        "student_id": profile.student_id,
        "risk_level": profile.risk_level,
        "risk_level_source": profile.risk_level_source,
        "risk_level_updated_at": profile.risk_level_updated_at,
        "risk_level_updated_by": profile.risk_level_updated_by,
        "tags": profile.tags or [],
        "guardian_contact_status": profile.guardian_contact_status,
        "guardian_contact_note": profile.guardian_contact_note,
        "total_counseling_count": profile.total_counseling_count or 0,
        "total_screening_count": profile.total_screening_count or 0,
        "total_intervention_count": profile.total_intervention_count or 0,
        "highest_risk_level": profile.highest_risk_level or "green",
        "is_referred": profile.is_referred or False,
        "referral_status": profile.referral_status,
        "referral_target": profile.referral_target,
        "last_counseling_date": profile.last_counseling_date,
        "last_screening_date": profile.last_screening_date,
        "last_intervention_date": profile.last_intervention_date,
        "notes": profile.notes,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


# ============================================================
# 一、心理档案 CRUD
# ============================================================
@router.get("/profiles")
async def api_list_profiles(
    risk_level: str = Query(None, description="风险等级筛选: green/yellow/orange/red"),
    tag: str = Query(None, description="标签筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """心理档案列表 — 支持风险等级/标签筛选"""
    profiles, total = await svc.list_profiles(
        db,
        school_id=current_user.school_id,
        risk_level=risk_level,
        tag=tag,
        page=page,
        page_size=page_size,
    )

    # 批量获取学生姓名
    student_ids = [p.student_id for p in profiles]
    name_map = {}
    if student_ids:
        stmt = select(Student.id, Student.name).where(Student.id.in_(student_ids))
        for sid, sname in (await db.execute(stmt)).all():
            name_map[sid] = sname

    items = []
    for p in profiles:
        item = _profile_to_response(p)
        item["student_name"] = name_map.get(p.student_id)
        items.append(item)

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/profiles/{student_id}")
async def api_get_profile(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """心理档案详情 — 含学生基本信息 + 最近筛查/咨询记录"""
    profile = await svc.get_profile(db, current_user.school_id, student_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="该学生暂无心理档案")

    # 学生基本信息
    student, class_, grade, _ = await _get_student_info(db, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="学生不存在")

    item = _profile_to_response(profile)
    item["student_name"] = student.name
    item["student_no"] = student.student_no
    item["class_name"] = class_.name if class_ else None
    item["grade_name"] = grade.name if grade else None

    # 最近筛查记录
    screenings = await svc.get_student_screenings(db, current_user.school_id, student_id, limit=5)
    item["recent_screenings"] = [
        {
            "id": s.id,
            "scale_name": s.scale_name,
            "risk_level": s.risk_level,
            "total_score": s.total_score,
            "test_date": s.test_date.isoformat() if s.test_date else None,
        }
        for s in screenings
    ]

    # 最近咨询记录 (脱敏 — 仅显示元数据, 不解密内容)
    item["recent_counselings"] = []
    try:
        from modules.psych_counseling.models import PsyConsultRecord

        counsel_stmt = (
            select(PsyConsultRecord)
            .where(PsyConsultRecord.student_id == student_id)
            .order_by(PsyConsultRecord.created_at.desc())
            .limit(5)
        )
        for cr in (await db.execute(counsel_stmt)).scalars().all():
            item["recent_counselings"].append(
                {
                    "id": cr.id,
                    "risk_level": cr.risk_level,
                    "consult_category": cr.consult_category,
                    "is_crisis": cr.is_crisis,
                    "is_referred": cr.is_referred,
                    "created_at": cr.created_at.isoformat() if cr.created_at else None,
                    # 注意: encrypted_clog 不返回 — 隐私切面
                }
            )
    except ImportError:
        pass

    # 最近干预记录
    item["recent_interventions"] = []
    try:
        from modules.psych_screening.models import InterventionRecord

        interv_stmt = (
            select(InterventionRecord)
            .where(InterventionRecord.student_id == student_id)
            .order_by(InterventionRecord.intervention_date.desc())
            .limit(5)
        )
        for ir in (await db.execute(interv_stmt)).scalars().all():
            item["recent_interventions"].append(
                {
                    "id": ir.id,
                    "intervention_type": ir.intervention_type,
                    "intervention_date": ir.intervention_date.isoformat()
                    if ir.intervention_date
                    else None,
                    "status": ir.status,
                    "effect_rating": ir.effect_rating,
                }
            )
    except ImportError:
        pass

    return item


@router.post("/profiles/{student_id}")
async def api_create_profile(
    student_id: int,
    payload: PsyProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_write),
):
    """初始化学生心理档案"""
    existing = await svc.get_profile(db, current_user.school_id, student_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="该学生已有心理档案, 请使用 PUT 更新")

    profile = await svc.get_or_create_profile(db, current_user.school_id, student_id)
    # 应用传入的初始值
    update_data = payload.model_dump(exclude_none=True)
    if update_data:
        updated = await svc.update_profile(
            db,
            current_user.school_id,
            student_id,
            {
                **update_data,
                "risk_level_updated_at": get_local_now(),
                "risk_level_updated_by": current_user.id,
            },
        )
        if updated:
            profile = updated

    await db.commit()
    return _profile_to_response(profile)


@router.put("/profiles/{student_id}")
async def api_update_profile(
    student_id: int,
    payload: PsyProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_write),
):
    """更新心理档案"""
    update_data = payload.model_dump(exclude_none=True)
    if "risk_level" in update_data:
        update_data["risk_level_updated_by"] = current_user.id

    profile = await svc.update_profile(db, current_user.school_id, student_id, update_data)
    if profile is None:
        raise HTTPException(status_code=404, detail="心理档案不存在")

    await db.commit()
    return _profile_to_response(profile)


@router.put("/profiles/{student_id}/tags")
async def api_update_tags(
    student_id: int,
    payload: TagsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_write),
):
    """更新标签云 (完整替换)"""
    profile = await svc.update_tags(db, current_user.school_id, student_id, payload.tags)
    if profile is None:
        raise HTTPException(status_code=404, detail="心理档案不存在")

    await db.commit()
    return {"status": "success", "student_id": student_id, "tags": profile.tags}


@router.delete("/profiles/{student_id}")
async def api_delete_profile(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_write),
):
    """删除心理档案"""
    ok = await svc.delete_profile(db, current_user.school_id, student_id)
    if not ok:
        raise HTTPException(status_code=404, detail="心理档案不存在")

    await db.commit()
    return {"status": "success", "message": "心理档案已删除"}


@router.post("/profiles/{student_id}/recompute")
async def api_recompute_profile(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_write),
):
    """重新聚合统计 — 从子表重新计算咨询/筛查/干预次数和最近活动时间"""
    profile = await svc.recompute_profile_stats(db, current_user.school_id, student_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="操作失败")

    await db.commit()
    return _profile_to_response(profile)


# ============================================================
# 二、筛查快照
# ============================================================
@router.post("/screenings")
async def api_create_screening(
    payload: PsyScreeningCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_write),
):
    """录入筛查快照 — 自动更新心理档案风险等级"""
    record = await svc.create_screening(
        db,
        school_id=current_user.school_id,
        operator_id=current_user.id,
        data=payload.model_dump(),
    )
    await db.commit()
    return {
        "id": record.id,
        "student_id": record.student_id,
        "scale_name": record.scale_name,
        "risk_level": record.risk_level,
        "test_date": record.test_date.isoformat() if record.test_date else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/screenings")
async def api_list_screenings(
    student_id: int = Query(None),
    scale_name: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """筛查快照列表"""
    records, total = await svc.list_screenings(
        db,
        school_id=current_user.school_id,
        student_id=student_id,
        scale_name=scale_name,
        page=page,
        page_size=page_size,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": r.id,
                "student_id": r.student_id,
                "scale_name": r.scale_name,
                "risk_level": r.risk_level,
                "total_score": r.total_score,
                "risk_factors": r.risk_factors or [],
                "test_date": r.test_date.isoformat() if r.test_date else None,
            }
            for r in records
        ],
    }


@router.get("/screenings/{student_id}")
async def api_student_screenings(
    student_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """学生筛查历史"""
    records = await svc.get_student_screenings(db, current_user.school_id, student_id, limit)
    return {
        "student_id": student_id,
        "total": len(records),
        "items": [
            {
                "id": r.id,
                "scale_name": r.scale_name,
                "scale_version": r.scale_version,
                "raw_scores": r.raw_scores,
                "total_score": r.total_score,
                "risk_factors": r.risk_factors or [],
                "risk_level": r.risk_level,
                "conclusion": r.conclusion,
                "ai_generated": r.ai_generated,
                "source": r.source,
                "test_date": r.test_date.isoformat() if r.test_date else None,
            }
            for r in records
        ],
    }


# ============================================================
# 三、双轨预警 Nexus
# ============================================================
@router.get("/nexus/comprehensive-risks")
async def api_comprehensive_risks(
    co_trigger_only: bool = Query(False, description="仅显示双预警学生"),
    min_priority: str = Query("WATCH", description="最低优先级: NORMAL/WATCH/URGENT/CRITICAL"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """
    学业x心理双轨预警合成视图

    联表 4 张异构表输出合成预警:
      - student_risk_alerts (Z-Score 学业)
      - risk_warnings (RDI 四维)
      - psy_profiles (心理档案)
      - psy_screening_records (筛查快照)
    """
    data = await svc.get_comprehensive_risks(
        db,
        school_id=current_user.school_id,
        co_trigger_only=co_trigger_only,
        min_priority=min_priority,
        page=page,
        page_size=page_size,
    )
    return data


@router.get("/nexus/student/{student_id}")
async def api_student_nexus(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """单个学生双轨详细画像 — 学业预警历史 + 筛查历史 + RDI四维 + 咨询摘要"""
    detail = await svc.get_student_nexus_detail(db, current_user.school_id, student_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    return detail


# ============================================================
# 四、统计
# ============================================================
@router.get("/dashboard")
async def api_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """心理档案仪表盘聚合统计"""
    data = await svc.get_dashboard_stats(db, current_user.school_id)
    return data


@router.get("/tags/suggestions")
async def api_tag_suggestions(
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_psych_read),
):
    """标签建议 — 从现有档案中提取高频标签"""
    tags = await svc.get_tag_suggestions(db, current_user.school_id, limit)
    return {"tags": tags}
