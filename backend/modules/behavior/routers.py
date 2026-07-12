"""
modules/behavior/routers.py — 违纪行为管理 API

端点:
  POST   /api/v1/behavior/records         创建违纪记录
  GET    /api/v1/behavior/records         分页查询违纪列表
  GET    /api/v1/behavior/records/{id}    查看单条违纪
  PUT    /api/v1/behavior/records/{id}    编辑违纪
  DELETE /api/v1/behavior/records/{id}    删除违纪
  POST   /api/v1/behavior/records/{id}/resolve  标记已解决
  GET    /api/v1/behavior/stats           违纪统计
  GET    /api/v1/behavior/escalation/{student_id}  升级风险评估
  POST   /api/v1/behavior/appeals         提交申诉
  GET    /api/v1/behavior/appeals         申诉列表
  POST   /api/v1/behavior/appeals/{id}/review  审核申诉
"""

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import User, UserRole
from core.routers import get_db, get_current_user, require_role
from .services import BehaviorService
from .schemas import (
    DisciplineCreate, DisciplineUpdate, DisciplineOut,
    DisciplineStatsOut, AppealCreate, AppealReview, AppealOut,
)

router = APIRouter(tags=["behavior"])


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _resolve_role(role) -> str:
    """自呼吸看守熔断 — 杜绝 str/enum 混合体 AttributeError，始终返回纯字符串"""
    if isinstance(role, UserRole):
        return role.value
    if isinstance(role, str):
        try:
            return UserRole(role).value
        except ValueError:
            return role
    return str(role)


# ═══════════════════════════════════════════════════════════════
# 违纪记录 CRUD
# ═══════════════════════════════════════════════════════════════

@router.post("/records", response_model=DisciplineOut, status_code=201)
async def create_discipline(
    body: DisciplineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN, UserRole.GRADE_LEADER, UserRole.CLASS_TEACHER)),
):
    """创建违纪记录 — 自动触发累计扣分升级检查"""
    try:
        record = await BehaviorService.create_record(
            db, current_user.school_id,
            body.model_dump(), current_user.id,
            creator_role=_resolve_role(current_user.role),
        )
        return _format_record(record)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/records")
async def list_discipline(
    class_id: Optional[int] = None,
    grade_id: Optional[int] = None,
    student_id: Optional[int] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分页查询违纪记录列表"""
    offset = (page - 1) * per_page
    records, total = await BehaviorService.list_records(
        db, current_user.school_id,
        class_id=class_id, grade_id=grade_id, student_id=student_id,
        type=type, status=status,
        start_date=start_date, end_date=end_date,
        limit=per_page, offset=offset,
    )
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        "items": [_format_record(r) for r in records],
        "total": total, "page": page, "per_page": per_page,
        "pages": pages,
    }


@router.get("/records/{record_id}")
async def get_discipline(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = await BehaviorService.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="违纪记录不存在")
    return _format_record(record)


@router.put("/records/{record_id}", response_model=DisciplineOut)
async def update_discipline(
    record_id: int,
    body: DisciplineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑违纪记录"""
    record = await BehaviorService.update_record(db, record_id, body.model_dump(exclude_none=True))
    if not record:
        raise HTTPException(status_code=404, detail="违纪记录不存在")
    return _format_record(record)


@router.delete("/records/{record_id}")
async def delete_discipline(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _guard: User = Depends(require_role(UserRole.MS_ADMIN)),
):
    """删除违纪记录 — 仅德育处管理员"""
    ok = await BehaviorService.delete_record(db, record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="违纪记录不存在")
    return {"message": "已删除"}


@router.post("/records/{record_id}/resolve", response_model=DisciplineOut)
async def resolve_discipline(
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记违纪已解决"""
    record = await BehaviorService.resolve_record(db, record_id)
    if not record:
        raise HTTPException(status_code=400, detail="无法解决该违纪记录（可能已解决或不存在）")
    return _format_record(record)


# ═══════════════════════════════════════════════════════════════
# 统计 & 风险评估
# ═══════════════════════════════════════════════════════════════

@router.get("/stats")
async def discipline_stats(
    grade_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """违纪统计概览（按类型/分类/班级/月份分组）"""
    return await BehaviorService.get_stats(
        db, current_user.school_id,
        grade_id=grade_id,
        start_date=start_date, end_date=end_date,
    )


@router.get("/escalation/{student_id}")
async def escalation_risk(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询学生的累计扣分升级风险"""
    return await BehaviorService.get_escalation_risk(db, student_id)


# ═══════════════════════════════════════════════════════════════
# 申诉
# ═══════════════════════════════════════════════════════════════

@router.post("/appeals", response_model=AppealOut, status_code=201)
async def create_appeal(
    body: AppealCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交违纪申诉（家长端）"""
    try:
        appeal = await BehaviorService.create_appeal(
            db, current_user.school_id,
            body.model_dump(),
            current_user.id,
            current_user.bound_student_id or 0,
            current_user.class_id or 0,
            current_user.grade_id or 0,
        )
        return _format_appeal(appeal)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/appeals")
async def list_appeals(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appeals, total = await BehaviorService.list_appeals(
        db, current_user.school_id,
        status=status,
        limit=per_page, offset=(page - 1) * per_page,
    )
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    return {
        "items": [_format_appeal(a) for a in appeals],
        "total": total, "page": page, "per_page": per_page,
        "pages": pages,
    }


@router.post("/appeals/{appeal_id}/review", response_model=AppealOut)
async def review_appeal(
    appeal_id: int,
    body: AppealReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """审核申诉（班主任/年级组长/德育处）"""
    appeal = await BehaviorService.review_appeal(
        db, appeal_id, body.status,
        body.review_comment or "", current_user.id,
    )
    if not appeal:
        raise HTTPException(status_code=400, detail="申诉不存在或已处理")
    return _format_appeal(appeal)


# ═══════════════════════════════════════════════════════════════
# 格式化辅助
# ═══════════════════════════════════════════════════════════════

def _format_record(r) -> dict:
    """安全格式化违纪记录，容错关系未加载"""
    try:
        student_name = r.student.name if r.student else None
        student_no = r.student.student_no if r.student else None
        class_name = r.student.class_.name if r.student and getattr(r.student, 'class_', None) else None
        creator_name = r.creator.display_name if r.creator else None
    except Exception:
        student_name = student_no = class_name = creator_name = None
    return {
        "id": r.id,
        "student_id": r.student_id,
        "student_name": student_name,
        "student_no": student_no,
        "class_id": r.class_id,
        "class_name": class_name,
        "grade_id": r.grade_id,
        "type": r.type,
        "category": r.category,
        "description": r.description,
        "action_taken": r.action_taken,
        "points": r.points,
        "status": r.status,
        "verify_status": r.verify_status,
        "incident_date": r.incident_date.isoformat() if r.incident_date else None,
        "created_by": r.created_by,
        "creator_name": creator_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
    }


def _format_appeal(a) -> dict:
    return {
        "id": a.id,
        "discipline_id": a.discipline_id,
        "student_id": a.student_id,
        "student_name": a.student.name if a.student else None,
        "reason": a.reason,
        "status": a.status,
        "review_comment": a.review_comment,
        "reviewer_name": a.reviewer.display_name if a.reviewer else None,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
